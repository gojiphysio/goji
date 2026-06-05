-- marts.fct_patient_retention
--
-- One row per patient who has ever had a service delivered, tiered by how long
-- it's been since their last visit. This feeds the staff admin dashboard's
-- retention worklist: the front desk uses the tier colour to decide who to call
-- to re-book.
--
--   green   last seen <= 7 days  (healthy — shown for context, not action)
--   yellow  last seen 8-14 days  (> 1 week)
--   orange  last seen 15-28 days (> 2 weeks)
--   red     last seen > 28 days  (> 4 weeks — most at risk of churning)
--
-- PII-FREE BY DESIGN. This view emits only patient_id, dates, the tier, and the
-- already-PII-safe scalars from dim_patient (clinician, age_band,
-- initial_lastname). Full name and phone are NEVER stored — the dashboard
-- hydrates those live from Plato at render time. Keep it that way: do not add a
-- name/phone/dob/postal column here.
--
-- Scope: only patients with at least one delivered visit. A brand-new contact
-- who has never been seen is not "lapsed", so they don't belong on a re-book
-- worklist. has_future_appt / followup state are applied downstream by the app.

CREATE OR REPLACE VIEW `goji-bi.marts.fct_patient_retention` AS
WITH last_visit AS (
  -- Most recent delivered service per patient, carrying the clinician who saw
  -- them last (more useful for "who should call" than the dim_patient primary).
  SELECT
    patient_id,
    delivery_date AS last_visit_date,
    clinician_id  AS last_clinician_id
  FROM `goji-bi.marts.fct_service_delivered`
  WHERE patient_id IS NOT NULL
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY patient_id ORDER BY delivery_date DESC
  ) = 1
),
next_appt AS (
  -- Soonest genuinely-booked future appointment per patient. Cancelled / void /
  -- no-show future slots don't count as "already handled", so exclude them.
  -- Plato keeps status in the payload; we treat a truthy cancelled/void flag or
  -- a cancelled/no-show status text as not-booked. (The exact keys are defensive
  -- — if Plato never sets them, this simply keeps every future appt, which is
  -- the safe default: at worst we under-surface a patient who has a booking.)
  SELECT
    patient_id,
    MIN(appt_date) AS next_appt_date
  FROM `goji-bi.stg.appointments`
  WHERE patient_id IS NOT NULL
    AND appt_date > CURRENT_DATE()
    AND COALESCE(SAFE_CAST(JSON_VALUE(payload, '$.cancelled') AS INT64), 0) = 0
    AND COALESCE(SAFE_CAST(JSON_VALUE(payload, '$.void')      AS INT64), 0) = 0
    AND LOWER(COALESCE(JSON_VALUE(payload, '$.status'), '')) NOT IN
        ('cancelled', 'canceled', 'no_show', 'noshow', 'no-show')
  GROUP BY patient_id
)
SELECT
  lv.patient_id,
  lv.last_visit_date,
  DATE_DIFF(CURRENT_DATE(), lv.last_visit_date, DAY)      AS days_since_last,
  na.next_appt_date,
  na.next_appt_date IS NOT NULL                           AS has_future_appt,
  CASE
    WHEN DATE_DIFF(CURRENT_DATE(), lv.last_visit_date, DAY) <= 7  THEN 'green'
    WHEN DATE_DIFF(CURRENT_DATE(), lv.last_visit_date, DAY) <= 14 THEN 'yellow'
    WHEN DATE_DIFF(CURRENT_DATE(), lv.last_visit_date, DAY) <= 28 THEN 'orange'
    ELSE 'red'
  END                                                     AS tier,
  COALESCE(lv.last_clinician_id, p.primary_doctor)        AS clinician_id,
  p.age_band,
  p.initial_lastname
FROM last_visit lv
LEFT JOIN next_appt na USING (patient_id)
LEFT JOIN `goji-bi.marts.dim_patient` p USING (patient_id);
