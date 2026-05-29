-- raw_plato.invoices_raw: append-only landing table for Plato /invoice payloads.
-- Run once before deploying the ingestion job.
--
-- One row per (invoice_id, _loaded_at). The latest row per invoice_id wins,
-- handled in stg.invoices (which dedupes via ROW_NUMBER() OVER ...).
--
-- Partition by ingestion date keeps load-job pruning effective.
-- Cluster by invoice_id keeps the dedupe-to-latest query cheap.

CREATE TABLE IF NOT EXISTS `goji-bi.raw_plato.invoices_raw` (
  _loaded_at TIMESTAMP NOT NULL
    OPTIONS(description = "UTC timestamp this row was loaded into BigQuery"),
  _source_modified_at TIMESTAMP
    OPTIONS(description = "Plato invoice.modified_at (UTC), parsed from the payload"),
  invoice_id STRING NOT NULL
    OPTIONS(description = "Plato invoice id (also queue entry id)"),
  invoice_date DATE
    OPTIONS(description = "Plato invoice.date, top-level, for partition pruning convenience"),
  payload JSON NOT NULL
    OPTIONS(description = "Full Plato invoice JSON. Source of truth; stg/marts read fields from here.")
)
PARTITION BY DATE(_loaded_at)
CLUSTER BY invoice_id
OPTIONS(
  description = "Raw landing for Plato /invoice. Append-only. Dedup to latest happens in stg.invoices."
);
