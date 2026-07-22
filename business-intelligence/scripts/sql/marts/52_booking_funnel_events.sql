-- marts.booking_funnel_events
--
-- Append-only log of the website booking funnel, one row per stage a visitor
-- reaches on /book. It answers "how far do people get, and where do they drop
-- off?" for the new self-service booking flow (the direct-to-Plato path, as
-- opposed to the click-to-WhatsApp intent tracked in link_click_events).
--
-- The booking service (goji-booking) writes a row when the browser POSTs to
-- /api/track as the visitor advances, plus a server-side 'confirmed' row when a
-- booking actually lands in Plato. The front-end tags every event with a random
-- session_id (per booking session) so drop-off is a distinct-session count per
-- stage.
--
-- stage: page_view -> service_selected -> time_selected -> details -> submitted
--   -> confirmed. Plus "stuck" events that make silent drop-off visible:
--   availability_empty (picked a date with no slots), validation_error (bad
--   phone/email on the form), book_error (submit failed — see `detail` for the
--   code: slot_taken | validation | plato_error). And step-2 behaviour events
--   that make the date/time drop-off legible: date_picked (detail = the date),
--   availability_error (the times fetch failed in the browser; detail = date),
--   clinician_changed (detail = clinician id or "first-available"). Unknown
--   stages are still stored (forward-compatible).
-- session_id: opaque per-session id from the browser (sessionStorage UUID). No
--   PII — not linkable to a patient; just for funnel counting.
-- visitor_id / utm_* / gclid / go_click_id: attribution carried from the landing
--   beacon (marts.web_session_events) so a confirmed booking can be traced back
--   to how the visitor arrived (Ads / Instagram / Google / Direct). Nullable —
--   older rows and non-attributed sessions simply have NULLs. No PII.
-- detail: free-form context for "stuck" events (e.g. the book_error code, or the
--   date that had no availability). NULL for normal stages.
-- service: the selected service id if known at that stage, else NULL.
-- user_agent / referer: low-signal context for later bot filtering. No PII.
--
-- Written via the streaming insert API (insert_rows_json), NOT DML: events are
-- public and potentially high-frequency, so we dodge BigQuery's 1,500
-- DML-statements-per-table-per-day cap. CREATE TABLE IF NOT EXISTS is idempotent
-- so deploy_all.sh can re-run it without clobbering data.

CREATE TABLE IF NOT EXISTS `goji-bi.marts.booking_funnel_events` (
  event_id    STRING    NOT NULL OPTIONS(description="UUID for this event row"),
  session_id  STRING    NOT NULL OPTIONS(description="Per-session id from the browser; distinct-count per stage = funnel. No PII."),
  stage       STRING    NOT NULL OPTIONS(description="Funnel stage: page_view | service_selected | date_picked | time_selected | details | submitted | confirmed | availability_empty | availability_error | validation_error | book_error | clinician_changed"),
  service     STRING    OPTIONS(description="Selected service id if known (physiotherapy | mummy-baby | clinical-pilates | strength-conditioning)"),
  occurred_at TIMESTAMP NOT NULL OPTIONS(description="When the event fired (UTC)"),
  user_agent  STRING    OPTIONS(description="Requesting User-Agent, for later bot filtering. No PII."),
  referer     STRING    OPTIONS(description="Referring URL if sent. No PII.")
)
PARTITION BY DATE(occurred_at)
CLUSTER BY stage;

-- Attribution + stuck-event columns, added idempotently so an already-deployed
-- table gains them without a rebuild (CREATE TABLE IF NOT EXISTS above won't
-- alter an existing table). Safe to re-run.
ALTER TABLE `goji-bi.marts.booking_funnel_events`
  ADD COLUMN IF NOT EXISTS detail       STRING OPTIONS(description="Context for stuck events: book_error code (slot_taken|validation|plato_error) or the no-availability date. NULL for normal stages."),
  ADD COLUMN IF NOT EXISTS visitor_id   STRING OPTIONS(description="First-party visitor id (from the landing beacon), joins web_session_events.visitor_id. No PII."),
  ADD COLUMN IF NOT EXISTS utm_source   STRING OPTIONS(description="Arrival utm_source carried from the landing beacon"),
  ADD COLUMN IF NOT EXISTS utm_campaign STRING OPTIONS(description="Arrival utm_campaign carried from the landing beacon"),
  ADD COLUMN IF NOT EXISTS gclid        STRING OPTIONS(description="Google Ads click id carried from the landing beacon"),
  ADD COLUMN IF NOT EXISTS go_click_id  STRING OPTIONS(description="Originating go-link click_id, joins link_click_events.click_id");
