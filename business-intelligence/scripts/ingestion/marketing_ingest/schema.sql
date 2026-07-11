-- raw_marketing.instagram_raw: append-only landing for Instagram account
-- insights pulled from the Meta Graph API. Run once before deploying the job.
--
-- Generic (metric, metric_date, value) shape: adding metrics later (followers,
-- profile views, ...) is more rows, not a schema change (ingestion/AGENTS.md).
-- One row per pull; the latest row per (metric, metric_date) wins, deduped in
-- stg.instagram via ROW_NUMBER() OVER (... ORDER BY _loaded_at DESC).
--
-- NOTE reach is de-duplicated (unique accounts), so it is NOT summable across
-- days. We store Meta's rolling 28-day reach (metric = 'reach_days_28'); the
-- mart/dashboard read the latest reading in-window, they never SUM it.
--
-- The raw_marketing dataset must exist first:
--   bq --location=asia-southeast1 mk --dataset goji-bi:raw_marketing

CREATE TABLE IF NOT EXISTS `goji-bi.raw_marketing.instagram_raw` (
  _loaded_at TIMESTAMP NOT NULL
    OPTIONS(description = "UTC timestamp this row was loaded into BigQuery"),
  metric STRING NOT NULL
    OPTIONS(description = "Metric name, e.g. 'reach_days_28' (rolling 28-day reach)"),
  metric_date DATE NOT NULL
    OPTIONS(description = "The insight's end_time date (the day this reading is as-of)"),
  value INT64 NOT NULL
    OPTIONS(description = "Metric value for (metric, metric_date)"),
  payload JSON
    OPTIONS(description = "Raw Meta Graph insight value object, kept for audit")
)
PARTITION BY DATE(_loaded_at)
CLUSTER BY metric, metric_date
OPTIONS(
  description = "Raw landing for Instagram account insights (Meta Graph API). Append-only. Dedup to latest happens in stg.instagram."
);
