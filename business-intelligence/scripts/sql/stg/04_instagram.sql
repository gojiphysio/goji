-- stg.instagram
--
-- One row per (ig_user_id, metric, metric_date, period), latest load only,
-- from the append-only raw_instagram.insights_raw landing table.
--
-- "Latest" = the row with the highest _loaded_at for that key. This collapses
-- the append-only raw layer into a single current value per metric+date.
--
-- Read this view (or marts.fct_instagram), never raw_instagram.insights_raw
-- directly from marts.
--
-- PREREQUISITE — the `raw_instagram` dataset + `insights_raw` table must exist
-- BEFORE this view deploys (deploy_all.sh runs `set -e`, so a view over a
-- missing table aborts the whole SQL deploy). Create it ONCE, in the SAME
-- location as stg/marts (a cross-region view fails):
--   bq mk --location=<loc> raw_instagram
--   bq query --use_legacy_sql=false < scripts/ingestion/instagram_insights/schema.sql
-- See scripts/dashboard/DEPLOY.md ("Instagram insights").

CREATE OR REPLACE VIEW `goji-bi.stg.instagram` AS
SELECT
  ig_user_id,
  metric,
  metric_date,
  period,
  value,
  _loaded_at
FROM `goji-bi.raw_instagram.insights_raw`
QUALIFY ROW_NUMBER() OVER (
  PARTITION BY ig_user_id, metric, metric_date, period
  ORDER BY _loaded_at DESC
) = 1;
