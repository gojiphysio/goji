-- marts.fct_package_balance
--
-- One row per patient who has ever bought a package, with how many prepaid
-- sessions they have left: sessions_sold - sessions_delivered. This feeds the
-- Front Desk "Package Alerts" tab (who is about to run out and should be
-- offered a renewal) and the per-row session balance on the Today schedule.
--
-- PII-FREE BY DESIGN — same boundary as fct_patient_retention. Keys on
-- patient_id only; full name + phone are hydrated live by the app from
-- marts.dim_patient_contact at render time and never stored here.
--
-- HOW SESSIONS ARE COUNTED
--
--   delivered = COUNT of package_burn rows in fct_service_delivered. Each burn
--               row is exactly one session redeemed, so this side is exact.
--
--   sold      = SUM of pack sizes across the patient's package_sale lines.
--               Plato does NOT store a session count on the line — qty is the
--               number of *packages* (almost always 1), not sessions. The
--               session count lives in the SKU (item_given_id), e.g.
--               "SC-10OP" = a 10-session S&C pack. We read the pack size as the
--               number in the SKU segment after the final hyphen
--               (REGEXP r'-(\d+)[A-Z]*$'): "SC-10OP" -> 10, "PP1:1-5" -> 5.
--               The leading "PP1:1" ratio uses a colon, so it is never mistaken
--               for a pack size. This is the same SKU-as-source-of-truth rule
--               the dashboard's promo-discount tile already relies on.
--
-- CONSERVATIVE WHEN UNSURE: if a patient holds any package whose SKU does not
-- encode a pack size we can read, sessions_remaining is NULL (unknown) rather
-- than a guess. A guessed-low number would wrongly push a renewal call on the
-- Package Alerts tab; NULL keeps them off it. A proper pack-size reference
-- table would make every package exact — fold one in here if/when it exists.
--
-- Created as a VIEW (CREATE OR REPLACE) — derived, no state to preserve.

CREATE OR REPLACE VIEW `goji-bi.marts.fct_package_balance` AS
WITH sold AS (
  SELECT
    patient_id,
    -- Pack size from the SKU; NULL when it isn't encoded there.
    SAFE_CAST(REGEXP_EXTRACT(item_given_id, r'-(\d+)[A-Z]*$') AS INT64) AS pack_sessions
  FROM `goji-bi.marts.fct_invoice_line`
  WHERE is_package_sale
    AND patient_id IS NOT NULL
),
sold_rollup AS (
  SELECT
    patient_id,
    -- Total prepaid sessions bought (only the packs whose size we can read).
    SUM(pack_sessions)                       AS sessions_sold,
    -- Did this patient buy any package whose pack size we couldn't read? If so
    -- the sold total is incomplete and the balance is not trustworthy.
    LOGICAL_OR(pack_sessions IS NULL)        AS has_unreadable_pack
  FROM sold
  GROUP BY patient_id
),
delivered AS (
  SELECT
    patient_id,
    COUNT(*)        AS sessions_delivered,
    MAX(delivery_date) AS last_visit_date
  FROM `goji-bi.marts.fct_service_delivered`
  WHERE patient_id IS NOT NULL
    AND delivery_method = 'package_burn'
  GROUP BY patient_id
)
SELECT
  s.patient_id,
  s.sessions_sold,
  COALESCE(d.sessions_delivered, 0)                        AS sessions_delivered,
  d.last_visit_date,
  -- Unknown (NULL) when any pack size was unreadable; otherwise floor at 0 so a
  -- patient who somehow over-redeemed still reads as "0 left", not negative.
  CASE
    WHEN s.has_unreadable_pack THEN NULL
    ELSE GREATEST(s.sessions_sold - COALESCE(d.sessions_delivered, 0), 0)
  END                                                      AS sessions_remaining
FROM sold_rollup s
LEFT JOIN delivered d USING (patient_id);
