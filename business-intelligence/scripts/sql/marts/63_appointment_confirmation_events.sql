-- marts.appointment_confirmation_events
--
-- Send ledger for the booking confirmation email (booking/confirmations.py):
-- one email per appointment, whoever booked it (website, WhatsApp assistant or
-- staff in Plato). One row appended per attempt. Append-only, like the other
-- event logs: goji-booking never UPDATEs or DELETEs here.
--
-- THIS IS THE GUARD AGAINST A SECOND EMAIL. Before sending, the service reads
-- the last row with the delivered status for the appointment:
--   none                    -> send the confirmation (kind 'booked', sequence 0)
--   same start_key          -> nothing (it already has its email)
--   different start_key     -> the appointment moved: send kind 'moved' with
--                              sequence + 1, which updates the patient's
--                              calendar entry (same invite UID) instead of
--                              adding a second one.
-- The Plato webhook and the 15-minute sweep can both see one staff booking;
-- the read happens under a lock in the single goji-booking instance.
--
-- KEYED ON appointment_id (the visit, never a home visit's travel legs):
-- website bookings have no patient_id, so the appointment is the only id every
-- booking has. start_key is the clinic wall clock ('YYYY-MM-DD HH:MM'), the
-- same string the sweep formats from stg.appointments.start_at at 'UTC'
-- (Plato wall clock, see the timezone note in stg/03_appointments.sql).
--
-- PII: no name, email or phone. `note` is operational ('registration form',
-- an SMTP error with the address scrubbed).
--
-- status values:
--   'sent'             — accepted by Gmail SMTP, to the patient (mode live).
--   'test'             — CONFIRMATIONS_MODE=test: sent to the test inbox. Only
--                        suppresses further test sends, never a real one.
--   'skipped_no_email' — nothing to send to.
--   'failed'           — the send raised. Retried by the sweep up to 3 times
--                        per start time, then left for someone to look at.
-- source: web | whatsapp | staff (Plato webhook) | sweep.
-- kind:   booked | moved.

CREATE TABLE IF NOT EXISTS `goji-bi.marts.appointment_confirmation_events` (
  event_id       STRING    NOT NULL OPTIONS(description="UUID for this event row"),
  appointment_id STRING    NOT NULL OPTIONS(description="Plato appointment id of the visit"),
  start_key      STRING    NOT NULL OPTIONS(description="Clinic wall-clock start, YYYY-MM-DD HH:MM, the email was about"),
  sequence       INT64     NOT NULL OPTIONS(description="Calendar invite SEQUENCE sent: 0 on booking, +1 per move"),
  kind           STRING    NOT NULL OPTIONS(description="booked | moved"),
  status         STRING    NOT NULL OPTIONS(description="sent | test | skipped_no_email | failed"),
  source         STRING    OPTIONS(description="web | whatsapp | staff | sweep"),
  note           STRING    OPTIONS(description="Operational note. Never PII"),
  sent_at        TIMESTAMP NOT NULL OPTIONS(description="When the send was attempted")
);
