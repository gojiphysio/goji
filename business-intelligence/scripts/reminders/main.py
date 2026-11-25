#!/usr/bin/env python3
"""
Cloud Run Job: send 48-hour appointment reminders, by WhatsApp or email.

Runs daily at 12:00 SGT (Cloud Scheduler, --time-zone Asia/Singapore) and
reminds every patient whose appointment is two calendar days out — Monday's run
covers Wednesday. Replaces a manual chore: Plato's reminder template can only be
fired by hand from its UI (its API has no notification endpoint), so someone had
to log in every day and click it.

Not an ingestion job — it reads marts and sends messages, writing nothing but its
own send ledger. Hence scripts/reminders/ rather than scripts/ingestion/.

FLOW
  1. Read marts.fct_appointment_reminders (D+2, PII-free), hydrating name/email/
     phone at query time from the appointment payload and dim_patient_contact —
     the same hydration join fetch_new_patient_welcome uses in dashboard/app.py.
     Anything already 'sent' in the ledger (on either channel) is suppressed in
     SQL. The D+2 window lives in the view's WHERE clause and nowhere else.
  2. WhatsApp (only when WA_REMINDERS_ENABLED): every appointment whose
     phone normalises to a WhatsApp number gets the approved template, ONE
     MESSAGE PER APPOINTMENT (a template holds one date/time), in time order,
     except one already confirmed in Plato whose patient has an email (the
     template asks them to confirm). See reminder_whatsapp.py.
  3. Email for everyone with an address, in parallel with WhatsApp (clinic
     decision, 25 Nov 2026). Grouped by recipient email: ONE email per patient per day, listing
     every session they have that day — a home visit is three Plato appointments
     (travel/visit/travel), and back-to-back bookings (physio then Pilates)
     shouldn't produce two emails. With WhatsApp off this is the whole job, and
     it behaves exactly as it did before WhatsApp existed.
  4. Each send is wrapped in try/except, so one bad address or number can't take
     down the run — same best-effort posture as booking/mailer.py.
  5. Append ONE ledger row per appointment_id per run (not per message), with
     the channel used and the WhatsApp message id, so the idempotency guard
     stays correct if one of a patient's sessions is later cancelled.
  6. Email the clinic a digest: who was reminded and on which channel, and — the
     part that matters — who got neither and needs contacting by hand.

SAFETY
  Independent guards, and they compose:
    DRY_RUN=true            -> nothing is sent to anyone but the digest, on
                               either channel. Template params are rendered and
                               the first one previewed in the digest.
    WA_REMINDERS_ENABLED    -> off by default. Off = the email-only job, exactly.
    REMINDER_OVERRIDE_TO=x  -> reminder emails are really sent, but every one
                               goes to x. WhatsApp is skipped in this mode unless
                               WA_REMINDER_OVERRIDE_TO is set too.
    WA_REMINDER_OVERRIDE_TO -> every WhatsApp goes to this number instead. Only
                               allowed together with REMINDER_OVERRIDE_TO, so a
                               WhatsApp test can never email a patient.
  DRY_RUN=true writes 'dry_run' ledger rows (a distinct status, so it never
  suppresses the real send) and still delivers the digest. This is how the job
  ships; flip the flag only once the front desk has stopped clicking the button
  in Plato, or patients get two reminders.

Env vars:
  BQ_PROJECT            BigQuery project            default: goji-bi
  BQ_DATASET            Marts dataset               default: marts
  DRY_RUN               'true' => send nothing      default: true
  REMINDER_OVERRIDE_TO  test mode: send every patient reminder email HERE
                        instead of to the patient. Ledgered as 'test', so it
                        never suppresses the real reminder.
  GMAIL_APP_PASSWORD    SMTP app password           (required unless DRY_RUN)
  REMINDER_ADMIN_EMAIL  Digest recipient            default: hello@gojiphysio.com
  WA_REMINDERS_ENABLED  '1' => WhatsApp first       default: off
  WA_API_BASE           Cloud API base URL          default: https://graph.facebook.com/v23.0
  WA_PHONE_NUMBER_ID    Sending number's id         (required for WhatsApp)
  WA_TOKEN              Cloud API token, Secret Manager wa-token (required for WhatsApp)
  WA_SEND_PATH          Send path under WA_API_BASE  default: /{phone_number_id}/messages
  WA_AUTH_HEADER        Header that carries WA_TOKEN default: Authorization
  WA_AUTH_PREFIX        Prefix before WA_TOKEN       default: 'Bearer ' (set empty for a raw key)
  WA_REMINDER_TEMPLATE  Approved template name      default: goji_appointment_reminder
  WA_REMINDER_OVERRIDE_TO  test mode for WhatsApp (see SAFETY)
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

import registration
import reminder_mailer as mailer
import reminder_whatsapp as wa

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
# 8-15 digits, optionally '+'-led and split by single spaces or dashes: a phone
# number. Meta error details can echo the recipient back.
_PHONE_RE = re.compile(r"\+?\d(?:[ -]?\d){7,14}")


def scrub(text: str | None, limit: int = 400) -> str | None:
    """Strip email addresses out of an error before it reaches the ledger.

    The event log is PII-free by design (see marts/48_appointment_reminder_events.sql)
    and the likeliest send failure is smtplib.SMTPRecipientsRefused, whose str()
    is a dict keyed on the patient's address — so writing str(e) raw would put an
    address in the warehouse. The status and the appointment_id are enough to act
    on; the address is recoverable from Plato. Phone numbers are stripped the
    same way, for WhatsApp errors.
    """
    if not text:
        return None
    return _PHONE_RE.sub("[phone]", _EMAIL_RE.sub("[email]", text))[:limit]


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
            "confirm": [],   # (time, appointment_id): one Confirm link per session
            "confirmed": False,  # at least one session already confirmed in Plato
            "form_url": None,    # Plato's registration form, if they still owe it
            "has_clinic": False,
            "has_home_visit": False,
        })
        g["appointment_ids"].append(r["appointment_id"])
        if r.get("form_url") and not g["form_url"]:
            g["form_url"] = r["form_url"]
        if r.get("confirmed"):
            g["confirmed"] = True
        else:
            g["confirm"].append((r.get("time") or "", r["appointment_id"]))
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
        g["confirm"].sort()
    # Stable, human order: earliest session first.
    ordered = sorted(groups.values(), key=lambda g: g["times"][0] if g["times"] else "")
    return ordered, unreachable


# --- BigQuery --------------------------------------------------------------

RECIPIENTS_SQL = """
WITH due AS (
SELECT
  r.appointment_id,
  r.appt_date,
  r.appt_time_sgt                       AS time,
  r.is_home_visit,
  r.treatment_type,
  r.clinician_id,
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
           NULLIF(TRIM(c.phone), ''))                           AS phone,
  -- Already confirmed in Plato (code_Right 'qK8x' = "Confirmed": the patient's
  -- Confirm link, a WhatsApp Confirm tap, or staff). No Confirm ask then.
  COALESCE(JSON_VALUE(a.payload, '$.code_Right'), '') = 'qK8x'  AS confirmed,
  r.patient_id,
  -- For matching a profile-less booking to an existing profile (below).
  RIGHT(REGEXP_REPLACE(COALESCE(JSON_VALUE(a.payload, '$.handphone'), ''), r'\\D', ''), 8)
                                                                AS appt_phone8,
  LOWER(COALESCE(JSON_VALUE(a.payload, '$.email'), ''))         AS appt_email
