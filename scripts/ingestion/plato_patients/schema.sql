-- marts.dim_patient: the PII-minimised patient dimension.
--
-- IMPORTANT: this is the ONLY place in the warehouse with anything resembling
-- a patient name. We deliberately store "C. Wong" (first initial + last token
-- of the patient's name in Plato), not the full name. The ingestion job
-- derives this in Python and writes only the derived value — the raw
-- patient name never lands in BigQuery.
--
-- Why a dim table (not raw + stg + dim like invoices): there's no payload to
-- preserve. We extract one PII-safe scalar at ingestion and discard the rest.
-- That keeps the privacy invariant a single function in `main.py`, instead of
-- a SQL view that could be edited to expose more later.

CREATE TABLE IF NOT EXISTS `goji-bi.marts.dim_patient` (
  patient_id STRING NOT NULL
    OPTIONS(description = "Plato patient _id"),
  initial_lastname STRING
    OPTIONS(description = 'PII-safe display name. First-name initial + last token, e.g. "C. Wong". NULL if Plato has no name on file.'),
  _updated_at TIMESTAMP NOT NULL
    OPTIONS(description = "UTC timestamp this row was last refreshed from Plato.")
)
CLUSTER BY patient_id
OPTIONS(
  description = "PII-minimised patient dimension. Source: Plato /patient. Refreshed by the plato-patients-ingest Cloud Run Job."
);
