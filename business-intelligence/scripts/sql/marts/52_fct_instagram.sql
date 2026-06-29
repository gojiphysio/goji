-- marts.fct_instagram
--
-- Thin Instagram-insights fact: one row per (metric_date, metric, period),
-- deduped to the latest load by stg.instagram. The dashboard's fetch_instagram
-- reads this to light the Marketing-tab Instagram cards (reach, profile views,
-- follower growth).
--
-- Grain notes for downstream:
--   - period='day'      : daily series. profile_views is additive (sum over a
--                         range); follower_count is point-in-time (take latest).
--   - period='days_28'  : the de-duplicated trailing-28-day total. Use this for
--                         the headline "reach / month" — never sum daily reach.

CREATE OR REPLACE VIEW `goji-bi.marts.fct_instagram` AS
SELECT
  metric_date,
  metric,
  period,
  value
FROM `goji-bi.stg.instagram`;