FROM `{project}.{dataset}.fct_appointment_reminders` r
LEFT JOIN `{project}.stg.appointments`                a USING (appointment_id)
LEFT JOIN `{project}.{dataset}.dim_patient_contact`   c ON r.patient_id = c.patient_id
LEFT JOIN `{project}.{dataset}.appointment_reminder_latest` e USING (appointment_id)
-- Idempotency guard: never re-send. 'sent' on EITHER channel suppresses (the
-- guard keys on status only, never on channel). 'failed' and 'dry_run' fall
-- through on purpose so a failure retries next run and a dry run doesn't block
-- go-live.
WHERE COALESCE(e.status, '') != 'sent'
),
-- A profile-less booking by a returning patient (website, before staff link
-- the appointment): their profile, matched by phone or email. Several
-- matches: prefer one that has signed.
matched AS (
  SELECT due.appointment_id,
         ARRAY_AGG(m.patient_id ORDER BY d.consent_signed_at IS NULL, m.patient_id
                   LIMIT 1)[SAFE_OFFSET(0)] AS patient_id
  FROM due
  JOIN `{project}.{dataset}.dim_patient_contact` m
    ON due.patient_id IS NULL
   AND ((due.appt_phone8 != ''
         AND RIGHT(REGEXP_REPLACE(COALESCE(m.phone, ''), r'\\D', ''), 8) = due.appt_phone8)
        OR (due.appt_email != '' AND LOWER(m.email) = due.appt_email))
  LEFT JOIN `{project}.{dataset}.dim_patient` d ON d.patient_id = m.patient_id
  GROUP BY due.appointment_id
)
SELECT
  due.* EXCEPT (appt_phone8, appt_email),
  -- The patient's Plato profile: the one on the appointment, else the match.
  COALESCE(due.patient_id, matched.patient_id)                   AS profile_id,
  -- The registration-form flag: the profile carries a signed "Clinic Consent
  -- Form", the last step of Plato's registration form (dim_patient, from last
  -- night's import). registration.py rechecks Plato live before asking.
  COALESCE(d.consent_signed_at IS NOT NULL, FALSE)               AS consent_signed
