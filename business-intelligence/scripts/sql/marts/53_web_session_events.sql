-- marts.web_session_events
--
-- Append-only log of first-party website landings, one row per session_start /
-- page_view / page_engagement fired by the beacon in the Astro site's
-- BaseLayout. This is the
-- TOP of the acquisition funnel: it captures HOW a visitor arrived (utm_*,
-- gclid, fbclid, referer, landing_path) before they ever click a CTA, so "Web"
-- stops being a phantom top-of-funnel source and becomes the owned surface that
-- Ads / Instagram / Google / Direct drive people INTO.
--
-- It also closes the attribution loop the Marketing tab flagged ("no FK from
-- link_click_events … needs a click-id passthrough"): a go.gojiphysio.com/<slug>
-- redirect to the site appends ?cid=<click_id>, which the beacon records here as
-- go_click_id — an exact join back to marts.link_click_events.click_id. And the
-- booking form reuses the same first-party visitor_id, so
--   web_session_events (arrival) -> booking_funnel_events (on-site funnel)
-- join on visitor_id, giving a deterministic origin -> surface -> CTA -> booked
-- chain for the native booking journey.
--
-- A `page_engagement` row is the *exit* counterpart to the arrival rows: fired
-- once per page load when the page is first hidden (tab switch, app switch,
-- back button, close), carrying how long the page was actually VISIBLE
-- (dwell_ms) and how far down it was read (scroll_pct). It exists because
-- arrival rows alone cannot distinguish "landed and bounced in 3 seconds" from
-- "read the whole page for 90 seconds and left" — a distinction that decides
-- whether a landing page fails on load or fails to close (see
-- marketing/ads/measurement-and-optimization.md).
--
-- visitor_id: first-party id (localStorage, long-lived across sessions). No PII.
-- session_id: per-session id (sessionStorage), shared with booking_funnel_events.
-- gclid/fbclid: Google/Meta ad click ids (auto-tagging) for paid-inflow joins to
--   the google_ads transfer / Meta insights. utm_* is the deterministic fallback.
-- go_click_id: the click_id of the originating go-link redirect, if any.
--
-- Written via the streaming insert API (insert_rows_json), NOT DML: pageviews
-- are public and high-frequency, so we dodge BigQuery's 1,500-DML/table/day cap.
-- CREATE TABLE IF NOT EXISTS is idempotent so deploy_all.sh can re-run it.

CREATE TABLE IF NOT EXISTS `goji-bi.marts.web_session_events` (
  event_id     STRING    NOT NULL OPTIONS(description="UUID for this event row"),
  visitor_id   STRING    OPTIONS(description="First-party id (localStorage), stable across sessions. No PII."),
  session_id   STRING    OPTIONS(description="Per-session id (sessionStorage); shared with booking_funnel_events for the on-site join."),
  event_type   STRING    NOT NULL OPTIONS(description="session_start | page_view | page_engagement"),
  utm_source   STRING    OPTIONS(description="utm_source (e.g. google | instagram | gbp | newsletter)"),
  utm_medium   STRING    OPTIONS(description="utm_medium (e.g. cpc | organic | paid | referral)"),
  utm_campaign STRING    OPTIONS(description="utm_campaign — joins to the Google Ads transfer campaign name"),
  utm_content  STRING    OPTIONS(description="utm_content (ad/creative variant)"),
  utm_term     STRING    OPTIONS(description="utm_term (keyword)"),
  gclid        STRING    OPTIONS(description="Google Ads click id (auto-tagging) for paid-inflow joins"),
  fbclid       STRING    OPTIONS(description="Meta click id for paid-inflow joins"),
  referer      STRING    OPTIONS(description="document.referrer at landing. No PII."),
  landing_path STRING    OPTIONS(description="First path the visitor landed on"),
  go_click_id  STRING    OPTIONS(description="click_id of the originating go-link redirect (joins link_click_events.click_id)"),
  occurred_at  TIMESTAMP NOT NULL OPTIONS(description="When the event fired (UTC)"),
  user_agent   STRING    OPTIONS(description="Requesting User-Agent, for later bot filtering. No PII.")
)
PARTITION BY DATE(occurred_at)
CLUSTER BY utm_source;

-- Engagement columns, added idempotently so an already-deployed table gains
-- them without a rebuild (CREATE TABLE IF NOT EXISTS above won't alter an
-- existing table). NULL on session_start / page_view rows — only
-- page_engagement carries them. Safe to re-run.
ALTER TABLE `goji-bi.marts.web_session_events`
  ADD COLUMN IF NOT EXISTS dwell_ms   INT64 OPTIONS(description="Milliseconds the page was VISIBLE before it was first hidden (backgrounded time excluded). page_engagement rows only."),
  ADD COLUMN IF NOT EXISTS scroll_pct INT64 OPTIONS(description="Deepest scroll reached, 0-100. A page shorter than the viewport reports 100 (all of it was on screen). page_engagement rows only.");

-- Keep the event_type description on an already-deployed table in sync with the
-- CREATE above (which only applies to a fresh deploy). Idempotent.
ALTER TABLE `goji-bi.marts.web_session_events`
  ALTER COLUMN event_type SET OPTIONS(description="session_start | page_view | page_engagement");
