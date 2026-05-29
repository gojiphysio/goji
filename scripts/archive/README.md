# Archived one-shot scripts

Discovery and investigation tools from the early exploration phase. None of
these are part of the live ingestion or dashboard pipeline — they're kept for
reference only. Everything they probe is now modelled in BigQuery and served by
the dashboard.

- `plato_probe.py`, `plato_probe2.py` — hit ~20 Plato endpoints and dumped their
  shapes to `probe_output.json` / `probe2_output.json` (gitignored, contain PII).
- `plato_week_metrics.py` — last-7-days bookings + recognised revenue + clinician
  split, computed locally before the warehouse existed.
- `probe_patient_custom_fields.py`, `probe_patient_demographics.py` — explored
  the `patient` payload to confirm demographics/tag fields.
- `investigate_invoice_doctor.py` — first pass at the invoice-doctor mismatch
  problem; the live version is `scripts/cross_reference_invoice_doctor.py` +
  `scripts/fix_invoice_doctor.py` + the `marts.fct_invoice_doctor_mismatches` view.
