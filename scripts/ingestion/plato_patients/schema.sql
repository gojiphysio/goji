-- marts.dim_patient: the PII-minimised patient dimension.
--
-- IMPORTANT: this is the ONLY place in the warehouse with anything resembling
-- a patient name. We deliberately store "C. Wong" (first initial + last token
-- of the patient's name in Plato), not the full name. The ingestion job
-- derives this in Python and writes only the derived value — the raw
-- patient name never lands in BigQuery.
--
-- Same privacy boundary applies to every other column below: the ingest job
-- derives PII-safe scalars in memory (age_band, not DOB; postal_sector, not
-- full postal) and only the derived values reach BQ. Adding a new attribute
-- here means adding a derivation in main.py — never piping a raw Plato field
-- through.
--
-- Why a dim table (not raw + stg + dim like invoices): there's no payload to
-- preserve. We extract PII-safe scalars at ingestion and discard the rest.
-- That keeps the privacy invariant a single function in `main.py`, instead of
-- a SQL view that could be edited to expose more later.

CREATE TABLE IF NOT EXISTS `goji-bi.marts.dim_patient` (
  patient_id STRING NOT NULL
    OPTIONS(description = "Plato patient _id"),
  initial_lastname STRING
    OPTIONS(description = 'PII-safe display name. First-name initial + last token, e.g. "C. Wong". NULL if Plato has no name on file.'),
  age_band STRING
    OPTIONS(description = 'Coarse age bucket derived from DOB at ingest time: "Under 18" / "18-29" / "30-39" / "40-49" / "50-59" / "60+". NULL if DOB is missing or unparseable. Recomputed every refresh so the bucket shifts with the patient'),
  sex STRING
    OPTIONS(description = 'Plato sex field as recorded ("Male" / "Female" / blank). Not derived — passed through.'),
  postal_sector STRING
    OPTIONS(description = "Singapore postal sector: first 2 digits of the patient's postal code. Public geographic unit (covers thousands of addresses), not PII. NULL if no postal on file."),
  tags ARRAY<STRING>
    OPTIONS(description = 'Clinical / segmentation tags applied to the patient in Plato (e.g. "Musculoskeletal", "Post-partum"). Empty array if none.'),
  primary_doctor STRING
    OPTIONS(description = "First entry of the patient's Plato `doctor` array (PCL/PKN/PCN). NULL if unassigned."),
  created_on DATE
    OPTIONS(description = "Date the patient record was first created in Plato. Used for acquisition cohort analysis."),
  referred_by STRING
    OPTIONS(description = "patient_id of the existing patient who referred this one (word-of-mouth graph). NULL when blank — Plato has no field for external sources like Google/Instagram/walk-in."),
  _updated_at TIMESTAMP NOT NULL
    OPTIONS(description = "UTC timestamp this row was last refreshed from Plato.")
)
CLUSTER BY patient_id
OPTIONS(
  description = "PII-minimised patient dimension. Source: Plato /patient. Refreshed by the plato-patients-ingest Cloud Run Job."
);
