# Appointment reminders

Cloud Run Job `appointment-reminders`. Emails every patient whose appointment is
**two calendar days out**, once a day at **12:00 SGT**. Monday's run covers
Wednesday.

Replaces a daily manual chore: Plato's reminder template can only be fired by
hand from its UI — the Plato API exposes appointments, webhooks, PlatoPay and
invoices, but **no notification or template endpoint** — so someone had to log in
every day and click it for the sessions ~48h out.

Not an ingestion job (it ingests nothing), hence `scripts/reminders/` rather than
`scripts/ingestion/`. It reads marts, sends email via Gmail SMTP, and writes only
its own send ledger.

## How it works

| | |
|---|---|
| Who gets one | `marts.fct_appointment_reminders` — `appt_date = CURRENT_DATE('Asia/Singapore') + 2`, PII-free |
| Contact | Hydrated at query time: appointment payload first (the front desk typed it for *this* booking), then `marts.dim_patient_contact` (the Plato profile). The profile fallback is what makes this viable — only ~4% of upcoming appointments carry an inline address |
| Never twice | `marts.appointment_reminder_events` / `_latest`. Anything already `sent` is suppressed in SQL |
| Grouping | One email per patient per day, listing every session that day |
| Transport | Gmail SMTP as `hello@gojiphysio.com`, app password from Secret Manager — same path as `scripts/booking/mailer.py` |
| Unreachable | No email on file → skipped, and listed in a digest to `hello@` for the front desk to WhatsApp |

### Why grouping matters

A home visit is **three** Plato appointments (travel / visit / travel), and a
patient can have back-to-back bookings (physio then Pilates). Both would
otherwise produce several emails for one day. The travel legs are already dropped
by the view's qualifier — `booking.py` creates them with no email/phone/type —
but grouping is the belt-and-braces guard.

The ledger still records **one row per appointment**, so the guard stays correct
if one of a patient's sessions is later cancelled.

## ⚠️ The timezone trap

`stg.appointments.start_at` is `PARSE_TIMESTAMP`'d as if UTC, but Plato stores
clinic **wall-clock (SGT)**. The view formats it at `'UTC'` to read the wall clock
straight back out.

**Never convert `start_at` to `Asia/Singapore`.** That shifts every appointment by
8 hours and tells the whole list the wrong time. `dashboard/admin.html`
compensates the same way client-side (`- 8`). `test_reminders.py` pins this.

Selection keys on `appt_date`, which is already a clinic-local DATE — that's what
makes the D+2 window itself immune to the trap.

## Environment

| Var | Default | Notes |
|---|---|---|
| `BQ_PROJECT` | `goji-bi` | |
| `BQ_DATASET` | `marts` | |

The **D+2 window is not configurable** — it lives in the view's `WHERE` clause and
nowhere else. The job reads the date off the returned rows rather than recomputing
it, so SQL and Python can't drift apart and mail someone a date that doesn't match
their appointment. To change the window, change the view.

| `DRY_RUN` | `true` | **Defaults to true** — a misconfigured deploy must never surprise-mail patients |
| `GMAIL_APP_PASSWORD` | — | Secret Manager `gmail-app-password`. Required unless `DRY_RUN` |
| `REMINDER_ADMIN_EMAIL` | `hello@gojiphysio.com` | Digest recipient |

See `reminder_mailer.py` for the `SMTP_*`, subject and link overrides.

Exit codes: `0` ok, `1` config, `2` BigQuery, `3` every send failed. Partial
failure is **not** an error — failed rows aren't `sent`, so the next run retries
them, and the digest reports them.

## Run it

```bash
python -m pytest test_reminders.py -q          # pure functions, no network
```

Deploy is automatic from `main` via `.github/workflows/deploy-dashboard.yml`
(tests gate it). The workflow reads the live `DRY_RUN` back and preserves it, and
deliberately never executes the job — only Cloud Scheduler may.

Manual dry run:

```bash
gcloud run jobs execute appointment-reminders --region asia-southeast1 --wait
```

## Cloud Scheduler (one-off)

```bash
gcloud scheduler jobs create http appointment-reminders-daily \
  --location asia-southeast1 \
  --schedule "0 12 * * *" \
  --time-zone "Asia/Singapore" \
  --uri "https://run.googleapis.com/v2/projects/goji-bi/locations/asia-southeast1/jobs/appointment-reminders:run" \
  --http-method POST \
  --oauth-service-account-email "scheduler-sa@goji-bi.iam.gserviceaccount.com"
```

Runs all 7 days on purpose: Saturday covers Monday, Sunday covers Tuesday, so no
weekend gap.

## Going live — the part that actually bites

**The front desk must stop clicking the reminder button in Plato on the same day
`DRY_RUN` is flipped**, or every patient gets two reminder emails.

The dry-run phase is safe precisely because the manual process keeps running
alongside it — patients keep getting exactly one reminder throughout.

```bash
# 1. Watch the digest for 2-3 days with DRY_RUN=true, checking the would-send
#    list against the Plato calendar for that date. Check the TIMES especially.
# 2. Agree the cutover date and tell the team.
# 3. Confirm the manual sends have stopped, then:
gcloud run jobs update appointment-reminders --region asia-southeast1 \
  --update-env-vars DRY_RUN=false
```

`--update-env-vars`, never `--set-env-vars` — the latter replaces the whole env
block and would silently drop `BQ_PROJECT` with it.

## Identity

Runs as `dashboard-sa@goji-bi.iam.gserviceaccount.com`. It already has marts
read, already holds table-level `dataEditor` on the event logs (the workflow's
grant loop covers `appointment_reminder_events`), and is already the runtime SA
for `goji-booking` — so it already has `secretAccessor` on `gmail-app-password`.
No new identity was needed.

## PDPA

An appointment reminder is a transactional/service message about a booking the
patient made, not marketing — different footing from the nurture-email caution in
`DEPLOY.md` and `dashboard/app.py`. Note the "Front Desk → Contactability" consent
ledger those comments reference does not exist; if outbound *marketing* is ever
added here, that gap needs closing first.

## Related

- `marts/47_fct_appointment_reminders.sql` — recipient view
- `marts/48_appointment_reminder_events.sql` — send ledger
- `scripts/booking/mailer.py` — the SMTP path this borrows
- `marts/44_fct_new_patient_welcome.sql` — where the appointment qualifier, ghost
  guard and PII boundary come from
