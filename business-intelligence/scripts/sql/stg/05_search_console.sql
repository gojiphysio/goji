-- stg.search_console
--
-- One row per (metric_date, dimension, dimension_value), latest version only,
-- from the append-only raw_marketing.search_console_raw landing table.
--
-- "Latest" = the highest _loaded_at for each key. This matters more here than
-- for Instagram: Search Console backfills for ~2-3 days, so the job re-pulls a
-- trailing window every run and the same (date, query) legitimately arrives
-- several times with different numbers. The last pull is the corrected one.
--
-- Read this view, never read raw_marketing.search_console_raw directly.
--
-- WARNING: `ctr` and `position` are per-row only. Do NOT AVG() them across
-- rows — position is impression-weighted. Use marts.fct_search_console_daily
-- (or copy its weighting) for any window roll-up.

CREATE OR REPLACE VIEW `goji-bi.stg.search_console` AS
WITH latest AS (
  SELECT *
  FROM `goji-bi.raw_marketing.search_console_raw`
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY metric_date, dimension, dimension_value
    ORDER BY _loaded_at DESC
  ) = 1
)
SELECT
  metric_date,
  dimension,
  dimension_value,
  clicks,
  impressions,
  ctr,
  position,
  _loaded_at
FROM latest;
