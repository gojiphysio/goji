#!/usr/bin/env python3
"""
Cloud Run Job: send 48-hour appointment reminder emails.

Runs daily at 12:00 SGT (Cloud Scheduler, --time-zone Asia/Singapore) and emails
every patient whose appointment is two calendar days out — Monday's run covers
Wednesday. Replaces a manual chore: Plato's reminder template can only be fired
by hand from its UI (its API has no notification endpoint), so someone had to log
in every day and click it.

Not an ingestion job — it reads marts and sends mail, writing nothing but its own
send ledger. Hence scripts/reminders/ rather than scripts/ingestion/.

FLOW
  1. Read marts.fct_appointment_reminders (D+2, PII-free), hydrating name/email/
     phone at query time from the appointment payload and dim_patient_contact —
     the same hydration join fetch_new_patient_welcome uses in dashboard/app.py.
     Anything already 'sent' in the ledger is suppressed in SQL. The D+2 window
     lives in the view's WHERE clause and nowhere else.
  2. Group by recipient email: ONE email per patient per day, listing every
     session they have that day. Two reasons this matters — a home visit is
     three Plato appointments (travel/visit/travel), and back-to-back bookings
     (physio then Pilates) shouldn't produce two emails.
  3. Send. Each recipient is wrapped in try/except, so one bad address can't take
     down the run — same best-effort posture as booking/mailer.py.
  4. Append one ledger row per appointment_id (not per email), so the idempotency
     guard stays correct if one of a patient's sessions is later cancelled.
  5. Email the clinic a digest: who was sent, and — the part that matters — who
     had no email address and needs a WhatsApp instead.

SAFETY
  Two guards. Test mode deliberately WINS over DRY_RUN:
    DRY_RUN=true            -> nothing is sent to anyone but the digest.
    REMINDER_OVERRIDE_TO=x  -> reminders are really sent, but every one goes to
                               x. Sufficient on its own; do NOT pair it with
                               DRY_RUN=false. On an image that predates this
                               flag the override is ignored, and DRY_RUN=false
                               then mails real patients — which is exactly how 8
                               were emailed on 2026-09-10.
  DRY_RUN=true renders and groups everything, sends NO patient email, writes
  'dry_run' ledger rows (a distinct status, so it never suppresses the real send)
  and still delivers the digest. This is how the job ships; flip the flag only
  once the front desk has stopped clicking the button in Plato, or patients get
  two reminders.

Env vars:
  BQ_PROJECT            BigQuery project            default: goji-bi
  BQ_DATASET            Marts dataset               default: marts
  DRY_RUN               'true' => send nothing      default: true
  REMINDER_OVERRIDE_TO  test mode: send every patient reminder HERE instead of
                        to the patient. Real end-to-end send, reaches nobody.
                        Ledgered as 'test', so it never suppresses the real
                        reminder. Setting this ALONE is enough — it overrides
                        DRY_RUN, so testing never requires DRY_RUN=false.
                        Unset in normal operation.
  REMINDER_BCC          copy every real patient send here (Bcc).
                        default: hello@gojiphysio.com
  GMAIL_APP_PASSWORD    SMTP app password           (required unless DRY_RUN)
  REMINDER_ADMIN_EMAIL  Digest recipient            default: hello@gojiphysio.com
  (see reminder_mailer.py for the SMTP_* / link overrides)

Exit codes: 0 on success, 1 on config error, 2 on BQ failure, 3 if every send failed.
"""
from __future__ import annotations

import logging
import os
import re
import sys
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from google.cloud import bigquery

import reminder_mailer as mailer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("appointment-reminders")

SGT = ZoneInfo("Asia/Singapore")
# Mirrors the window in marts/47_fct_appointment_reminders.sql. The view is the
# source of truth; this is only used to label a run that returned no rows.
REMINDER_DAYS_AHEAD = 2


