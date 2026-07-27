-- marts.fct_new_patient_welcome
--
-- Upcoming FIRST visits — the front-desk "Welcome" worklist. One row per
-- patient booking (a person, not a slot: unlike the founder dashboard's session
-- count we do NOT collapse group/2:1 classes here — every new person needs
-- welcoming). Feeds the frontdesk portal's first tab, where the front desk
-- messages new patients directions / arrival info before they turn up.
--
-- PII-FREE BY DESIGN — same boundary as fct_patient_retention /
-- fct_package_balance. Keys on appointment_id (+ patient_id when the patient has
-- a Plato profile). Name / phone / email are hydrated live by the app at render
-- time: from the appointment payload for profile-less website/walk-in bookings
-- (the documented lead-style PII exception) and from marts.dim_patient_contact
-- for linked patients. Nothing identifying is stored here.
--
-- WHAT QUALIFIES AS A PATIENT SESSION (mirrors fetch_upcoming_sessions in
-- app.py — keep the two in sync):
--   not cancelled / void / no-show, AND it looks like a real patient booking:
--   a linked patient_id, OR inline contact (handphone/email — how a
--   profile-less website/walk-in booking still carries the patient), OR a real
--   treatment_type (not the blank 'Untyped' / unrecognised 'Unknown'). This
--   drops lunches, 1:1s, time blocks, shifts, travel and admin, which carry
--   none of those. treatment_type alone is NOT a qualifier (~45% of real appts
--   are Untyped).
--
-- GHOST / DELETED-APPOINTMENT GUARD (freshness filter):
--   The plato_appointments ingestion is append-only with no deletion detection,
--   so a deleted Plato appointment lingers in stg.appointments as its
--   last-known version. The whole [today-PAST, today+FUTURE] window is re-pulled
--   every run, so a *live* appointment's _loaded_at advances each run; a deleted
--   one goes stale. We keep only appointments reloaded in the most recent run
--   (within 30 min of the newest _loaded_at) so cancelled/deleted ghosts drop
--   off the welcome list.
--
-- WHAT COUNTS AS "NEW":
--   linked patient   -> no prior delivered service (marts.fct_service_delivered)
--                        AND no prior appointment before today. The appointment
--                        check catches a just-happened first visit that hasn't
--                        been invoiced yet (fct_service_delivered lags booking).
--   profile-less      -> no Plato profile yet => new, UNLESS the same phone/email
--                        already appeared on an appointment before today
--                        (returning-but-unlinked guard; bounded by how far back
--                        appointments have been ingested).

CREATE OR REPLACE VIEW `goji-bi.marts.fct_new_patient_welcome` AS
WITH freshness AS (
  -- Newest load across all appointments = the most recent ingestion run.
  SELECT TIMESTAMP_SUB(MAX(_loaded_at), INTERVAL 30 MINUTE) AS min_loaded_at
  FROM `goji-bi.stg.appointments`
),
prior_service AS (
  SELECT DISTINCT patient_id
  FROM `goji-bi.marts.fct_service_delivered`
  WHERE patient_id IS NOT NULL
),
prior_appt_patients AS (
  -- Linked patients who already have an appointment before today: they've been
  -- (or were due to come) before, so an upcoming appt isn't a first visit even
  -- if the earlier one hasn't landed in fct_service_delivered yet.
  SELECT DISTINCT patient_id
  FROM `goji-bi.stg.appointments`
  WHERE patient_id IS NOT NULL AND patient_id != ''
    AND appt_date < CURRENT_DATE('Asia/Singapore')
),
prior_contacts AS (
  -- Phone / email seen on any appointment before today: used to spot a
  -- returning-but-unlinked patient so we don't welcome them as brand new.
  SELECT contact FROM (
    SELECT JSON_VALUE(payload, '$.handphone') AS contact
    FROM `goji-bi.stg.appointments`
    WHERE appt_date < CURRENT_DATE('Asia/Singapore')
    UNION ALL
    SELECT JSON_VALUE(payload, '$.email')
    FROM `goji-bi.stg.appointments`
    WHERE appt_date < CURRENT_DATE('Asia/Singapore')
  )
  WHERE contact IS NOT NULL AND contact != ''
  GROUP BY contact
),
qualifying AS (
  SELECT
    a.appointment_id,
    NULLIF(a.patient_id, '')                        AS patient_id,
    a.start_at                                      AS appt_datetime,
    a.appt_date,
    a.clinician_id,
    a.treatment_type,
    JSON_VALUE(a.payload, '$.created_by')           AS created_by,
    JSON_VALUE(a.payload, '$.handphone')            AS handphone,
    JSON_VALUE(a.payload, '$.email')                AS email
  FROM `goji-bi.stg.appointments` a, freshness f
  WHERE a.appt_date BETWEEN CURRENT_DATE('Asia/Singapore')
                        AND DATE_ADD(CURRENT_DATE('Asia/Singapore'), INTERVAL 30 DAY)
    -- not cancelled / void / no-show (same defensive keys as fct_patient_retention)
    AND COALESCE(SAFE_CAST(JSON_VALUE(a.payload, '$.cancelled') AS INT64), 0) = 0
    AND COALESCE(SAFE_CAST(JSON_VALUE(a.payload, '$.void')      AS INT64), 0) = 0
    AND LOWER(COALESCE(JSON_VALUE(a.payload, '$.status'), '')) NOT IN
        ('cancelled', 'canceled', 'no_show', 'noshow', 'no-show')
    -- looks like a real patient session, not a lunch / block / 1:1 / admin
    AND (
         (a.patient_id IS NOT NULL AND a.patient_id != '')
      OR COALESCE(JSON_VALUE(a.payload, '$.handphone'), '') != ''
      OR COALESCE(JSON_VALUE(a.payload, '$.email'), '')     != ''
      OR a.treatment_type NOT IN ('Untyped', 'Unknown')
    )
    -- ghost guard: only appointments seen in the most recent ingestion run
    AND a._loaded_at >= f.min_loaded_at
)
SELECT
  q.appointment_id,
  q.patient_id,                                     -- NULL for profile-less bookings
  q.appt_datetime,
  q.appt_date,
  q.clinician_id,
  q.treatment_type,
  q.created_by,
  -- Booking source: Plato tags website/API bookings with created_by='api'.
  CASE WHEN LOWER(COALESCE(q.created_by, '')) = 'api' THEN 'website' ELSE 'manual' END
                                                    AS booking_source,
  -- Does this patient already have a Plato profile? (drives the "set up profile"
  -- nudge on the front desk.)
  q.patient_id IS NOT NULL                          AS has_profile
FROM qualifying q
WHERE
  -- Linked patient with no prior delivered service and no prior appointment.
  (q.patient_id IS NOT NULL
     AND q.patient_id NOT IN (SELECT patient_id FROM prior_service)
     AND q.patient_id NOT IN (SELECT patient_id FROM prior_appt_patients))
  OR
  -- Profile-less booking: new unless this phone/email was seen on a past appt.
  (q.patient_id IS NULL
     AND COALESCE(q.handphone, '') NOT IN (SELECT contact FROM prior_contacts)
     AND COALESCE(q.email, '')     NOT IN (SELECT contact FROM prior_contacts));
