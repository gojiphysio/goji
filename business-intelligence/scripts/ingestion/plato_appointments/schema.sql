-- raw_plato.appointments_raw: append-only landing table for Plato /appointment payloads.
-- Run once before deploying the ingestion job.
--
-- One row per (appointment_id, _loaded_at). The latest row per appointment_id
-- wins, handled in stg.appointments (which dedupes via ROW_NUMBER() OVER ...).
--
-- Partition by ingestion date keeps load-job pruning effective.
-- Cluster by appointment_id keeps the dedupe-to-latest query cheap.

CREATE TABLE IF NOT EXISTS `goji-bi.raw_plato.appointments_raw` (
  _loaded_at TIMESTAMP NOT NULL
    OPTIONS(description = "UTC timestamp this row was loaded into BigQuery"),
  _source_modified_at TIMESTAMP
    OPTIONS(description = "Plato appointment.last_edited (UTC), parsed from the payload"),
  appointment_id STRING NOT NULL
    OPTIONS(description = "Plato appointment id (payload._id)"),
  appt_date DATE
    OPTIONS(description = "DATE(payload.starttime), top-level for partition pruning convenience"),
  payload JSON NOT NULL
    OPTIONS(description = "Full Plato appointment JSON. Source of truth; stg/marts read fields from here.")
)
PARTITION BY DATE(_loaded_at)
CLUSTER BY appointment_id
OPTIONS(
  description = "Raw landing for Plato /appointment. Append-only. Dedup to latest happens in stg.appointments."
);
