-- raw_instagram.insights_raw: append-only landing for Instagram Graph API
-- account insights. Run once before deploying the ingestion job (the dataset
-- raw_instagram must exist first: `bq mk --location=<loc> raw_instagram`).
--
-- One row per (metric, metric_date, period, _loaded_at). The latest load per
-- (metric, metric_date, period) wins — handled in stg.instagram via
-- ROW_NUMBER() OVER (... ORDER BY _loaded_at DESC). Metric-as-row, so adding a
-- metric later is more rows, not a schema change.
--
-- Partition by ingestion date keeps load-job pruning effective.
-- Cluster by metric keeps the dedupe-to-latest query cheap.

CREATE TABLE IF NOT EXISTS `goji-bi.raw_instagram.insights_raw` (
  _loaded_at  TIMESTAMP NOT NULL
    OPTIONS(description = "UTC timestamp this row was loaded into BigQuery"),
  ig_user_id  STRING NOT NULL
    OPTIONS(description = "Instagram Business account id the metric belongs to"),
  metric      STRING NOT NULL
    OPTIONS(description = "reach | profile_views | follower_count | ..."),
  metric_date DATE NOT NULL
    OPTIONS(description = "The day (period=day) or window end (period=days_28) the value covers"),
  period      STRING NOT NULL
    OPTIONS(description = "Graph API period: day | days_28"),
  value       INT64 NOT NULL
    OPTIONS(description = "The metric value"),
  payload     JSON
    OPTIONS(description = "Raw Graph API value/total_value object for this metric+date")
)
PARTITION BY DATE(_loaded_at)
CLUSTER BY metric
OPTIONS(
  description = "Raw landing for Instagram Graph API insights. Append-only. Dedup to latest happens in stg.instagram."
);
