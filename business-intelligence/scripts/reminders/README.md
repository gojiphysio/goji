# Appointment reminders

Cloud Run Job `appointment-reminders`. Reminds every patient whose appointment
is **two calendar days out**, once a day at **12:00 SGT**. Monday's run covers
Wednesday. **WhatsApp first** for anyone with a usable mobile, **email** as the
fallback. The WhatsApp channel is **off until `WA_REMINDERS_ENABLED=1`**; off,
the job is the email-only job, unchanged.

Replaces a daily manual chore: Plato's reminder template can only be fired by
hand from its UI — the Plato API exposes appointments, webhooks, PlatoPay and
invoices, but **no notification or template endpoint** — so someone had to log in
every day and click it for the sessions ~48h out.

Not an ingestion job (it ingests nothing), hence `scripts/reminders/` rather than
`scripts/ingestion/`. It reads marts, sends WhatsApp templates via the Cloud API
and email via Gmail SMTP, and writes only its own send ledger.

## How it works

| | |
|---|---|
| Who gets one | `marts.fct_appointment_reminders` — `appt_date = CURRENT_DATE('Asia/Singapore') + 2`, PII-free |
| Contact | Hydrated at query time: appointment payload first (the front desk typed it for *this* booking), then `marts.dim_patient_contact` (the Plato profile). The profile fallback is what makes this viable — only ~4% of upcoming appointments carry an inline address |
| Never twice | `marts.appointment_reminder_events` / `_latest`. Anything already `sent` is suppressed in SQL, **whichever channel sent it** |
| Channel | WhatsApp if `WA_REMINDERS_ENABLED` and the phone normalises to a WhatsApp number; else email. A failed WhatsApp send (non-2xx, error body, network) falls back to email for that appointment. Never both unless WhatsApp failed |
| Grouping | WhatsApp: **one message per appointment** (a template holds one date/time), in time order. Email: one per patient per day, listing every session that day |
| Transport | WhatsApp Cloud API template (`reminder_whatsapp.py`). Gmail SMTP as `hello@gojiphysio.com`, app password from Secret Manager — same path as `scripts/booking/mailer.py` |
| Unreachable | No WhatsApp and no email (or WhatsApp failed and no email) → listed in a digest to `hello@` for the front desk to contact by hand |

### Why grouping matters

A home visit is **three** Plato appointments (travel / visit / travel), and a
patient can have back-to-back bookings (physio then Pilates). Both would
otherwise produce several emails for one day. The travel legs are already dropped
by the view's qualifier — `booking.py` creates them with no email/phone/type —
but grouping is the belt-and-braces guard.

The ledger still records **one row per appointment**, so the guard stays correct
if one of a patient's sessions is later cancelled.

### The WhatsApp template

`goji_appointment_reminder`, language `en`, category UTILITY:

> Hi {{1}}, a reminder of your {{2}} appointment on {{3}} with {{4}} at Goji
> Women's and Family Physiotherapy.
>
> If you need to reschedule, please let us know at least 24 hours before.
>
> [Confirm] [Reschedule]

| Slot | Value | Source |
|---|---|---|
| `{{1}}` | Patient first name, `there` if none | hydrated name |
| `{{2}}` | `physiotherapy`, `Pilates`, `strength and conditioning`, `home visit`; `upcoming` for Untyped/Unknown | `treatment_type` (`SERVICE_WORDS`) |
| `{{3}}` | `Thu 26 Nov, 10:00am` | `appt_date` + `appt_time_sgt`, wall clock as-is |
| `{{4}}` | Clinician first name, `our team` if the calendar isn't mapped | `clinician_id` (`CLINICIAN_FIRST_NAMES`, mirrors `booking/config.py`; a test fails if they drift) |

Each quick-reply button carries a payload, `reminder_confirm:<appointment_id>`
and `reminder_reschedule:<appointment_id>` (button index 0 and 1, matching the
approved order). The webhook returns it as `messages[].button.payload` on a tap,
with `context.id` = the wamid in the ledger, so the assistant can tell which
appointment a tap is about.

Phone normalisation (`normalise_phone`): Singapore 8-digit numbers starting 8 or
9 become `65XXXXXXXX`; a number written with `+`/`00`, or 11-15 bare digits not
starting 65, is kept as international; SG landlines and anything ambiguous get no
WhatsApp and fall to email.

