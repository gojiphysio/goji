-- marts.fct_service_delivered
--
-- THE REVENUE FACT. Grain: one row per session actually rendered. Two sources:
--
--   (A) Redemption lines: fanned out by item.others.redeem_alloc[]. A two-session
--       redemption on one invoice line yields TWO rows here. Each row's
--       recognised_revenue is the per-session value Plato computed for us
--       (redeem_alloc[].value).
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

-- (A) Redemption fan-out
SELECT
  CONCAT(invoice_id, '-', CAST(line_idx AS STRING), '-', CAST(alloc_idx AS STRING))
                                                      AS delivery_id,
  invoice_date                                        AS delivery_date,
  finalized_at                                        AS delivery_ts,
  patient_id,
  clinician_id,
  location_id,
  item_id                                             AS service_item_id,
  item_given_id                                       AS service_item_given_id,
  item_name,
  JSON_VALUE(alloc, '$.invoice')                      AS source_invoice_id,
  JSON_VALUE(alloc, '$.item_id')                      AS source_item_id,
  CAST(NULL AS STRING)                                AS appointment_id,
  SAFE_CAST(JSON_VALUE(alloc, '$.value') AS NUMERIC)  AS recognised_revenue,
  'package_burn'                                      AS delivery_method
FROM `goji-bi.stg.invoice_items`,
  UNNEST(redeem_alloc) AS alloc WITH OFFSET alloc_idx
WHERE classification = 'redemption'

UNION ALL

-- (B) Single-use sales
SELECT
  CONCAT(invoice_id, '-', CAST(line_idx AS STRING))   AS delivery_id,
  invoice_date                                        AS delivery_date,
  finalized_at                                        AS delivery_ts,
  patient_id,
  clinician_id,
  location_id,
  item_id                                             AS service_item_id,
  item_given_id                                       AS service_item_given_id,
  item_name,
  invoice_id                                          AS source_invoice_id,
  item_id                                             AS source_item_id,
  CAST(NULL AS STRING)                                AS appointment_id,
  recognised_amount                                   AS recognised_revenue,
  'single_use'                                        AS delivery_method
FROM `goji-bi.stg.invoice_items`
WHERE classification = 'sale'
  AND COALESCE(recognised_amount, 0) > 0;
