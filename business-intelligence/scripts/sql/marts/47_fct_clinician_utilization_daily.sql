-- marts.fct_clinician_utilization_daily
--
-- One row per clinician × day, carrying the two calendar facts a utilisation
-- metric needs: how many patient-facing minutes were booked, and whether that
-- day was an all-day block (leave / clinic closure). The *policy* half of
-- utilisation — contracted hours, each clinician's normal working weekdays,
-- public holidays — lives in the dashboard (`fetch_utilization` in app.py), so
-- this view stays a thin, testable layer over the calendar and nothing here
-- needs to change when someone's contracted hours do.
--
--   utilization% = booked patient hours / available hours   (computed in app.py)
--   available hours shrinks dynamically for days off: a day is "off" when it is
--   a public holiday OR carries an all-day block (`is_all_day_leave`).
--
-- Grain: (clinician_id, day) for the three mapped clinicians, emitted for any
-- day that had EITHER a real patient session OR an all-day block. Booked-only
-- days carry is_all_day_leave = FALSE; leave-only days carry booked_minutes = 0.
--
-- Scope note: reads past-and-present calendar rows. Plato ingestion is
-- append-only with no delete detection, so a past appointment cancelled without
-- a status update can linger as a "ghost" and marginally overstate booked
-- minutes — the same accepted limitation the rest of the appointment marts
-- carry. Downstream caps the window at today, so no forward-looking ghost
-- guard is needed here.

CREATE OR REPLACE VIEW `goji-bi.marts.fct_clinician_utilization_daily` AS
WITH clinicians AS (
  SELECT clinician_id FROM UNNEST(['PCN', 'PKN', 'PCL']) AS clinician_id
),

-- Distinct booked SLOTS (not appointment rows): a 2:1 / group class writes two
-- appointment rows for one physical slot at the same (colour, start, end), and
-- counting rows would double the clinician's booked time. Dedupe to the slot,
-- then sum its duration. Qualifier is the canonical "real patient session" rule
-- (cancelled/void/no-show excluded; a genuine patient signal present) shared
-- with the upcoming-sessions / new-patient marts.
slots AS (
  SELECT DISTINCT
    clinician_id,
    appt_date                                        AS day,
    calendar_color,
    start_at,
    end_at,
    TIMESTAMP_DIFF(end_at, start_at, MINUTE)         AS mins
  FROM `goji-bi.stg.appointments`
  WHERE clinician_id IS NOT NULL
    AND end_at > start_at
    AND TIMESTAMP_DIFF(end_at, start_at, MINUTE) BETWEEN 5 AND 240
    AND COALESCE(SAFE_CAST(JSON_VALUE(payload, '$.cancelled') AS INT64), 0) = 0
    AND COALESCE(SAFE_CAST(JSON_VALUE(payload, '$.void')      AS INT64), 0) = 0
    AND LOWER(COALESCE(JSON_VALUE(payload, '$.status'), '')) NOT IN
        ('cancelled', 'canceled', 'no_show', 'noshow', 'no-show')
    AND (
         (patient_id IS NOT NULL AND patient_id != '')
      OR COALESCE(JSON_VALUE(payload, '$.handphone'), '') != ''
      OR COALESCE(JSON_VALUE(payload, '$.email'),     '') != ''
      OR treatment_type NOT IN ('Untyped', 'Unknown')
    )
),
sessions AS (
  SELECT clinician_id, day, SUM(mins) AS booked_minutes, COUNT(*) AS slots
  FROM slots
  GROUP BY clinician_id, day
),

-- All-day blocks = how the clinic records leave / closures in Plato. A block on
-- a clinician's own calendar (colour → clinician) is that person's day off; a
-- clinic-wide block (the booking service's `-all-` colour convention) is a day
-- off for everyone.
allday AS (
  SELECT DISTINCT appt_date AS day, calendar_color
  FROM `goji-bi.stg.appointments`
  WHERE COALESCE(SAFE_CAST(JSON_VALUE(payload, '$.allDay') AS BOOL), FALSE) = TRUE
),
leave AS (
  -- Per-clinician all-day block
  SELECT
    CASE a.calendar_color
      WHEN 'blue'  THEN 'PCL'
      WHEN 'green' THEN 'PKN'
      WHEN '6hpO'  THEN 'PCN'
    END        AS clinician_id,
    a.day
  FROM allday a
  WHERE a.calendar_color IN ('blue', 'green', '6hpO')
  UNION DISTINCT
  -- Clinic-wide all-day block applies to every clinician
  SELECT c.clinician_id, a.day
  FROM allday a
  CROSS JOIN clinicians c
  WHERE a.calendar_color = '-all-'
),

-- Union of every (clinician, day) we have something to say about.
days AS (
  SELECT clinician_id, day FROM sessions
  UNION DISTINCT
  SELECT clinician_id, day FROM leave
)

SELECT
  d.clinician_id,
  d.day,
  COALESCE(s.booked_minutes, 0)     AS booked_minutes,
  COALESCE(s.slots, 0)              AS slots,
  lv.clinician_id IS NOT NULL       AS is_all_day_leave
FROM days d
LEFT JOIN sessions s USING (clinician_id, day)
LEFT JOIN leave    lv USING (clinician_id, day);