def env(name: str, default: str | None = None, required: bool = True) -> str:
    v = os.environ.get(name, default)
    if required and not v:
        log.error(f"missing env var: {name}")
        sys.exit(1)
    return v  # type: ignore[return-value]


def env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


# --- pure logic (unit-tested) ----------------------------------------------

def target_date(days_ahead: int = REMINDER_DAYS_AHEAD, *,
                now: datetime | None = None) -> str:
    """The clinic-local date we're reminding about, as 'YYYY-MM-DD'.

    ONLY used to label an empty run (no appointments -> no row to read a date
    from). When there ARE rows, the date comes from the rows themselves — see
    resolve_appt_date. The window is defined in exactly one place, the view's
    WHERE clause; duplicating it here as config would let SQL and Python drift
    apart and mail people a date that doesn't match their appointment.

    Clinic-local on purpose: the whole job keys on dates in Asia/Singapore, which
    is what makes it immune to the start_at wall-clock-stored-as-UTC trap
    documented in marts/47_fct_appointment_reminders.sql.
    """
    ref = now or datetime.now(SGT)
    return (ref.astimezone(SGT).date() + timedelta(days=days_ahead)).isoformat()


_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def scrub(text: str | None, limit: int = 400) -> str | None:
    """Strip email addresses out of an error before it reaches the ledger.

    The event log is PII-free by design (see marts/48_appointment_reminder_events.sql)
    and the likeliest send failure is smtplib.SMTPRecipientsRefused, whose str()
    is a dict keyed on the patient's address — so writing str(e) raw would put an
    address in the warehouse. The status and the appointment_id are enough to act
    on; the address is recoverable from Plato.
    """
    if not text:
        return None
    return _EMAIL_RE.sub("[email]", text)[:limit]


def resolve_appt_date(rows: list[dict]) -> str:
    """The date being reminded about, taken from the data rather than recomputed.

    The view returns exactly one appt_date, so any row answers it. Falling back
    to target_date() only matters for an empty run, where the date is just a
    label on the digest.
    """
    for r in rows:
        d = r.get("appt_date")
        if d:
            return d.isoformat() if hasattr(d, "isoformat") else str(d)
    return target_date()


