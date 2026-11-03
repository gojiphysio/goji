-- marts.fct_cash_book
--
-- Thin fact: one row per Cash Book entry with its P&L line resolved and the
-- period it pays for filled in. Grain and row order match the sheet.
--
-- Rules the P&L depends on:
--   - A debit with a blank or unrecognised line becomes 'Uncategorised'. It
--     still counts as a cost, so a missed dropdown overstates cost rather than
--     hiding it, and the page warns with the count and amount.
--   - A credit with no line is a patient receipt, not a cost, so it stays NULL.
--   - Blank covers dates mean the calendar month of entry_date. Bad covers dates
--     (to before from) also fall back to that month.

CREATE OR REPLACE VIEW `goji-bi.marts.fct_cash_book` AS
WITH resolved AS (
  SELECT
    *,
    CASE
      WHEN pnl_line IN (
        'Payroll', 'CPF', 'Rent', 'Utilities', 'Ads', 'Printing',
        'Clinical supplies', 'Laundry & cleaning', 'Training',
        'Staff meals & events', 'Software', 'Insurance', 'Bank fees',
        'Professional fees', 'Other', 'Capex', 'Deposit', 'Financing',
        'Non-operating'
      ) THEN pnl_line
      WHEN debit <> 0 THEN 'Uncategorised'
    END AS line
  FROM `goji-bi.stg.cash_book`
)
SELECT
  _loaded_at,
  sheet_row,
  entry_date,
  debit,
  credit,
  line,
  source_type,
  parse_issue,
  IF(covers_from IS NOT NULL AND COALESCE(covers_to, LAST_DAY(covers_from)) >= covers_from,
     covers_from, DATE_TRUNC(entry_date, MONTH)) AS covers_from,
  IF(covers_from IS NOT NULL AND COALESCE(covers_to, LAST_DAY(covers_from)) >= covers_from,
     COALESCE(covers_to, LAST_DAY(covers_from)), LAST_DAY(entry_date)) AS covers_to,
  sheet_total_debit,
  sheet_total_credit,
  sheet_balance
FROM resolved;
