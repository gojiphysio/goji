-- marts.fct_invoice_doctor_mismatches
--
-- One row per non-void invoice in the last 90 days, with a `status` flag
-- ('match' | 'mismatch' | 'no_appointment') derived by cross-referencing
-- the invoice's recorded doctor against the calendar-color-mapped doctors
-- who saw the same patient on the same day.
--
-- Background: Plato's New Visit form sticky-defaults the doctor field to
-- whoever was last used in the workstation, not the patient's same-day
-- appointment doctor — so PCN/PCL/PKN attribution silently goes wrong. This
-- view powers the dashboard's "invoice-doctor mismatch" alert. Previously the
-- dashboard hit Plato's /appointment endpoint live on every cold cache miss;
-- with stg.appointments in BQ that's no longer needed.
--
-- Downstream: read this from scripts/dashboard/app.py
-- (fetch_invoice_doctor_mismatches). Window-narrow further at read time if
-- you only care about the last N days; the view's own 90d horizon keeps the
-- scan cheap.

CREATE OR REPLACE VIEW `goji-bi.marts.fct_invoice_doctor_mismatches` AS
WITH appts AS (
  SELECT
    patient_id,
    appt_date,
    -- DISTINCT inside ARRAY_AGG: multiple appts for the same patient on the
    -- same day count once. IGNORE NULLS drops calendars we haven't mapped.
    ARRAY_AGG(DISTINCT clinician_id IGNORE NULLS) AS appt_clinician_ids
  FROM `goji-bi.stg.appointments`
  WHERE appt_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
    AND patient_id IS NOT NULL
    AND clinician_id IS NOT NULL
  GROUP BY patient_id, appt_date
),
invoices AS (
  SELECT
    invoice_id,
    invoice_date,
    patient_id,
    clinician_id                                              AS invoice_clinician_id,
    JSON_VALUE(payload, '$.created_by')                       AS created_by,
    JSON_VALUE(payload, '$.last_edited_by')                   AS last_edited_by,
    JSON_VALUE(payload, '$.invoice_prefix')                   AS invoice_prefix,
    SAFE_CAST(JSON_VALUE(payload, '$.invoice') AS INT64)      AS invoice_no,
    total
  FROM `goji-bi.stg.invoices`
  WHERE NOT COALESCE(is_void, FALSE)
    AND invoice_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
    AND patient_id IS NOT NULL
)
SELECT
  i.invoice_id,
  i.invoice_date,
  i.patient_id,
  p.initial_lastname,
  i.invoice_clinician_id,
  a.appt_clinician_ids,
  CASE
    WHEN a.appt_clinician_ids IS NULL                            THEN 'no_appointment'
    WHEN i.invoice_clinician_id IN UNNEST(a.appt_clinician_ids)  THEN 'match'
    ELSE                                                              'mismatch'
  END                                                            AS status,
  CONCAT(COALESCE(i.invoice_prefix, ''), CAST(COALESCE(i.invoice_no, 0) AS STRING)) AS invoice_label,
  i.invoice_prefix,
  i.invoice_no,
  i.created_by,
  i.last_edited_by,
  i.total
FROM invoices i
LEFT JOIN appts a
  ON  i.patient_id   = a.patient_id
  AND i.invoice_date = a.appt_date
LEFT JOIN `goji-bi.marts.dim_patient` p
  ON i.patient_id = p.patient_id;
