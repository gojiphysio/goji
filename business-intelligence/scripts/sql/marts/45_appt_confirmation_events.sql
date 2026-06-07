-- marts.appt_confirmation_events  (+ marts.appt_confirmation_latest)
--
-- Front-desk appointment-confirmation state for the "Call List" tab. Plato has
-- no confirmation field, so we track it ourselves. Append-only event log: every
-- time the front desk confirms an appointment (after the reminder call) one row
-- is written. We never UPDATE or DELETE — the current state of an appointment
-- is its latest event by confirmed_at. Same idiom as patient_followup_events,
-- and it sidesteps BigQuery's restrictions on mutating recently-streamed rows.
--
-- PII boundary: keys on appointment_id only. No patient name or phone is ever
-- written here — the app hydrates those live from marts.dim_patient_contact and
-- never persists them.
--
-- Created as a real table (not a view). CREATE TABLE IF NOT EXISTS is
-- idempotent, so deploy_all.sh can run it repeatedly without clobbering data.

CREATE TABLE IF NOT EXISTS `goji-bi.marts.appt_confirmation_events` (
  event_id       STRING    NOT NULL OPTIONS(description="UUID for this event row"),
  appointment_id STRING    NOT NULL OPTIONS(description="Plato appointment id this confirmation applies to"),
  confirmed_by   STRING    OPTIONS(description="Auth username of the staff member who confirmed"),
  confirmed_at   TIMESTAMP NOT NULL OPTIONS(description="When the appointment was confirmed")
);

-- Latest confirmation per appointment. The Call List LEFT JOINs this: an
-- appointment with a row here is confirmed (and drops off the call list);
-- everything else is still unconfirmed.
CREATE OR REPLACE VIEW `goji-bi.marts.appt_confirmation_latest` AS
SELECT
  appointment_id, confirmed_by, confirmed_at
FROM (
  SELECT
    *,
    ROW_NUMBER() OVER (PARTITION BY appointment_id ORDER BY confirmed_at DESC) AS _rn
  FROM `goji-bi.marts.appt_confirmation_events`
)
WHERE _rn = 1;
