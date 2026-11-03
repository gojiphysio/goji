-- marts.fct_pnl_monthly
--
-- One row per (month, line): what that P&L line cost in that calendar month.
--
-- Each entry is spread evenly across the days it covers, then summed by month.
-- This one rule handles the 26th-to-25th payroll before Aug 2026 (spanning two
-- months), utilities billed a month late, and annual prepayments.
--
-- amount = debit - credit, so a cost refund entered as a credit with a line
-- reduces that line. Patient receipts have no line and are excluded.
--
-- in_ebitda is FALSE for Capex, Deposit, Financing and Non-operating. Card fees
-- are NOT here: Plato nets them out of its payouts so they never reach the Cash
-- Book. The dashboard adds them, from Plato payment data.

CREATE OR REPLACE VIEW `goji-bi.marts.fct_pnl_monthly` AS
WITH spread AS (
  SELECT
    DATE_TRUNC(day, MONTH) AS month,
    line,
    (debit - credit) / (DATE_DIFF(covers_to, covers_from, DAY) + 1) AS amount
  FROM `goji-bi.marts.fct_cash_book`,
    UNNEST(GENERATE_DATE_ARRAY(covers_from, covers_to)) AS day
  WHERE line IS NOT NULL
    AND covers_from IS NOT NULL
)
SELECT
  month,
  line,
  CASE
    WHEN line IN ('Payroll', 'CPF') THEN 'Staff'
    WHEN line IN ('Rent', 'Utilities') THEN 'Occupancy'
    WHEN line IN ('Ads', 'Printing') THEN 'Marketing'
    WHEN line IN ('Clinical supplies', 'Laundry & cleaning') THEN 'Clinic ops'
    WHEN line IN ('Capex', 'Deposit', 'Financing', 'Non-operating') THEN 'Below EBITDA'
    ELSE 'Admin'
  END AS line_group,
  line NOT IN ('Capex', 'Deposit', 'Financing', 'Non-operating') AS in_ebitda,
  ROUND(SUM(amount), 2) AS amount
FROM spread
GROUP BY month, line;