FROM due
LEFT JOIN matched USING (appointment_id)
LEFT JOIN `{project}.{dataset}.dim_patient` d
  ON d.patient_id = COALESCE(due.patient_id, matched.patient_id)
ORDER BY due.time
"""


def fetch_recipients(bq: bigquery.Client, project: str, dataset: str) -> list[dict]:
    sql = RECIPIENTS_SQL.format(project=project, dataset=dataset)
    return [dict(r) for r in bq.query(sql).result()]


def ledger_entry(appointment_id: str, status: str, channel: str, *,
                 note: str | None = None,
                 wa_message_id: str | None = None) -> dict:
    """One ledger row. channel: 'whatsapp' | 'email' | 'none' (nothing tried)."""
    return {"appointment_id": appointment_id, "status": status, "note": note,
            "channel": channel, "wa_message_id": wa_message_id}


def write_ledger(bq: bigquery.Client, project: str, dataset: str,
                 entries: list[dict], appt_date: str) -> None:
    """Append one row per appointment (see ledger_entry for the shape).

    Parameterised DML INSERT (a query job), not streaming — the house pattern for
    every event log here (see record_welcome_contacted in dashboard/app.py). It
    honours the SA's table-level dataEditor grant and avoids BigQuery's limits on
    mutating recently-streamed rows. Daily volume is tens of rows, so one
    multi-row INSERT is plenty.

    Every row in one INSERT gets the same CURRENT_TIMESTAMP(), so an appointment
    must appear at most once per run: two rows would tie on sent_at and
    appointment_reminder_latest could pick either. dispatch() guarantees it.
    """
    if not entries:
        return
    values, params = [], [
        bigquery.ScalarQueryParameter("appt_date", "DATE", appt_date),
    ]
    for i, e in enumerate(entries):
        values.append(f"(@e{i}, @a{i}, @appt_date, @s{i}, @n{i}, @c{i}, @w{i}, "
                      "CURRENT_TIMESTAMP())")
        params += [
            bigquery.ScalarQueryParameter(f"e{i}", "STRING", str(uuid.uuid4())),
            bigquery.ScalarQueryParameter(f"a{i}", "STRING", e["appointment_id"]),
            bigquery.ScalarQueryParameter(f"s{i}", "STRING", e["status"]),
            bigquery.ScalarQueryParameter(f"n{i}", "STRING", e["note"]),
            bigquery.ScalarQueryParameter(f"c{i}", "STRING", e["channel"]),
            bigquery.ScalarQueryParameter(f"w{i}", "STRING", e["wa_message_id"]),
        ]
    sql = (f"INSERT INTO `{project}.{dataset}.appointment_reminder_events`\n"
           "  (event_id, appointment_id, appt_date, status, note, channel, "
           "wa_message_id, sent_at)\n"
           "VALUES\n  " + ",\n  ".join(values))
    bq.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()


# --- dispatch (channel choice; unit-tested with fake senders) --------------

def dispatch(rows: list[dict], day: str, *, dry_run: bool, wa_enabled: bool,
             send_whatsapp, send_email, test_mode: bool = False) -> dict:
    """Send each appointment's reminder on every channel it has, and say what
    to ledger/digest.

    send_whatsapp(to, params, appointment_id) -> wamid, raises on failure.
    send_email(group, day) -> None, raises on failure.

    The channels run in parallel (clinic decision, 25 Nov 2026):
      - EMAIL goes to everyone with an address, confirmed or not, grouped one
        email per patient per day. A confirmed session gets no Confirm button.
      - WHATSAPP (wa_enabled only) goes to every appointment with a usable
        mobile, one message per appointment in time order, EXCEPT an
        appointment already confirmed in Plato whose patient has an email: the
        template's first button asks them to confirm, and the clinic doesn't
        want to keep asking. With no email, WhatsApp is their only reminder,
        so it still goes.

    Returns {"ledger", "sent", "skipped", "failed", "preview"}; the ledger holds
    exactly one entry per appointment: 'sent' when any channel got through,
    channel 'both' | 'whatsapp' | 'email' | 'none', and the other channel's
    error in `note`.
    """
    ok_status = "test" if test_mode else "sent"
    sent: list[dict] = []
    failed: list[dict] = []
    skipped: list[dict] = []
    preview: str | None = None
    wa_ok: dict[str, str | None] = {}   # appointment_id -> wamid (None in a dry run)
    wa_error: dict[str, str] = {}       # appointment_id -> why WhatsApp failed
    email_ok: set[str] = set()
    email_error: dict[str, str] = {}

    for r in sorted(rows, key=lambda r: r.get("time") or ""):
        to = wa.normalise_phone(r.get("phone")) if wa_enabled else None
        if not to or (r.get("confirmed") and (r.get("email") or "").strip()):
            continue
        ref = r["appointment_id"]
        params = wa.template_params(r, day)
        summary = {"name": r.get("name"), "time": r.get("time"),
                   "channel": "whatsapp",
                   "detail": f"{params[1]} with {params[3]}, {params[2]}"}
        if dry_run:
            # Log keys on appointment_id only; the rendered text, which names
            # the patient, goes to the digest.
            log.info("DRY RUN would WhatsApp appointment %s", ref)
            preview = preview or wa.render_preview(params)
            sent.append(summary)
            wa_ok[ref] = None
            continue
        try:
            wa_ok[ref] = send_whatsapp(to, params, ref)
            sent.append(summary)
        except Exception as e:
            log.warning("whatsapp for appointment %s failed: %s", ref, scrub(str(e)))
            wa_error[ref] = scrub(str(e)) or "unknown error"

    groups, unreachable = group_by_recipient(rows)
    for g in groups:
        # Log lines key on appointment_id, never on the recipient address.
        # Cloud Logging is a different surface from BigQuery but the same PII
        # boundary applies: it's retained ~30 days and readable by anyone with a
        # logging role. The appointment_id is enough to trace a send, and the
        # digest to hello@ carries the human-readable list.
        ids = g["appointment_ids"]
        ref = ids[0]
        summary = {"name": g["name"], "time": g["times"][0] if g["times"] else "",
                   "email": g["email"], "channel": "email"}
        if dry_run:
            log.info("DRY RUN would send to appointment %s (%d appt)", ref, len(ids))
            sent.append(summary)
            email_ok.update(ids)
            continue
        try:
            send_email(g, day)
            sent.append(summary)
            email_ok.update(ids)
        except Exception as e:
            # One bad address must not stop the rest of the list.
            log.warning("reminder for appointment %s failed: %s", ref, scrub(str(e)))
            failed.append({**summary, "error": str(e)})
            for i in ids:
                email_error[i] = scrub(str(e)) or "unknown error"

    ledger: list[dict] = []
    status_ok = "dry_run" if dry_run else ok_status
    for r in rows:
        i = r["appointment_id"]
        by_wa, by_email = i in wa_ok, i in email_ok
        notes = ([f"whatsapp failed: {wa_error[i]}"] if i in wa_error else []) + \
                ([f"email failed: {email_error[i]}"] if i in email_error else [])
        note = scrub("; ".join(notes)) if notes else None
        if by_wa or by_email:
            channel = "both" if by_wa and by_email else ("whatsapp" if by_wa else "email")
            # TEST MODE writes 'test', never 'sent' — otherwise a test run would
            # suppress the real reminder on the actual day.
            ledger.append(ledger_entry(i, status_ok, channel, note=note,
                                       wa_message_id=wa_ok.get(i)))
        elif i in wa_error or i in email_error:
            # Nothing got through: 'failed' (not skipped) so a re-run retries.
            ledger.append(ledger_entry(i, "failed", "email" if i in email_error else "whatsapp",
                                       note=note))
        else:
            ledger.append(ledger_entry(
                i, "skipped_no_contact" if wa_enabled else "skipped_no_email", "none"))

    for r in unreachable:
        i = r["appointment_id"]
        if i in wa_ok:
            continue  # no email, but WhatsApp reached them
        entry = {"name": r.get("name"), "phone": r.get("phone"), "time": r.get("time")}
        if i in wa_error:
            entry["reason"] = f"WhatsApp failed: {wa_error[i]}"
        skipped.append(entry)

    return {"ledger": ledger, "sent": sent, "skipped": skipped,
            "failed": failed, "preview": preview}


def whatsapp_config(enabled: bool, *, dry_run: bool) -> tuple[bool, list[str], str | None]:
    """(whatsapp on for this run?, digest notices, config error or None).

    A missing token or number id turns WhatsApp off for the run and says so in
    the digest, rather than failing the job: everyone still gets an email.
    """
    if not enabled:
        return False, [], None
    if wa.OVERRIDE_TO_RAW and not wa.OVERRIDE_TO:
        return False, [], "WA_REMINDER_OVERRIDE_TO is not a usable WhatsApp number"
    if wa.OVERRIDE_TO and not mailer.OVERRIDE_TO:
        return False, [], ("WA_REMINDER_OVERRIDE_TO needs REMINDER_OVERRIDE_TO too, "
                           "so a WhatsApp test can't email patients")
    notices: list[str] = []
    if mailer.OVERRIDE_TO and not wa.OVERRIDE_TO:
        return False, ["Test mode: WhatsApp was skipped because "
                       "WA_REMINDER_OVERRIDE_TO is unset. Everyone went by email."], None
    if not dry_run and not (wa.WA_TOKEN and (wa.WA_PHONE_NUMBER_ID
                                             or not wa.needs_phone_number_id())):
        return False, ["WhatsApp reminders are enabled but WA_TOKEN or "
                       "WA_PHONE_NUMBER_ID is missing, so everyone went by "
                       "email. Fix the job config."], None
    if wa.OVERRIDE_TO:
        notices.append(f"Test mode: every WhatsApp went to +{wa.OVERRIDE_TO}, "
                       "not the patient.")
    return True, notices, None


# --- entrypoint ------------------------------------------------------------

def main() -> int:
    project = env("BQ_PROJECT", "goji-bi")
    dataset = env("BQ_DATASET", "marts")
    # Defaults to TRUE: a misconfigured deploy must never surprise-mail patients.
    dry_run = env_bool("DRY_RUN", True)
    # Defaults to OFF: merging the WhatsApp channel changes nothing until go-live.
    wa_requested = env_bool("WA_REMINDERS_ENABLED", False)

    if not dry_run and not mailer.SMTP_PASS:
        log.error("DRY_RUN is false but GMAIL_APP_PASSWORD is unset; refusing to run")
        return 1
    wa_on, notices, wa_err = whatsapp_config(wa_requested, dry_run=dry_run)
    if wa_err:
        log.error("%s; refusing to run", wa_err)
        return 1
    for n in notices:
        log.warning(n)

    try:
        bq = bigquery.Client(project=project)
        rows = fetch_recipients(bq, project, dataset)
        # Who still owes the registration form (a Plato read each; skipped
        # without a Plato key, and in a dry run nothing is sent anyway).
        registration.attach(rows, registration.Plato() if registration.PLATO_API_KEY else None)
    except Exception as e:
        log.error("BigQuery read failed: %s", e)
        return 2

    # Read the date off the rows, never recompute it — see resolve_appt_date.
    day = resolve_appt_date(rows)
    test_mode = bool(mailer.OVERRIDE_TO)
    if test_mode:
        log.warning("TEST MODE: every reminder email goes to %s, no patient is mailed",
                    mailer.OVERRIDE_TO)
    log.info("reminders for %s (dry_run=%s, test_mode=%s, whatsapp=%s)",
             day, dry_run, test_mode, wa_on)
    log.info("%d appointment(s) due", len(rows))

    def send_email(g: dict, day: str) -> None:
        mailer.send_reminder(
            g["email"], g["name"], day, g["times"],
            has_clinic=g["has_clinic"], has_home_visit=g["has_home_visit"],
            ref=g["appointment_ids"][0],
            confirm_links=[(t, mailer.confirm_url(aid)) for t, aid in g.get("confirm", [])],
            confirmed=g.get("confirmed", False), form_url=g.get("form_url"))

    out = dispatch(rows, day, dry_run=dry_run, wa_enabled=wa_on,
                   send_whatsapp=wa.send_template, send_email=send_email,
                   test_mode=test_mode)

    try:
        write_ledger(bq, project, dataset, out["ledger"], day)
    except Exception as e:
        # The sends already happened; losing the ledger means the next run could
        # re-send, so this is loud — but it isn't worth failing the whole job.
        log.error("ledger write failed (sends already made!): %s", e)

    # The two-channel digest whenever WhatsApp was asked for, even if this run
    # had to fall back, so the notice explaining why is shown.
    mailer.send_digest(out["sent"], out["skipped"], out["failed"], day,
                       dry_run=dry_run, whatsapp=wa_requested,
                       notices=notices, preview=out["preview"])

    sent, skipped, failed = out["sent"], out["skipped"], out["failed"]
    log.info("done: %d sent (%d whatsapp), %d unreachable, %d failed",
             len(sent), sum(1 for s in sent if s["channel"] == "whatsapp"),
             len(skipped), len(failed))
    # Only a total wipeout is an error; partial failure is logged and digested.
    if failed and not sent:
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
