-- marts.fct_search_console_terms
--
-- Thin fact: the per-day query and page breakdowns from Search Console, kept in
-- one view because they share a shape and the dashboard reads them the same way
-- (filter on `dimension`).
--
-- Grain: one row per (metric_date, dimension, term). Roll up over a window with
-- SUM(clicks), SUM(impressions) and SUM(position_weight)/SUM(impressions) —
-- never AVG(position_avg), for the reason spelled out in
-- marts.fct_search_console_daily.
--
-- Note Search Console omits low-volume queries for privacy, so summing the
-- query rows for a day will NOT equal that day's `total` row. That is expected,
-- not a data bug — use fct_search_console_daily for headline numbers and this
-- view only for "what are we ranking for".

CREATE OR REPLACE VIEW `goji-bi.marts.fct_search_console_terms` AS
SELECT
  metric_date,
  dimension,                                  -- 'query' | 'page'
  dimension_value                 AS term,
  clicks,
  impressions,
  position                        AS position_avg,
  position * impressions          AS position_weight
FROM `goji-bi.stg.search_console`
WHERE dimension IN ('query', 'page');
