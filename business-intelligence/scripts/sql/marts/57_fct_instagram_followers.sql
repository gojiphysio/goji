-- marts.fct_instagram_followers
--
-- Thin fact: one row per date carrying that day's Instagram follower total
-- (a running snapshot, pulled daily by the marketing_ingest job).
--
-- followers_count is a running TOTAL, not a daily delta, so it is NOT additive:
-- consumers read the LATEST row in their window for the count, and derive growth
-- as (latest - first) across the window — never SUM(followers). The dashboard's
-- fetch_instagram_engagement does exactly that (same read-latest pattern as
-- fct_instagram_reach).

CREATE OR REPLACE VIEW `goji-bi.marts.fct_instagram_followers` AS
SELECT
  metric_date,
  value AS followers
FROM `goji-bi.stg.instagram`
WHERE metric = 'followers_count';
