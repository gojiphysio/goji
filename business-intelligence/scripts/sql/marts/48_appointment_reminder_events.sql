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
-- KEYED ON appointment_id, not patient_id: profile-less website/walk-in bookings
-- have no Plato patient_id, so the appointment is the only stable id shared by
-- linked and unlinked patients. Note the job sends ONE email per patient per day
-- (grouping same-day appointments together), but writes one ledger row per
-- appointment in that group — so the guard stays correct if the patient's other
-- appointment is later cancelled.
--
-- PII boundary: no name / phone / email is ever written here, same as every
-- other event log. `note` carries an SMTP error string on failure — keep it
-- operational, and never interpolate an address into it.
--
-- status values:
--   'sent'             — reminder email accepted by the SMTP server.
--   'skipped_no_email' — no email address on the appointment or the profile.
--                        These are the rows that feed the daily digest to
--                        hello@ so the front desk can WhatsApp them instead.
--   'failed'           — send raised; `note` has the error. NOT treated as sent,
--                        so the next run retries it (until the appointment
--                        falls out of the D+2 window).
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
  status         STRING    NOT NULL OPTIONS(description="sent | skipped_no_email | failed | dry_run"),
  note           STRING    OPTIONS(description="Operational note / SMTP error text. Never PII"),
  sent_at        TIMESTAMP NOT NULL OPTIONS(description="When the job attempted the send")
);

-- Latest event per appointment. The job LEFT JOINs this to decide who still
-- needs a reminder ('sent' -> suppressed; anything else or no row -> send).
CREATE OR REPLACE VIEW `goji-bi.marts.appointment_reminder_latest` AS
SELECT
  appointment_id, appt_date, status, note, sent_at
FROM (
  SELECT
    *,
    ROW_NUMBER() OVER (PARTITION BY appointment_id ORDER BY sent_at DESC) AS _rn
  FROM `goji-bi.marts.appointment_reminder_events`
)
WHERE _rn = 1;
