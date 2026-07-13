-- marts.link_click_events
--
-- Append-only log of click-to-WhatsApp redirects. WhatsApp is Goji's primary
-- CTA — customers message before they book (high price point; they want to
-- explain symptoms and discuss scheduling first) — so the leading *intent*
-- signal across every channel is a tap to start a WhatsApp chat, not a
-- booking-page visit.
--
-- Every outbound CTA (website button, Instagram bio link, Google Business
-- Profile link, ad destinations, email signature, printed QR codes) points at
-- the dashboard's public GET /r/<slug> route. That route logs one row here and
-- 302-redirects to a wa.me deep link whose prefilled message is channel-
-- specific. The Marketing tab reads counts from this table (total + per-slug
-- split) so cross-channel WhatsApp intent is attributable.
--
-- slug: the channel the click came from (e.g. 'web' | 'ig' | 'gbp' | 'ads' |
--   'email' | 'qr'). The redirect logs whatever slug was hit, including unknown
--   ones, so a mistyped/retired link still shows up rather than vanishing.
-- user_agent / referer: low-signal context kept only for later bot filtering
--   if click counts get noisy. No PII (no IP, no patient identifiers).
-- session_id / page: for ON-SITE CTA taps (web-*), the site appends the visitor's
--   booking session_id and the page path they tapped from (?sid=…&p=…). This is
--   the golden-flow join: a WhatsApp tap can't carry a ?cid passthrough (it's an
--   external wa.me redirect) and cross-origin Referer is trimmed to the origin,
--   so the site passes session_id explicitly. session_id joins
--   booking_funnel_events.session_id / web_session_events.session_id, letting the
--   dashboard tell "reached /book then tapped WhatsApp" from "reached /book then
--   dropped". NULL for off-site channels (ig/gbp/ads/qr) that never touch the site.
--
-- Written via the streaming insert API (insert_rows_json), NOT DML: clicks are
-- public and potentially high-frequency, so we avoid BigQuery's 1,500
-- DML-statements-per-table-per-day cap. Created as a real table; CREATE TABLE
-- IF NOT EXISTS is idempotent so deploy_all.sh can run it repeatedly without
-- clobbering data.

CREATE TABLE IF NOT EXISTS `goji-bi.marts.link_click_events` (
  click_id   STRING    NOT NULL OPTIONS(description="UUID for this click row"),
  slug       STRING    NOT NULL OPTIONS(description="Channel slug the click came from (web | ig | gbp | ads | email | qr | ...)"),
  clicked_at TIMESTAMP NOT NULL OPTIONS(description="When the redirect was hit (UTC)"),
  user_agent STRING    OPTIONS(description="Requesting User-Agent, for later bot filtering. No PII."),
  referer    STRING    OPTIONS(description="Referring URL if sent. No PII.")
)
PARTITION BY DATE(clicked_at)
CLUSTER BY slug;

-- On-site golden-flow attribution columns, added idempotently so an already-
-- deployed table gains them without a rebuild (CREATE TABLE IF NOT EXISTS above
-- won't alter an existing table). Safe to re-run. No PII.
ALTER TABLE `goji-bi.marts.link_click_events`
  ADD COLUMN IF NOT EXISTS session_id STRING OPTIONS(description="On-site booking session_id the tap came from (joins booking_funnel_events / web_session_events). NULL for off-site channels."),
  ADD COLUMN IF NOT EXISTS page       STRING OPTIONS(description="Page path the on-site CTA was tapped from (e.g. /book). NULL for off-site channels.");
