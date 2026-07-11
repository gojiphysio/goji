-- stg.instagram
--
-- One row per (metric, metric_date), latest version only, from the append-only
-- raw_marketing.instagram_raw landing table.
--
-- "Latest" = the highest _loaded_at for each (metric, metric_date). This
-- collapses re-pulls (the job may re-read the same day) to a single current
-- reading, the same dedup pattern as stg.invoices / stg.appointments.
--
-- Read this view, never read raw_marketing.instagram_raw directly from marts.

CREATE OR REPLACE VIEW `goji-bi.stg.instagram` AS
WITH latest AS (
  SELECT *
  FROM `goji-bi.raw_marketing.instagram_raw`
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY metric, metric_date ORDER BY _loaded_at DESC
  ) = 1
)
SELECT
  metric,
  metric_date,
  value,
  _loaded_at
FROM latest;
