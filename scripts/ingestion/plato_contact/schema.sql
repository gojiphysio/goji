-- marts.dim_referral_source: the referral-source dimension.
--
-- Plato's /contact endpoint is a small registry of external referral channels
-- (GPs, specialist clinics, gyms, "Walk-in", online booking sources, etc).
-- Patient records reference these via the `referred_by` field, which holds a
-- contact `_id` (NOT a patient_id — confirmed empirically).
--
-- We keep the channel identity (name, person, category) because referrers are
-- organisations or named professionals listed publicly, not patients. We
-- discard contact-detail fields (email/phone/address/fax/url/notes) at ingest
-- because they are unused by the dashboard and increase risk of leaking
-- professional contacts.
--
-- Same pattern as dim_patient: the ingest job is the only code that ever
-- sees the raw payload; only the PII-safe derived shape lands here.

CREATE TABLE IF NOT EXISTS `goji-bi.marts.dim_referral_source` (
  contact_id STRING NOT NULL
    OPTIONS(description = "Plato contact _id. Joins marts.dim_patient.referred_by."),
  name STRING
    OPTIONS(description = "Organisation/channel name as recorded in Plato, e.g. 'UFIT', 'Trinity Women's', 'Walk-in', 'Goji Physio'. May be blank."),
  person STRING
    OPTIONS(description = "Named contact at the channel, e.g. 'Dr Samantha Yeo' for an external clinic, or 'Online Booking - Instagram' for an intake-channel marker. May be blank."),
  category STRING
    OPTIONS(description = "Free-text category recorded in Plato, e.g. 'OBGYN', 'GP', 'Spine'. May be blank."),
  source_type STRING
    OPTIONS(description = "Derived bucket: 'medical' (GPs, specialists), 'partner' (gyms, allied health), 'walk_in', 'online' (Plato Online, WhatsApp, Instagram bookings), 'word_of_mouth' (in-house clinician personal network), 'other'. Computed by the ingest job from name/person/category."),
  display_label STRING
    OPTIONS(description = "Human-friendly label for dashboard tables, derived from name + person."),
  created_on DATE
    OPTIONS(description = "Date the contact record was created in Plato."),
  _updated_at TIMESTAMP NOT NULL
    OPTIONS(description = "UTC timestamp this row was last refreshed from Plato.")
)
CLUSTER BY contact_id
OPTIONS(
  description = "PII-minimised referral source dimension. Source: Plato /contact. Refreshed by the plato-contact-ingest Cloud Run Job. Joins marts.dim_patient.referred_by."
);
