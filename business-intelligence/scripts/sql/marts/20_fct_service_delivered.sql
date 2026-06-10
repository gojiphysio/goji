-- marts.fct_service_delivered
--
-- THE REVENUE FACT. Grain: one row per session actually rendered. Two sources:
--
--   (A) Redemption lines: fanned out by physical session count (qty), NOT by the
--       redeem_alloc array length. When a patient redeems 1 session but the credit
--       is split across two packages (cross-package transition), Plato writes two
--       redeem_alloc entries for one physical visit. Using qty instead avoids
--       double-counting in that scenario while still generating the correct number
--       of rows when qty > 1 (e.g. a 2-session redemption yields two rows).
--       recognised_revenue per row = recognised_amount / qty.
--
--   (B) Single-use sale lines (consults, products): one row per line, with
--       delivery_date = invoice_date (booking and recognition collapse).
--
-- Package sale lines do NOT appear here. They sit only in fct_invoice_line;
-- their revenue gets recognised over time as redemptions land in (A).
--
-- clinician_id on (A) rows is invoice.doctor, which for a redemption invoice
-- is the DELIVERING clinician (not the seller).

CREATE OR REPLACE VIEW `goji-bi.marts.fct_service_delivered` AS

-- (A) Redemption fan-out by session count (qty), not alloc array length
SELECT
  CONCAT(invoice_id, '-', CAST(line_idx AS STRING), '-', CAST(session_idx AS STRING))
                                                        AS delivery_id,
  invoice_date                                          AS delivery_date,
  finalized_at                                          AS delivery_ts,
  patient_id,
  clinician_id,
  location_id,
  item_id                                               AS service_item_id,
  item_given_id                                         AS service_item_given_id,
  item_name,
  -- Use first alloc entry for package source attribution (primary package)
  JSON_VALUE(redeem_alloc[OFFSET(0)], '$.invoice')      AS source_invoice_id,
  JSON_VALUE(redeem_alloc[OFFSET(0)], '$.item_id')      AS source_item_id,
  CAST(NULL AS STRING)                                  AS appointment_id,
  -- Spread total recognised value evenly across physical sessions
  SAFE_DIVIDE(recognised_amount, GREATEST(qty, 1))      AS recognised_revenue,
  'package_burn'                                        AS delivery_method
FROM `goji-bi.stg.invoice_items`,
  UNNEST(GENERATE_ARRAY(0, CAST(GREATEST(qty, 1) AS INT64) - 1)) AS session_idx
WHERE classification = 'redemption'

UNION ALL

-- (B) Single-use sales
SELECT
  CONCAT(invoice_id, '-', CAST(line_idx AS STRING))     AS delivery_id,
  invoice_date                                          AS delivery_date,
  finalized_at                                          AS delivery_ts,
  patient_id,
  clinician_id,
  location_id,
  item_id                                               AS service_item_id,
  item_given_id                                         AS service_item_given_id,
  item_name,
  invoice_id                                            AS source_invoice_id,
  item_id                                               AS source_item_id,
  CAST(NULL AS STRING)                                  AS appointment_id,
  recognised_amount                                     AS recognised_revenue,
  'single_use'                                          AS delivery_method
FROM `goji-bi.stg.invoice_items`
WHERE classification = 'sale'
  AND COALESCE(recognised_amount, 0) > 0;
