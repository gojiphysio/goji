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

-- ---------------------------------------------------------------------------
-- raw_marketing.search_console_raw: append-only landing for Google Search
-- Console performance (searchAnalytics.query). Run once before enabling the
-- `search_console` source.
--
-- One row per (metric_date, dimension, dimension_value). `dimension` is
-- 'total' (one row/day, dimension_value ''), 'query', or 'page' — adding a
-- dimension later (country, device) is more rows, not a schema change.
--
-- NOTE clicks/impressions are additive; **ctr and position are not**. Position
-- is an impression-weighted average, so any window roll-up must compute
-- SUM(position*impressions)/SUM(impressions). marts.fct_search_console_daily
-- does this so callers never hand-roll it.
--
-- Search Console backfills for ~2-3 days, so the job re-pulls a trailing
-- window every run; the latest row per key wins, deduped in stg.search_console
-- via ROW_NUMBER() OVER (... ORDER BY _loaded_at DESC).

CREATE TABLE IF NOT EXISTS `goji-bi.raw_marketing.search_console_raw` (
  _loaded_at TIMESTAMP NOT NULL
    OPTIONS(description = "UTC timestamp this row was loaded into BigQuery"),
  metric_date DATE NOT NULL
    OPTIONS(description = "The Search Console date this row reports on"),
  dimension STRING NOT NULL
    OPTIONS(description = "'total' | 'query' | 'page' — the breakdown this row belongs to"),
  dimension_value STRING
    OPTIONS(description = "The query text or page URL; empty string for dimension='total'"),
  clicks INT64 NOT NULL
    OPTIONS(description = "Clicks from Google Search (additive)"),
  impressions INT64 NOT NULL
    OPTIONS(description = "Impressions in Google Search (additive)"),
  ctr FLOAT64
    OPTIONS(description = "Click-through rate for THIS row only — not additive; recompute as clicks/impressions"),
  position FLOAT64
    OPTIONS(description = "Average position for THIS row only — impression-weighted; never AVG() across rows")
)
PARTITION BY DATE(_loaded_at)
CLUSTER BY dimension, metric_date
OPTIONS(
  description = "Raw landing for Google Search Console performance. Append-only. Dedup to latest happens in stg.search_console."
);