**A 2xx is "accepted", not "delivered".** A number that isn't on WhatsApp fails
later, on the status webhook (error 131026), which this job never sees, so it
does not fall back to email. The digest shows who was sent a WhatsApp, so the
front desk can spot it if a patient says they got nothing.

## ⚠️ The timezone trap

`stg.appointments.start_at` is `PARSE_TIMESTAMP`'d as if UTC, but Plato stores
clinic **wall-clock (SGT)**. The view formats it at `'UTC'` to read the wall clock
straight back out.

**Never convert `start_at` to `Asia/Singapore`.** That shifts every appointment by
8 hours and tells the whole list the wrong time. `dashboard/admin.html`
compensates the same way client-side (`- 8`). `test_reminders.py` pins this, for
both the email and the WhatsApp `{{3}}`.

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
| `REMINDER_OVERRIDE_TO` | unset | Test mode: send every reminder here instead of to the patient. See below |
| `GMAIL_APP_PASSWORD` | — | Secret Manager `gmail-app-password`. Required unless `DRY_RUN` |
| `REMINDER_ADMIN_EMAIL` | `hello@gojiphysio.com` | Digest recipient |
| `WA_REMINDERS_ENABLED` | off | `1` turns the WhatsApp channel on. Off = email-only, exactly as before |
| `WA_API_BASE` | `https://graph.facebook.com/v23.0` | |
| `WA_PHONE_NUMBER_ID` | — | The sending number's id (Meta app > WhatsApp > API Setup). Required for WhatsApp unless `DRY_RUN` |
| `WA_TOKEN` | — | Secret Manager `wa-token`. Required for WhatsApp unless `DRY_RUN` |
| `WA_REMINDER_TEMPLATE` | `goji_appointment_reminder` | Approved template name |
| `WA_REMINDER_LANGUAGE` | `en` | Template language code |
| `WA_REMINDER_OVERRIDE_TO` | unset | Test mode for WhatsApp, see below. Only allowed with `REMINDER_OVERRIDE_TO` |

If WhatsApp is enabled but `WA_TOKEN` or `WA_PHONE_NUMBER_ID` is missing, the run
sends everyone email instead and says so at the top of the digest.

See `reminder_mailer.py` for the `SMTP_*`, subject and link overrides.

Exit codes: `0` ok, `1` config, `2` BigQuery, `3` every send failed. A WhatsApp
failure that email then covered is not a failure at all. Partial failure is
**not** an error — failed rows aren't `sent`, so the next run retries
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

### Ledger

One row per appointment per run, with `channel` (`whatsapp` | `email` | `none`)
and `wa_message_id`. A WhatsApp failure followed by a successful email is one
`sent`/`email` row with the WhatsApp error in `note`. Statuses: `sent`, `test`,
`dry_run`, `failed`, `skipped_no_email` (WhatsApp off, no email) and
`skipped_no_contact` (WhatsApp on, neither channel usable). Notes are scrubbed of
email addresses and phone numbers. See `marts/48_appointment_reminder_events.sql`.

### Digest

With `WA_REMINDERS_ENABLED`, the digest gives counts per channel, each patient's
channel (`[WhatsApp]` with service, clinician and slot, or `[email]`, marked when
WhatsApp failed first), the by-hand list (no WhatsApp and no email, with the
reason when WhatsApp failed), and in a dry run the first WhatsApp as the patient
would read it. With it off, the digest is byte-identical to the email-only one
(pinned by a test).

## Test mode — prove the real send without mailing a patient

`DRY_RUN=true` never sends a patient email, so it can't tell you whether the
reminders themselves go out correctly. `REMINDER_OVERRIDE_TO` closes that gap:
every reminder is really sent — real names, times, grouping, SMTP — but every
one goes to the override address instead of the patient.

```bash
gcloud run jobs update appointment-reminders --region asia-southeast1   --update-env-vars DRY_RUN=false,REMINDER_OVERRIDE_TO=hello@gojiphysio.com

gcloud run jobs execute appointment-reminders --region asia-southeast1 --wait
```

You get one email per recipient, body byte-identical to the patient's, subject
prefixed `[TEST -> their@address]` so you can check each landed on the right
person. **Put it back afterwards:**

```bash
gcloud run jobs update appointment-reminders --region asia-southeast1   --update-env-vars DRY_RUN=true --remove-env-vars REMINDER_OVERRIDE_TO
```

Two properties worth knowing:

