-- marts.fct_invoice_line
--
-- THE BOOKING FACT. Grain: one row per invoice line item that represents
-- money coming in (a sale or a package sale). Redemption lines live in
-- fct_service_delivered, not here.
--
-- For 'sale' items (single-use consults, products), booking == recognised
-- on the same day, so the row also carries recognised_amount > 0. For
-- 'package_sale' items, recognised_amount is 0 and revenue is recognised
-- later through fct_service_delivered as sessions burn.
--
-- Read this from Looker Studio for: bookings $, sales by clinician, package
-- vs single-visit split, average sale value, top-selling items.

CREATE OR REPLACE VIEW `goji-bi.marts.fct_invoice_line` AS
SELECT
  invoice_id,
  line_idx                                AS line_id,
  invoice_date,
  finalized_at                            AS booked_at,
  patient_id,
  clinician_id,
  location_id,

  item_id,
  item_given_id,
  item_name,
  inventory_type,

  qty,
  unit_price,
  discount,
  line_sub_total                          AS line_total,
  line_tax                                AS tax,

  (classification = 'package_sale')       AS is_package_sale,
  invoice_status                          AS status,

  booking_amount,
  recognised_amount
FROM `goji-bi.stg.invoice_items`
WHERE classification IN ('sale', 'package_sale');
