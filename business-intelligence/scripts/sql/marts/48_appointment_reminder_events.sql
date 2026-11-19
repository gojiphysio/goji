-- marts.appointment_reminder_events  (+ marts.appointment_reminder_latest)
--
-- Send ledger for the daily 48-hour reminder job. One row appended per
-- appointment per attempt. Append-only — we never UPDATE or DELETE; the current
-- state of an appointment is the latest event by sent_at. Mirrors
-- new_patient_welcome_events / patient_followup_events and sidesteps BigQuery's
-- limits on mutating recently-streamed rows.
--
-- THIS IS THE IDEMPOTENCY GUARD, and it is the reason the job is safe to re-run.
-- Before sending, the job LEFT JOINs marts.appointment_reminder_latest and drops
-- anything already 'sent'. So a retry after a partial failure (SMTP died
-- halfway, Cloud Run retried the task) resumes where it stopped instead of
-- mailing the first half of the list a second time.
--
-- CHANNEL: the job reminds by WhatsApp first (when WA_REMINDERS_ENABLED) and
-- email as the fallback. `channel` records which one this row is about, and the
-- guard deliberately ignores it: an appointment 'sent' on either channel is
-- never reminded again. One row per appointment per run, even when WhatsApp
-- failed and email then succeeded (the WhatsApp error goes in `note`): rows in
-- one INSERT share a sent_at, so two rows for one appointment would tie in
-- appointment_reminder_latest.
--   'whatsapp' — the template message (one per appointment). wa_message_id is
--                the wamid Meta returned, which is also the context.id on the
--                patient's Confirm/Reschedule tap.
--   'email'    — the reminder email (one per patient per day, listing all of
--                that day's appointments).
--   'none'     — nothing was attempted (no usable mobile and no email).
--   NULL       — rows written before the channel column existed (all email).
-- A 2xx from the Cloud API means Meta accepted the message, not that it was
-- delivered; delivery failures arrive later on the status webhook.
--
-- KEYED ON appointment_id, not patient_id: profile-less website/walk-in bookings
-- have no Plato patient_id, so the appointment is the only stable id shared by
-- linked and unlinked patients. Note the job sends ONE email per patient per day
-- (grouping same-day appointments together), but writes one ledger row per
-- appointment in that group — so the guard stays correct if the patient's other
-- appointment is later cancelled.
--
-- PII boundary: no name / phone / email is ever written here, same as every
-- other event log. `note` carries an SMTP or WhatsApp error string on failure —
-- keep it operational, and never interpolate an address or phone number into it
-- (the job scrubs both).
--
-- status values:
--   'sent'             — reminder accepted: by the SMTP server (email) or the
--                        Cloud API (whatsapp).
--   'skipped_no_email' — WhatsApp channel off, and no email address on the
--                        appointment or the profile. These feed the daily
--                        digest so the front desk can WhatsApp them by hand.
--   'skipped_no_contact' — WhatsApp channel on, and neither a usable mobile nor
--                        an email. Same digest list.
--   'failed'           — send raised; `note` has the error. NOT treated as sent,
--                        so the next run retries it (until the appointment
--                        falls out of the D+2 window).
--   'test'             — REMINDER_OVERRIDE_TO was set: a real email went out,
--                        but to the override address, not the patient.
--                        Deliberately NOT 'sent' — otherwise an end-to-end test
--                        would suppress the real reminder on the day and those
--                        patients would silently never hear from us.
--   'dry_run'          — DRY_RUN=true: we would have sent. Deliberately a
--                        distinct status so a dry-run row never suppresses the
--                        real send when the flag is flipped.
--
-- CREATE TABLE IF NOT EXISTS is idempotent, so deploy_all.sh can re-run it
-- without clobbering data.

CREATE TABLE IF NOT EXISTS `goji-bi.marts.appointment_reminder_events` (
  event_id       STRING    NOT NULL OPTIONS(description="UUID for this event row"),
  appointment_id STRING    NOT NULL OPTIONS(description="Plato appointment id this reminder applies to"),
  appt_date      DATE      OPTIONS(description="Clinic-local date of the appointment being reminded about"),
  status         STRING    NOT NULL OPTIONS(description="sent | test | skipped_no_email | skipped_no_contact | failed | dry_run"),
  note           STRING    OPTIONS(description="Operational note / SMTP or WhatsApp error text. Never PII"),
  sent_at        TIMESTAMP NOT NULL OPTIONS(description="When the job attempted the send"),
  channel        STRING    OPTIONS(description="whatsapp | email | none. NULL on rows from before the WhatsApp channel (all email)"),
  wa_message_id  STRING    OPTIONS(description="WhatsApp message id (wamid) when channel = whatsapp and Meta accepted it")
);

-- ADDING A COLUMN: CREATE TABLE IF NOT EXISTS is a no-op once the table exists,
-- so the live table only gets new columns through this ALTER. ADD COLUMN IF NOT
-- EXISTS is itself idempotent. It must run before the job's next INSERT, which
-- names these columns; deploy-dashboard.yml runs the SQL step before the job
-- deploy.
ALTER TABLE `goji-bi.marts.appointment_reminder_events`
  ADD COLUMN IF NOT EXISTS channel STRING
    OPTIONS(description="whatsapp | email | none. NULL on rows from before the WhatsApp channel (all email)"),
  ADD COLUMN IF NOT EXISTS wa_message_id STRING
    OPTIONS(description="WhatsApp message id (wamid) when channel = whatsapp and Meta accepted it");

-- Latest event per appointment. The job LEFT JOINs this to decide who still
-- needs a reminder ('sent' -> suppressed; anything else or no row -> send).
CREATE OR REPLACE VIEW `goji-bi.marts.appointment_reminder_latest` AS
SELECT
  appointment_id, appt_date, status, note, sent_at, channel, wa_message_id
FROM (
  SELECT
    *,
    ROW_NUMBER() OVER (PARTITION BY appointment_id ORDER BY sent_at DESC) AS _rn
  FROM `goji-bi.marts.appointment_reminder_events`
)
WHERE _rn = 1;
