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
--   -> confirmed. Unknown stages are still stored (forward-compatible).
-- session_id: opaque per-session id from the browser (sessionStorage UUID). No
--   PII — not linkable to a patient; just for funnel counting.
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
  stage       STRING    NOT NULL OPTIONS(description="Funnel stage: page_view | service_selected | time_selected | details | submitted | confirmed"),
  service     STRING    OPTIONS(description="Selected service id if known (physiotherapy | mummy-baby | clinical-pilates | strength-conditioning)"),
  occurred_at TIMESTAMP NOT NULL OPTIONS(description="When the event fired (UTC)"),
  user_agent  STRING    OPTIONS(description="Requesting User-Agent, for later bot filtering. No PII."),
  referer     STRING    OPTIONS(description="Referring URL if sent. No PII.")
)
PARTITION BY DATE(occurred_at)
CLUSTER BY stage;
