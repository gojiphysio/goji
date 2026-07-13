-- marts.fct_instagram_profile_views
--
-- Thin fact: one row per date carrying that day's Instagram profile views
-- (taps on the profile), pulled daily by the marketing_ingest job.
--
-- Profile views ARE additive across days (unlike reach), so consumers SUM over
-- their window — the "did reach turn into interest?" step of the funnel. The
-- dashboard's fetch_instagram_engagement does SUM(profile_views) for [start,end].

CREATE OR REPLACE VIEW `goji-bi.marts.fct_instagram_profile_views` AS
SELECT
  metric_date,
  value AS profile_views
FROM `goji-bi.stg.instagram`
WHERE metric = 'profile_views';
