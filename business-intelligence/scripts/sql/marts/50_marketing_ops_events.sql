-- marts.marketing_ops_events  (+ marts.marketing_ops_latest)
--
-- State for the founder dashboard's Marketing tab "operating tools": the
-- weekly-rhythm checklist, the 12-week content-calendar status, the partnership
-- pipeline, and the enquiry log. Append-only event log, exactly like
-- patient_followup_events: every toggle / stage change / enquiry the founder
-- records writes one new row. We never UPDATE or DELETE — the current state of
-- an item is the latest event by updated_at. This sidesteps BigQuery's
-- restrictions on mutating recently-streamed rows and gives us a free history.
--
-- The clinic metrics on the Marketing tab (visits, active patients, bookings,
-- treatment mix, demographics, referrals) all come from the existing read-only
-- marts — nothing about them is written here. This table holds ONLY the
-- operator's own light workflow state, which has no source in Plato.
--
-- item_type / item_key / state:
--   'checklist'    — weekly operating rhythm. item_key is the rhythm slot
--                    ('mon' | 'tuethu' | 'daily' | 'fri' | 'monthly'); state is
--                    'done' | 'todo' for the current ISO week (item_key carries
--                    the week, e.g. 'mon|2026-W24', so a new week starts fresh).
--   'content'      — 12-week content calendar. item_key is the week number
--                    ('1'..'12'); state is 'planned' | 'filmed' | 'published'.
--   'partnership'  — referral pipeline. item_key is a stable partner slug; state
--                    is the stage ('not_started' | 'intro_sent' | 'talking' |
--                    'live' | 'paused'). payload holds the contact / next step.
--   'enquiry'      — enquiry log (the manual bridge while Plato attribution is
--                    limited). item_key is a per-row UUID so every enquiry is
--                    kept; state is the source tag ('whatsapp' | 'call' |
--                    'form' | 'instagram' | 'google' | 'referral' | 'walk_in' |
--                    'other'); payload holds an optional note (no patient PII —
--                    keep it to source + a short context).
--
-- payload: free-text / small JSON the operator types. Operational, not clinical,
-- and never patient PII (name/phone/NRIC). updated_by is the auth username.
--
-- Created as a real table (not a view). CREATE TABLE IF NOT EXISTS is
-- idempotent, so deploy_all.sh can run it repeatedly without clobbering data.

CREATE TABLE IF NOT EXISTS `goji-bi.marts.marketing_ops_events` (
  event_id   STRING    NOT NULL OPTIONS(description="UUID for this event row"),
  item_type  STRING    NOT NULL OPTIONS(description="checklist | content | partnership | enquiry"),
  item_key   STRING    NOT NULL OPTIONS(description="Stable id within item_type (rhythm slot+week, content week, partner slug, or enquiry UUID)"),
  state      STRING    OPTIONS(description="Current state/stage/source-tag for this item (see file header)"),
  payload    STRING    OPTIONS(description="Free-text operational note or small JSON. Never patient PII."),
  updated_by STRING    OPTIONS(description="Auth username of the founder who took the action"),
  updated_at TIMESTAMP NOT NULL OPTIONS(description="When the action was taken")
);

-- Latest event per (item_type, item_key). The Marketing tab reads this to paint
-- the current checklist/calendar/pipeline state and the enquiry log on load.
CREATE OR REPLACE VIEW `goji-bi.marts.marketing_ops_latest` AS
SELECT
  item_type, item_key, state, payload, updated_by, updated_at
FROM (
  SELECT
    *,
    ROW_NUMBER() OVER (PARTITION BY item_type, item_key ORDER BY updated_at DESC) AS _rn
  FROM `goji-bi.marts.marketing_ops_events`
)
WHERE _rn = 1;
