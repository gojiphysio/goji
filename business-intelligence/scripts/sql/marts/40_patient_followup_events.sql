-- marts.patient_followup_events  (+ marts.patient_followup_latest)
--
-- Front-desk follow-up workflow state for the staff admin dashboard's
-- retention worklist. Append-only event log: every "mark contacted / snooze /
-- dismiss" action the front desk takes writes one new row. We never UPDATE or
-- DELETE — the current state of a patient is the latest event by updated_at.
-- This mirrors the stg.appointments "latest version per id" idiom and sidesteps
-- BigQuery's restrictions on mutating recently-streamed rows.
--
-- PII boundary: this table keys on patient_id only. No name, phone, or other
-- identifier is ever written here — the staff dashboard hydrates those live
-- from Plato at render time and never persists them. `note` is free text the
-- staff type ("left voicemail", "moved overseas"); keep it operational, not
-- clinical.
--
-- status values:
--   'contacted' — front desk reached out (re-book nudge). Stays on the list.
--   'snoozed'   — hide until snooze_until passes (e.g. patient said "call me
--                 next month"). snooze_until is required for this status.
--   'dismissed' — remove from the worklist for good. Doubles as our "patient
--                 discharged / not returning" signal, since Plato has no
--                 discharge field.
--   'active'    — re-surface a previously dismissed/snoozed patient (undo).
--
-- Created as a real table (not a view). CREATE TABLE IF NOT EXISTS is
-- idempotent, so deploy_all.sh can run it repeatedly without clobbering data.

CREATE TABLE IF NOT EXISTS `goji-bi.marts.patient_followup_events` (
  event_id     STRING    NOT NULL OPTIONS(description="UUID for this event row"),
  patient_id   STRING    NOT NULL OPTIONS(description="Plato patient id this action applies to"),
  status       STRING    NOT NULL OPTIONS(description="contacted | snoozed | dismissed | active"),
  note         STRING    OPTIONS(description="Free-text operational note from the front desk"),
  snooze_until DATE      OPTIONS(description="For status=snoozed: hide from the worklist until this date"),
  updated_by   STRING    OPTIONS(description="Auth username of the staff member who took the action"),
  updated_at   TIMESTAMP NOT NULL OPTIONS(description="When the action was taken")
);

-- Latest event per patient. The retention fetch LEFT JOINs this to decide who
-- is still actionable (dismissed -> hidden; snoozed & snooze_until in the
-- future -> hidden; everything else -> shown).
CREATE OR REPLACE VIEW `goji-bi.marts.patient_followup_latest` AS
SELECT
  patient_id, status, note, snooze_until, updated_by, updated_at
FROM (
  SELECT
    *,
    ROW_NUMBER() OVER (PARTITION BY patient_id ORDER BY updated_at DESC) AS _rn
  FROM `goji-bi.marts.patient_followup_events`
)
WHERE _rn = 1;
