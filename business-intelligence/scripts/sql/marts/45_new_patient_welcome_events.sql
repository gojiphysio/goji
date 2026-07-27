-- marts.new_patient_welcome_events  (+ marts.new_patient_welcome_latest)
--
-- Front-desk "Welcome" worklist state: every time the front desk marks an
-- upcoming new patient as contacted (or skips them), one row is appended.
-- Append-only — we never UPDATE or DELETE; the current state of a booking is
-- the latest event by updated_at. Mirrors patient_followup_events /
-- appt_confirmation_events and sidesteps BigQuery's limits on mutating
-- recently-streamed rows.
--
-- KEYED ON appointment_id, not patient_id: profile-less website/walk-in
-- bookings have no Plato patient_id yet, so the appointment is the only stable
-- id shared by linked and unlinked new patients.
--
-- PII boundary: no name / phone / email is ever written here. The worklist
-- (marts.fct_new_patient_welcome) is hydrated live at render time. `note` is
-- free text the front desk types ("sent directions", "no answer"); keep it
-- operational, not clinical.
--
-- status values:
--   'contacted' — front desk reached out with directions / welcome. Drops the
--                 booking off the worklist.
--   'skipped'   — deliberately not contacting (e.g. handled another way).
--                 Also drops it off.
--   'active'    — re-surface a previously actioned booking (undo).
--
-- CREATE TABLE IF NOT EXISTS is idempotent, so deploy_all.sh can re-run it
-- without clobbering data.

CREATE TABLE IF NOT EXISTS `goji-bi.marts.new_patient_welcome_events` (
  event_id       STRING    NOT NULL OPTIONS(description="UUID for this event row"),
  appointment_id STRING    NOT NULL OPTIONS(description="Plato appointment id this action applies to"),
  status         STRING    NOT NULL OPTIONS(description="contacted | skipped | active"),
  note           STRING    OPTIONS(description="Free-text operational note from the front desk"),
  updated_by     STRING    OPTIONS(description="Auth username of the staff member who took the action"),
  updated_at     TIMESTAMP NOT NULL OPTIONS(description="When the action was taken")
);

-- Latest event per appointment. The welcome fetch LEFT JOINs this to decide who
-- is still to be welcomed (contacted / skipped -> hidden; active or none -> shown).
CREATE OR REPLACE VIEW `goji-bi.marts.new_patient_welcome_latest` AS
SELECT
  appointment_id, status, note, updated_by, updated_at
FROM (
  SELECT
    *,
    ROW_NUMBER() OVER (PARTITION BY appointment_id ORDER BY updated_at DESC) AS _rn
  FROM `goji-bi.marts.new_patient_welcome_events`
)
WHERE _rn = 1;