- **The override is applied at the point of send**, so there is no code path
  where a patient is mailed while it has a value.
- **Test runs are ledgered `test`, never `sent`.** A `sent` row would suppress
  the real reminder on the day, so testing against a live cohort would silently
  cost those patients their reminder. Only `sent` suppresses; `test`, `dry_run`
  and `failed` all fall through.

**WhatsApp in test mode.** With `REMINDER_OVERRIDE_TO` alone, WhatsApp is
skipped and every reminder goes by email to the override. To prove the WhatsApp
path too, add `WA_REMINDER_OVERRIDE_TO=<your mobile>`: every template goes to that
number, real params and buttons, applied at the point of send. The job refuses to
start with `WA_REMINDER_OVERRIDE_TO` but no `REMINDER_OVERRIDE_TO`, because the
email fallback would then reach real patients. Remove both afterwards.

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

### Turning on WhatsApp

Independent of the `DRY_RUN` cutover above; it can happen before or after.

1. **Template approved on Goji's real number.** In WhatsApp Manager, check
   `goji_appointment_reminder` (`en`) is *Approved* on the WABA that owns the
   production number, with the buttons in the order Confirm, Reschedule. A
   template approved on the test number doesn't carry over.
2. **Teach the deploy workflow the WhatsApp config. Required before step 4.**
   The reminders step in `.github/workflows/deploy-dashboard.yml` redeploys with
   `--set-env-vars` and `--set-secrets`, which *replace* the job's whole env and
   secret blocks. Anything set by hand with `gcloud run jobs update` is wiped on
   the next merge that touches `reminders/`. The step needs to (a) read back and
   preserve `WA_REMINDERS_ENABLED` the way it already preserves `DRY_RUN`, (b)
   pass `WA_PHONE_NUMBER_ID` (a repo variable), and (c) mount the token:
   `--set-secrets=GMAIL_APP_PASSWORD=gmail-app-password:latest,WA_TOKEN=wa-token:latest`.
   Same warning as for `gmail-app-password`: no `gcloud secrets describe` probe.
3. **Let the job's SA read the token.** It runs as `dashboard-sa`, which has no
   access to `wa-token` yet (the assistant runs as its own SA):
   ```bash
   gcloud secrets add-iam-policy-binding wa-token --project goji-bi \
     --member=serviceAccount:dashboard-sa@goji-bi.iam.gserviceaccount.com \
     --role=roles/secretmanager.secretAccessor
   ```
4. **Dry run with WhatsApp on.** Merge the workflow change, then
   `--update-env-vars WA_REMINDERS_ENABLED=1` with `DRY_RUN=true`. The digest now
   shows who would get WhatsApp vs email, and previews the first message. Check
   the slot times against Plato.
5. **Prove one real send to yourself** with both overrides (test mode above).
   Tap Confirm and check the assistant receives the tap.
6. **Go live**: with `DRY_RUN=false`, `WA_REMINDERS_ENABLED=1` is all it takes.
   To turn WhatsApp off again: `--update-env-vars WA_REMINDERS_ENABLED=0`, and
   everyone gets email again on the next run.

## Identity

Runs as `dashboard-sa@goji-bi.iam.gserviceaccount.com`. It already has marts
read, already holds table-level `dataEditor` on the event logs (the workflow's
grant loop covers `appointment_reminder_events`), and is already the runtime SA
for `goji-booking` — so it already has `secretAccessor` on `gmail-app-password`.
No new identity was needed. For WhatsApp it also needs `secretAccessor` on
`wa-token` (go-live step 3).

## PDPA

An appointment reminder is a transactional/service message about a booking the
patient made, not marketing (on WhatsApp too: the template is category UTILITY,
and the booking form tells patients reminders come by WhatsApp) — different
footing from the nurture-email caution in
`DEPLOY.md` and `dashboard/app.py`. Note the "Front Desk → Contactability" consent
ledger those comments reference does not exist; if outbound *marketing* is ever
added here, that gap needs closing first.

## Related

- `marts/47_fct_appointment_reminders.sql` — recipient view
- `marts/48_appointment_reminder_events.sql` — send ledger
- `scripts/booking/mailer.py` — the SMTP path this borrows
- `scripts/wa_agent/` — the WhatsApp assistant that receives the Confirm /
  Reschedule taps (same Cloud API config names)
- `marts/44_fct_new_patient_welcome.sql` — where the appointment qualifier, ghost
  guard and PII boundary come from
