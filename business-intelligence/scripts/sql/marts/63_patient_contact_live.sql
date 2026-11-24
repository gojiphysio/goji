-- marts.patient_contact_live
--
-- Patients created or changed since the nightly plato-patients-ingest run, so
-- the WhatsApp assistant recognises a number the same day. On 24 Nov 2026 it
-- booked a new patient at 10:03 and told the same number "no patient record"
-- at 16:30, because marts.dim_patient_contact is rebuilt once a night.
--
-- Written by goji-booking (booking/patient_live.py), by streaming insert:
--   source = 'plato_webhook'    Plato's patient:upsert / patient:merge webhook
--                               (staff creating or editing a patient in Plato)
--   source = 'whatsapp_booking' a patient /internal/book created (Plato sends
--                               no webhook for API writes)
-- Read by the assistant's lookups (wa_agent/tools.py _CONTACTS) together with
-- dim_patient_contact; the newest row for a patient wins.
--
-- PII: full name + phone, the same scoped exception as dim_patient_contact
-- (see 42_dim_patient_contact.sql). Append-only; partitions expire after 7
-- days, by when the nightly table has every patient.

CREATE TABLE IF NOT EXISTS `goji-bi.marts.patient_contact_live` (
  patient_id  STRING    NOT NULL OPTIONS(description="Plato patient id"),
  full_name   STRING    OPTIONS(description="Patient's full name as in Plato"),
  phone       STRING    OPTIONS(description="Best-effort mobile/phone from the Plato record (same probe as the nightly ingest)"),
  source      STRING    NOT NULL OPTIONS(description="plato_webhook | whatsapp_booking"),
  received_at TIMESTAMP NOT NULL OPTIONS(description="When goji-booking wrote the row (UTC)")
)
PARTITION BY DATE(received_at)
OPTIONS(partition_expiration_days=7);
