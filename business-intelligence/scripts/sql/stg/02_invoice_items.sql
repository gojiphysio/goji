-- stg.invoice_items
--
-- One row per invoice line item, with the booking-vs-revenue classification
-- baked in. This is the workhorse view: both marts.fct_invoice_line and
-- marts.fct_service_delivered read from here.
--
-- Classification rules (per architecture/schema.md "Deriving service delivery"):
--   redemption   item.others.redeem_from IS NOT NULL
--                booking_amount    = 0
--                recognised_amount = SUM(others.redeem_alloc[].value)
--
--   package_sale item.inventory = 'package' AND no redeem_from
--                booking_amount    = sub_total
--                recognised_amount = 0  (recognised later as sessions burn)
--
--   sale         everything else (single-use consults, products, etc.)
--                booking_amount    = sub_total
--                recognised_amount = sub_total  (collapse on same day)
--
-- Voided invoices are excluded.

CREATE OR REPLACE VIEW `goji-bi.stg.invoice_items` AS
SELECT
  -- Invoice context
  inv.invoice_id,
  inv.invoice_date,
  inv.patient_id,
  inv.location_id,
  inv.clinician_id,
  inv.status                                    AS invoice_status,
  inv.is_void,
  inv.is_finalized,
  inv.finalized_at,

  -- Line position + identity
  CAST(item_idx AS INT64)                       AS line_idx,
  JSON_VALUE(item, '$.item_id')                 AS item_id,
  JSON_VALUE(item, '$.given_id')                AS item_given_id,
  JSON_VALUE(item, '$.name')                    AS item_name,
  JSON_VALUE(item, '$.inventory')               AS inventory_type,

  -- Quantities + money on the line itself
  SAFE_CAST(JSON_VALUE(item, '$.qty')           AS NUMERIC) AS qty,
  SAFE_CAST(JSON_VALUE(item, '$.selling_price') AS NUMERIC) AS unit_price,
  SAFE_CAST(JSON_VALUE(item, '$.discount')      AS NUMERIC) AS discount,
  SAFE_CAST(JSON_VALUE(item, '$.sub_total')     AS NUMERIC) AS line_sub_total,
  SAFE_CAST(JSON_VALUE(item, '$.tax')           AS NUMERIC) AS line_tax,

  -- Redemption linkage (NULL except for redemption rows)
  JSON_VALUE(item, '$.others.redeem_from')      AS redeem_from_invoice_id,
  JSON_QUERY_ARRAY(item, '$.others.redeem_alloc') AS redeem_alloc,

  -- Classification
  CASE
    WHEN JSON_VALUE(item, '$.others.redeem_from') IS NOT NULL THEN 'redemption'
    WHEN JSON_VALUE(item, '$.inventory') = 'package'           THEN 'package_sale'
    ELSE 'sale'
  END                                            AS classification,

  -- Booking amount: zero for redemptions, sub_total (or qty*price) for the rest
  CASE
    WHEN JSON_VALUE(item, '$.others.redeem_from') IS NOT NULL THEN CAST(0 AS NUMERIC)
    ELSE COALESCE(
      SAFE_CAST(JSON_VALUE(item, '$.sub_total') AS NUMERIC),
      SAFE_CAST(JSON_VALUE(item, '$.selling_price') AS NUMERIC)
        * COALESCE(SAFE_CAST(JSON_VALUE(item, '$.qty') AS NUMERIC), 1)
    )
  END                                            AS booking_amount,

  -- Recognised amount: sum of redeem_alloc.value for redemptions, sub_total
  -- for single-use sales, zero for package sales.
  CASE
    WHEN JSON_VALUE(item, '$.others.redeem_from') IS NOT NULL THEN (
      SELECT SUM(SAFE_CAST(JSON_VALUE(alloc, '$.value') AS NUMERIC))
      FROM UNNEST(JSON_QUERY_ARRAY(item, '$.others.redeem_alloc')) AS alloc
    )
    WHEN JSON_VALUE(item, '$.inventory') = 'package' THEN CAST(0 AS NUMERIC)
    ELSE COALESCE(
      SAFE_CAST(JSON_VALUE(item, '$.sub_total') AS NUMERIC),
      SAFE_CAST(JSON_VALUE(item, '$.selling_price') AS NUMERIC)
        * COALESCE(SAFE_CAST(JSON_VALUE(item, '$.qty') AS NUMERIC), 1)
    )
  END                                            AS recognised_amount,

  -- Full line payload retained for anything we haven't surfaced
  item                                           AS item_payload

FROM `goji-bi.stg.invoices` inv,
  UNNEST(JSON_QUERY_ARRAY(inv.payload, '$.item')) AS item WITH OFFSET item_idx
WHERE NOT COALESCE(inv.is_void, FALSE);
