-- marts.fct_upcoming_appointments
--
-- Grain: one row per appointment from today through the next 72 hours
-- (CURRENT_DATE() .. CURRENT_DATE() + 3). Feeds the Front Desk "Today",
-- "Call List" and (via fct_package_balance) "Package Alerts" tabs so the team
-- no longer has to keep Plato open alongside the dashboard.
--
-- PII-FREE BY DESIGN — same boundary as fct_patient_retention. Emits only
-- patient_id, the appointment scalars, and the already-PII-safe dim_patient
-- fields (initial_lastname, age_band). Full name + phone are hydrated live by
-- the app from marts.dim_patient_contact at render time and never stored here.
-- Keep it that way: do not add a name/phone column.
--
-- CONFIRMATION lives in our own append-only log (marts.appt_confirmation_events),
-- not in Plato, so this view cannot know "confirmed" vs "unconfirmed" — it only
-- exposes is_cancelled (derived from Plato). The app overlays confirmation
-- status at render time, exactly as the retention worklist overlays follow-up
-- state. An appointment is "unconfirmed" until the front desk confirms it.
--
-- DATA FRESHNESS: reads stg.appointments, which ingests from Plato every 15
-- minutes. A <=15-minute lag is acceptable for a same-day schedule view, so we
-- use BigQuery as-is rather than calling Plato live (Roadmap Phase 2 open
-- question, resolved: "use BQ as-is").
--
-- TIME-OF-DAY: Plato stores appointment times as naive "YYYY-MM-DD HH:MM:SS"
-- (parsed into start_at as a UTC timestamp upstream). We surface appt_time as
-- the verbatim wall-clock "HH:MM" string and never timezone-convert it, so the
-- schedule shows the same clock time the clinic booked. Ordering uses start_at.

CREATE OR REPLACE VIEW `goji-bi.marts.fct_upcoming_appointments` AS
WITH first_delivery AS (
  -- Earliest delivered visit per patient. A patient with no prior delivery (or
  -- whose first delivery is on/after this appointment) is treated as a new
  -- patient for this appointment -> the "NEW" badge on the Today tab.
  SELECT patient_id, MIN(delivery_date) AS first_visit_date
  FROM `goji-bi.marts.fct_service_delivered`
  WHERE patient_id IS NOT NULL
  GROUP BY patient_id
)
SELECT
  a.appointment_id,
  a.appt_date,
  a.start_at,
  a.end_at,
  -- Verbatim clock time for display (no TZ conversion — see header note).
  FORMAT_TIMESTAMP('%H:%M', a.start_at)                   AS appt_time,
  a.patient_id,
  a.clinician_id,
  a.treatment_type                                        AS service_name,
  -- Cancelled / void / no-show -> not a real upcoming appointment. Same
  -- defensive payload checks as fct_patient_retention.next_appt.
  (   COALESCE(SAFE_CAST(JSON_VALUE(a.payload, '$.cancelled') AS INT64), 0) <> 0
   OR COALESCE(SAFE_CAST(JSON_VALUE(a.payload, '$.void')      AS INT64), 0) <> 0
   OR LOWER(COALESCE(JSON_VALUE(a.payload, '$.status'), '')) IN
        ('cancelled', 'canceled', 'no_show', 'noshow', 'no-show')
  )                                                       AS is_cancelled,
  p.initial_lastname,
  p.age_band,
  (fd.first_visit_date IS NULL OR fd.first_visit_date >= a.appt_date)
                                                          AS is_first_visit,
  pb.sessions_remaining
FROM `goji-bi.stg.appointments` a
LEFT JOIN `goji-bi.marts.dim_patient`        p  USING (patient_id)
LEFT JOIN first_delivery                     fd USING (patient_id)
LEFT JOIN `goji-bi.marts.fct_package_balance` pb USING (patient_id)
WHERE a.appt_date BETWEEN CURRENT_DATE() AND CURRENT_DATE() + 3;
