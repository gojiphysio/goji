-- stg.appointments
--
-- One row per appointment, latest version only, with the most-used top-level
-- Plato fields surfaced as typed columns. The full JSON payload is kept
-- alongside so downstream can reach into anything we haven't extracted yet.
--
-- "Latest" = the row with the highest _loaded_at for each appointment_id.
-- This is how we collapse the append-only raw layer into a single current
-- state.
--
-- Read this view, never read raw_plato.appointments_raw directly from marts.

CREATE OR REPLACE VIEW `goji-bi.stg.appointments` AS
WITH latest AS (
  SELECT *
  FROM `goji-bi.raw_plato.appointments_raw`
  QUALIFY ROW_NUMBER() OVER (PARTITION BY appointment_id ORDER BY _loaded_at DESC) = 1
)
SELECT
  appointment_id,
  appt_date,

  -- Foreign keys / categorical
  JSON_VALUE(payload, '$.patient_id')                       AS patient_id,
  JSON_VALUE(payload, '$.color')                            AS calendar_color,
  -- Plato's `doctor` field on appointments is usually blank — the clinician
  -- is encoded via calendar color. We resolve via fixed mapping below.
  JSON_VALUE(payload, '$.doctor')                           AS doctor_raw,
  CASE JSON_VALUE(payload, '$.color')
    -- Stable mapping at Goji Health, recorded in MEMORY.md
    -- (reference-plato-provider-codes). Update here if a clinician joins or
    -- leaves and a new calendar is created.
    WHEN 'blue'  THEN 'PCL'  -- Cheryl Long (director)
    WHEN 'green' THEN 'PKN'  -- Kristy Ng
    WHEN '6hpO'  THEN 'PCN'  -- Claire Ng
    ELSE NULL
  END                                                       AS clinician_id,

  -- Times (Plato stores naive "YYYY-MM-DD HH:MM:SS"; treat as UTC like the
  -- rest of the Plato data we ingest).
  SAFE.PARSE_TIMESTAMP('%Y-%m-%d %H:%M:%S',
    JSON_VALUE(payload, '$.starttime'))                     AS start_at,
  SAFE.PARSE_TIMESTAMP('%Y-%m-%d %H:%M:%S',
    JSON_VALUE(payload, '$.endtime'))                       AS end_at,

  -- Audit trail
  JSON_VALUE(payload, '$.created_by')                       AS created_by,
  JSON_VALUE(payload, '$.last_edited_by')                   AS last_edited_by,
  SAFE.PARSE_TIMESTAMP('%Y-%m-%d %H:%M:%S',
    JSON_VALUE(payload, '$.created_on'))                    AS created_on,
  SAFE.PARSE_TIMESTAMP('%Y-%m-%d %H:%M:%S',
    JSON_VALUE(payload, '$.last_edited'))                   AS last_edited,

  -- Free text + payload for downstream JSON access
  JSON_VALUE(payload, '$.title')                            AS title,
  payload,

  -- Ingestion metadata
  _loaded_at,
  _source_modified_at
FROM latest;
