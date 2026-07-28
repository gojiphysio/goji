-- marts.fct_clinician_utilization_daily
--
-- One row per clinician × day, carrying the two calendar facts a utilisation
-- metric needs: how many patient-facing minutes were booked, and whether that
-- day was flagged as leave. The *policy* half of utilisation — contracted hours,
-- each clinician's normal working weekdays, public holidays — lives in the
-- dashboard (`fetch_utilization` in app.py), so this view stays a thin, testable
-- layer over the calendar and nothing here changes when someone's hours do.
--
--   utilization% = booked patient hours / available hours   (computed in app.py)
--   available hours shrinks dynamically for days off: a day is "off" when it is
--   a public holiday (app.py list) OR the clinician flagged it as leave (`is_leave`).
--
-- How leave is detected (verified against real data 2026-07):
--   Plato's `allDay` field is an unreliable string ("0"/"1") and is almost never
--   set, and the `-all-` calendar is a shared ADMIN calendar (team meetings,
--   "Admin Time", OOO, travel) — NOT a leave marker, so we must not treat it as
--   time off. Individual leave is entered as a block on the clinician's OWN
--   calendar (their colour) with a leave-word title, e.g. Claire's 6hpO "Leave" /
--   "Holiday". We key on that title. Public/clinic closures come from the app.py
--   holiday list, not from here.
--
-- Grain: (clinician_id, day) for the three mapped clinicians, emitted for any
-- day that had EITHER a real patient session OR a leave block. Booked-only days
-- carry is_leave = FALSE; leave-only days carry booked_minutes = 0.
--
-- Scope note: reads past-and-present calendar rows. Plato ingestion is
-- append-only with no delete detection, so a past appointment cancelled without
-- a status update can linger as a "ghost" and marginally overstate booked
-- minutes — the same accepted limitation the rest of the appointment marts
-- carry. Downstream caps the window at today, so no forward-looking ghost
-- guard is needed here.

CREATE OR REPLACE VIEW `goji-bi.marts.fct_clinician_utilization_daily` AS
WITH
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

-- Individual leave: a block on the clinician's OWN calendar (colour → clinician)
-- whose title flags time off. Word-boundary match keeps false positives down
-- (e.g. "leave" won't fire on a surname like "Cleaver"). Public/clinic closures
-- are NOT sourced here — they come from the app.py holiday list.
leave AS (
  SELECT DISTINCT
    CASE calendar_color
      WHEN 'blue'  THEN 'PCL'
      WHEN 'green' THEN 'PKN'
      WHEN '6hpO'  THEN 'PCN'
    END          AS clinician_id,
    appt_date    AS day
  FROM `goji-bi.stg.appointments`
  WHERE calendar_color IN ('blue', 'green', '6hpO')
    AND REGEXP_CONTAINS(
          LOWER(COALESCE(title, '')),
          r'\b(leave|holiday|annual|day off|rest day|time off|public holiday)\b')
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
  lv.clinician_id IS NOT NULL       AS is_leave
FROM days d
LEFT JOIN sessions s USING (clinician_id, day)
LEFT JOIN leave    lv USING (clinician_id, day);
