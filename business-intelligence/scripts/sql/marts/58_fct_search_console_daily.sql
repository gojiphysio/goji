-- marts.fct_search_console_daily
--
-- Thin fact: one row per date carrying that day's organic Search performance
-- (the `total` dimension only — query/page breakdowns live in
-- marts.fct_search_console_terms).
--
-- clicks and impressions are additive, so a window SUMs them. `position` is
-- **impression-weighted**, so this view carries `position_weight`
-- (position * impressions) alongside impressions: a window's true average
-- position is SUM(position_weight)/SUM(impressions), and CTR is
-- SUM(clicks)/SUM(impressions). Exposing the weight rather than the bare
-- average is what stops a caller reaching for AVG(position) and quietly
-- getting a wrong number on days with uneven impression volume.

CREATE OR REPLACE VIEW `goji-bi.marts.fct_search_console_daily` AS
SELECT
  metric_date,
  clicks,
  impressions,
  position                        AS position_avg,
  position * impressions          AS position_weight
FROM `goji-bi.stg.search_console`
WHERE dimension = 'total';