def group_by_recipient(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split query rows into (sendable groups, unreachable rows).

    Sendable groups are keyed on lowercased email so one patient with several
    sessions that day gets a single email. Each group carries every
    appointment_id in it, so the caller can ledger them all.

    A row is unreachable when no email survived hydration. Those become the
    digest's WhatsApp list — they are NOT an error.
    """
    groups: dict[str, dict] = {}
    unreachable: list[dict] = []
    for r in rows:
        email = (r.get("email") or "").strip()
        if not email:
            unreachable.append(r)
            continue
        key = email.lower()
        g = groups.setdefault(key, {
            "email": email,
            "name": r.get("name"),
            "phone": r.get("phone"),
            "appointment_ids": [],
            "times": [],
            "has_clinic": False,
            "has_home_visit": False,
        })
        g["appointment_ids"].append(r["appointment_id"])
        if r.get("time"):
            g["times"].append(r["time"])
        if r.get("is_home_visit"):
            g["has_home_visit"] = True
        else:
            g["has_clinic"] = True
        # Prefer a real name over a blank one if the rows disagree.
        if not g["name"] and r.get("name"):
            g["name"] = r.get("name")
    for g in groups.values():
        g["times"] = sorted(set(g["times"]))
    # Stable, human order: earliest session first.
    ordered = sorted(groups.values(), key=lambda g: g["times"][0] if g["times"] else "")
    return ordered, unreachable


# --- BigQuery --------------------------------------------------------------

RECIPIENTS_SQL = """
SELECT
  r.appointment_id,
  r.appt_date,
  r.appt_time_sgt                       AS time,
  r.is_home_visit,
  r.treatment_type,
  -- Hydrate contact at query time (the view itself is PII-free). Inline payload
  -- contact covers profile-less website/walk-in bookings; dim_patient_contact
  -- covers linked patients. Mirrors fetch_new_patient_welcome in dashboard/app.py.
  COALESCE(NULLIF(TRIM(c.full_name), ''),
           NULLIF(TRIM(JSON_VALUE(a.payload, '$.title')), ''))  AS name,
  -- Payload email first (the front desk typed it for THIS booking, so it's the
  -- most current), then the Plato profile. The profile is what makes this job
  -- viable at all: only ~4% of upcoming appointments carry an inline address,
  -- while the profile has one for nearly every linked patient.
  COALESCE(NULLIF(TRIM(JSON_VALUE(a.payload, '$.email')), ''),
           NULLIF(TRIM(c.email), ''))                           AS email,
  COALESCE(NULLIF(TRIM(JSON_VALUE(a.payload, '$.handphone')), ''),
           NULLIF(TRIM(c.phone), ''))                           AS phone
FROM `{project}.{dataset}.fct_appointment_reminders` r
LEFT JOIN `{project}.stg.appointments`                a USING (appointment_id)
LEFT JOIN `{project}.{dataset}.dim_patient_contact`   c ON r.patient_id = c.patient_id
LEFT JOIN `{project}.{dataset}.appointment_reminder_latest` e USING (appointment_id)
-- Idempotency guard: never re-send. 'failed' and 'dry_run' fall through on
-- purpose so a failure retries next run and a dry run doesn't block go-live.
WHERE COALESCE(e.status, '') != 'sent'
ORDER BY r.appt_time_sgt
"""


def fetch_recipients(bq: bigquery.Client, project: str, dataset: str) -> list[dict]:
    sql = RECIPIENTS_SQL.format(project=project, dataset=dataset)
    return [dict(r) for r in bq.query(sql).result()]


def write_ledger(bq: bigquery.Client, project: str, dataset: str,
                 entries: list[tuple[str, str, str | None]], appt_date: str) -> None:
    """Append one row per appointment. entries = [(appointment_id, status, note)].

    Parameterised DML INSERT (a query job), not streaming — the house pattern for
    every event log here (see record_welcome_contacted in dashboard/app.py). It
    honours the SA's table-level dataEditor grant and avoids BigQuery's limits on
    mutating recently-streamed rows. Daily volume is tens of rows, so one
    multi-row INSERT is plenty.
    """
    if not entries:
        return
    values, params = [], [
        bigquery.ScalarQueryParameter("appt_date", "DATE", appt_date),
    ]
    for i, (appt_id, status, note) in enumerate(entries):
        values.append(f"(@e{i}, @a{i}, @appt_date, @s{i}, @n{i}, CURRENT_TIMESTAMP())")
        params += [
            bigquery.ScalarQueryParameter(f"e{i}", "STRING", str(uuid.uuid4())),
            bigquery.ScalarQueryParameter(f"a{i}", "STRING", appt_id),
            bigquery.ScalarQueryParameter(f"s{i}", "STRING", status),
            bigquery.ScalarQueryParameter(f"n{i}", "STRING", note),
        ]
    sql = (f"INSERT INTO `{project}.{dataset}.appointment_reminder_events`\n"
           "  (event_id, appointment_id, appt_date, status, note, sent_at)\n"
           "VALUES\n  " + ",\n  ".join(values))
    bq.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()


# --- entrypoint ------------------------------------------------------------

def main() -> int:
    project = env("BQ_PROJECT", "goji-bi")
    dataset = env("BQ_DATASET", "marts")
    # Defaults to TRUE: a misconfigured deploy must never surprise-mail patients.
    dry_run = env_bool("DRY_RUN", True)

    # TEST MODE OVERRIDES DRY_RUN, and that asymmetry is deliberate.
    #
    # Test mode used to require DRY_RUN=false as well, which meant the test
    # procedure was two settings where one of them is "mail real patients". Run
    # against an image that predates REMINDER_OVERRIDE_TO, the override is
    # silently ignored and DRY_RUN=false does exactly what it says — which is
    # how 8 patients were emailed on 2026-09-10.
    #
    # Now REMINDER_OVERRIDE_TO alone is enough. On an older image, setting it
    # does nothing at all and the job stays in dry run. The failure mode of
    # "wrong image" is now "nothing happens" instead of "mails patients".
    if mailer.OVERRIDE_TO:
        dry_run = False

    if not dry_run and not mailer.SMTP_PASS:
        log.error("DRY_RUN is false but GMAIL_APP_PASSWORD is unset; refusing to run")
        return 1

    try:
        bq = bigquery.Client(project=project)
        rows = fetch_recipients(bq, project, dataset)
    except Exception as e:
        log.error("BigQuery read failed: %s", e)
        return 2

    # Read the date off the rows, never recompute it — see resolve_appt_date.
    day = resolve_appt_date(rows)
    if mailer.OVERRIDE_TO:
        log.warning("TEST MODE: really sending, but every reminder goes to %s. "
                    "No patient is mailed. (DRY_RUN is ignored in test mode.)",
                    mailer.OVERRIDE_TO)
    log.info("reminders for %s (dry_run=%s, test_mode=%s)",
             day, dry_run, bool(mailer.OVERRIDE_TO))

    groups, unreachable = group_by_recipient(rows)
    log.info("%d appointment(s) due; %d recipient group(s), %d unreachable",
             len(rows), len(groups), len(unreachable))

    sent: list[dict] = []
    failed: list[dict] = []
    ledger: list[tuple[str, str, str | None]] = []

    for g in groups:
        # Log lines key on appointment_id, never on the recipient address.
        # Cloud Logging is a different surface from BigQuery but the same PII
        # boundary applies: it's retained ~30 days and readable by anyone with a
        # logging role. The appointment_id is enough to trace a send, and the
        # digest to hello@ carries the human-readable list.
        ref = g["appointment_ids"][0]
        summary = {"name": g["name"], "time": g["times"][0] if g["times"] else "",
                   "email": g["email"]}
        if dry_run:
            log.info("DRY RUN would send to appointment %s (%d appt)", ref,
                     len(g["appointment_ids"]))
            sent.append(summary)
            ledger += [(i, "dry_run", None) for i in g["appointment_ids"]]
            continue
        try:
            mailer.send_reminder(
                g["email"], g["name"], day, g["times"],
                has_clinic=g["has_clinic"], has_home_visit=g["has_home_visit"],
                ref=ref)
            sent.append(summary)
            # TEST MODE writes 'test', never 'sent' — otherwise a test run would
            # suppress the real reminder on the actual day, and these 8 patients
            # would silently never hear from us. Only a genuine send is 'sent'.
            ledger += [(i, "test" if mailer.OVERRIDE_TO else "sent", None)
                       for i in g["appointment_ids"]]
        except Exception as e:
            # One bad address must not stop the rest of the list. 'failed' rows
            # aren't 'sent', so the next run retries them.
            log.warning("reminder for appointment %s failed: %s", ref, scrub(str(e)))
            failed.append({**summary, "error": str(e)})
            ledger += [(i, "failed", scrub(str(e))) for i in g["appointment_ids"]]

    skipped = [{"name": r.get("name"), "phone": r.get("phone"), "time": r.get("time")}
               for r in unreachable]
    ledger += [(r["appointment_id"], "skipped_no_email", None) for r in unreachable]

    try:
        write_ledger(bq, project, dataset, ledger, day)
    except Exception as e:
        # The sends already happened; losing the ledger means the next run could
        # re-send, so this is loud — but it isn't worth failing the whole job.
        log.error("ledger write failed (sends already made!): %s", e)

    mailer.send_digest(sent, skipped, failed, day, dry_run=dry_run)

    log.info("done: %d sent, %d skipped (no email), %d failed",
             len(sent), len(skipped), len(failed))
    # Only a total wipeout is an error; partial failure is logged and digested.
    if failed and not sent:
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
