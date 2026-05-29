-- stg.invoices
--
-- One row per invoice, latest version only, with the most-used top-level
-- Plato fields surfaced as typed columns. The full JSON payload is kept
-- alongside so downstream can reach into anything we haven't extracted yet.
--
-- "Latest" = the row with the highest _loaded_at for each invoice_id. This
-- is how we collapse the append-only raw layer into a single current state.
--
-- Read this view, never read raw_plato.invoices_raw directly from marts.

CREATE OR REPLACE VIEW `goji-bi.stg.invoices` AS
WITH latest AS (
  SELECT *
  FROM `goji-bi.raw_plato.invoices_raw`
  QUALIFY ROW_NUMBER() OVER (PARTITION BY invoice_id ORDER BY _loaded_at DESC) = 1
)
SELECT
  invoice_id,
  invoice_date,

  -- Foreign keys / categorical
  JSON_VALUE(payload, '$.patient_id')                    AS patient_id,
  JSON_VALUE(payload, '$.location')                      AS location_id,
  JSON_VALUE(payload, '$.doctor')                        AS clinician_id,
  JSON_VALUE(payload, '$.status')                        AS status,
  JSON_VALUE(payload, '$.rate')                          AS tax_code,

  -- Flags (Plato uses 0/1)
  SAFE_CAST(JSON_VALUE(payload, '$.void')      AS INT64) = 1  AS is_void,
  SAFE_CAST(JSON_VALUE(payload, '$.finalized') AS INT64) = 1  AS is_finalized,

  -- Money (invoice-level totals, not line items)
  SAFE_CAST(JSON_VALUE(payload, '$.sub_total') AS NUMERIC)    AS sub_total,
  SAFE_CAST(JSON_VALUE(payload, '$.tax')       AS NUMERIC)    AS tax,
  SAFE_CAST(JSON_VALUE(payload, '$.total')     AS NUMERIC)    AS total,

  -- Timestamps
  SAFE.PARSE_TIMESTAMP('%Y-%m-%d %H:%M:%S',
    JSON_VALUE(payload, '$.finalized_on'))                    AS finalized_at,
  SAFE.PARSE_TIMESTAMP('%Y-%m-%d %H:%M:%S',
    JSON_VALUE(payload, '$.modified_at'))                     AS modified_at,

  -- Full payload retained for downstream JSON access
  payload,

  -- Ingestion metadata
  _loaded_at,
  _source_modified_at
FROM latest;
