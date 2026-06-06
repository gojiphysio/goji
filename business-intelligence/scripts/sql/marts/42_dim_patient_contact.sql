-- marts.dim_patient_contact
--
-- Patient CONTACT details (full name + mobile) for the staff Front Desk
-- retention worklist. The front desk needs to actually phone patients, so —
-- unlike marts.dim_patient, which is deliberately PII-free — this table holds
-- PII on purpose. It is a scoped, deliberate exception to the "no PII in the
-- warehouse" boundary: read only by the staff worklist path, never surfaced on
-- the financial dashboard.
--
-- Populated by the plato-patients-ingest job (the only code that sees raw Plato
-- names), via WRITE_TRUNCATE alongside dim_patient. This file just creates an
-- empty shell so the dashboard's LEFT JOIN works before the first ingest run.
-- CREATE TABLE IF NOT EXISTS is idempotent — re-running deploy_all.sh never
-- clobbers the rows the ingest job has written.

CREATE TABLE IF NOT EXISTS `goji-bi.marts.dim_patient_contact` (
  patient_id  STRING    NOT NULL OPTIONS(description="Plato patient id — joins to dim_patient / fct_patient_retention"),
  full_name   STRING    OPTIONS(description="Patient's full name, for the front desk to address them"),
  phone       STRING    OPTIONS(description="Best-effort mobile/phone number pulled from the Plato record"),
  _updated_at TIMESTAMP OPTIONS(description="When this row was last refreshed by the ingest job")
);
