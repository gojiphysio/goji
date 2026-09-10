-- marts.fct_appointment_reminders
--
-- Appointments due a 48-hour reminder email — the recipient list for the daily
-- `appointment-reminders` Cloud Run Job (12:00 SGT, Asia/Singapore).
--
-- Replaces a manual chore: Plato's reminder template can only be fired by hand
-- from its UI (its API exposes no notification/template endpoint), so someone
-- had to log in every day and click it for the sessions ~48h out. This view is
-- the "who gets one today" half of automating that away.
--
-- WINDOW — D+2 CALENDAR DATE, not a rolling 48 hours:
--   appt_date = CURRENT_DATE('Asia/Singapore') + 2. Run at noon, Monday sends to
--   every Wednesday appointment (so a 9am Wed session gets 45h notice and a 7pm
--   one gets 55h). This is what the clinic actually asked for, and keying on
--   appt_date — already a clinic-local DATE — sidesteps the start_at timezone
--   trap below entirely. The job runs all 7 days, so there is no weekend gap:
--   Saturday covers Monday, Sunday covers Tuesday.
--
--   Someone who books INSIDE the window never gets a reminder. That's deliberate
--   — they just booked and already have a confirmation email.
--
-- ⚠️ TIMEZONE TRAP — READ BEFORE TOUCHING appt_time_sgt:
--   stg.appointments.start_at is PARSE_TIMESTAMP'd as if UTC (see
--   stg/03_appointments.sql) but Plato stores clinic WALL-CLOCK (SGT). So the
--   correct way to read the wall clock back out is to format at 'UTC'.
--   Converting to 'Asia/Singapore' shifts every appointment by 8 hours and mails
--   the whole list the wrong time. dashboard/admin.html compensates the same way
--   client-side (`- 8`). Do not "fix" this.
--
-- PII-FREE BY DESIGN — same boundary as fct_new_patient_welcome. Keys on
-- appointment_id (+ patient_id when linked). Name / phone / email are hydrated
-- at send time by the job, from the appointment payload for profile-less
-- website/walk-in bookings and from marts.dim_patient_contact for linked
-- patients. Nothing identifying is stored here. `has_email` is the one
-- concession: a boolean, so this view alone answers "how many can we reach?"
-- without exposing an address.
--
-- WHAT QUALIFIES AS A PATIENT SESSION (verbatim from fct_new_patient_welcome —
-- keep the three copies in sync):
--   not cancelled / void / no-show, AND it looks like a real patient booking:
--   a linked patient_id, OR inline contact (handphone/email), OR a real
--   treatment_type. This drops lunches, 1:1s, time blocks, shifts, travel and
--   admin. Travel blocks matter here specifically: a home visit is THREE Plato
--   appointments (travel / visit / travel) and booking.py creates the travel
--   legs with no email/phone/code_Bottom, so they fail this qualifier and we
--   don't remind anyone about a drive.
--
-- GHOST / DELETED-APPOINTMENT GUARD (freshness filter):
--   The plato_appointments ingestion is append-only with no deletion detection,
--   so a deleted Plato appointment lingers as its last-known version. The whole
--   window is re-pulled every 15 min, so a live appointment's _loaded_at
--   advances each run and a deleted one goes stale. Keeping only appointments
--   seen in the most recent run is what stops us emailing a reminder for an
--   appointment the patient already cancelled.

CREATE OR REPLACE VIEW `goji-bi.marts.fct_appointment_reminders` AS
WITH freshness AS (
  -- Newest load across all appointments = the most recent ingestion run.
  SELECT TIMESTAMP_SUB(MAX(_loaded_at), INTERVAL 30 MINUTE) AS min_loaded_at
  FROM `goji-bi.stg.appointments`
)
SELECT
  a.appointment_id,
  NULLIF(a.patient_id, '')                          AS patient_id,
  a.appt_date,
  a.start_at                                        AS appt_datetime,
  -- Clinic wall-clock. 'UTC' is correct here — see the timezone note above.
  FORMAT_TIMESTAMP('%H:%M', a.start_at, 'UTC')      AS appt_time_sgt,
  a.clinician_id,
  a.treatment_type,
  -- Drives which half of the email body the patient sees: the clinic address
  -- and directions block, or the home-visit paragraph. Never both.
  a.treatment_type = 'Home Visit'                   AS is_home_visit,
  -- Can we actually reach them by email? Contact itself is hydrated at send
  -- time; this boolean keeps the view PII-free while still being auditable.
  COALESCE(JSON_VALUE(a.payload, '$.email'), '') != '' AS has_email
FROM `goji-bi.stg.appointments` a, freshness f
WHERE a.appt_date = DATE_ADD(CURRENT_DATE('Asia/Singapore'), INTERVAL 2 DAY)
  -- not cancelled / void / no-show
  AND COALESCE(SAFE_CAST(JSON_VALUE(a.payload, '$.cancelled') AS INT64), 0) = 0
  AND COALESCE(SAFE_CAST(JSON_VALUE(a.payload, '$.void')      AS INT64), 0) = 0
  AND LOWER(COALESCE(JSON_VALUE(a.payload, '$.status'), '')) NOT IN
      ('cancelled', 'canceled', 'no_show', 'noshow', 'no-show')
  -- looks like a real patient session, not a lunch / block / 1:1 / travel / admin
  AND (
       (a.patient_id IS NOT NULL AND a.patient_id != '')
    OR COALESCE(JSON_VALUE(a.payload, '$.handphone'), '') != ''
    OR COALESCE(JSON_VALUE(a.payload, '$.email'), '')     != ''
    OR a.treatment_type NOT IN ('Untyped', 'Unknown')
  )
  -- ghost guard: only appointments seen in the most recent ingestion run
  AND a._loaded_at >= f.min_loaded_at;
