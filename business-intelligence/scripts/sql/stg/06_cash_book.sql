-- stg.cash_book
--
-- The latest snapshot of the Cash Book sheet, from the append-only
-- raw_cashbook.cash_book_raw landing table.
--
-- "Latest" is the whole newest _loaded_at, NOT latest per key as in the other
-- stg views. Sheet rows have no stable id, and a row deleted by hand must
-- disappear, so only a full snapshot tells the truth.
--
-- Read this view, never read raw_cashbook.cash_book_raw directly from marts.

CREATE OR REPLACE VIEW `goji-bi.stg.cash_book` AS
SELECT
  _loaded_at,
  sheet_row,
  entry_date,
  debit,
  credit,
  NULLIF(TRIM(pnl_line), '') AS pnl_line,
  covers_from,
  covers_to,
  source_type,
  parse_issue,
  sheet_total_debit,
  sheet_total_credit,
  sheet_balance
FROM `goji-bi.raw_cashbook.cash_book_raw`
WHERE _loaded_at = (SELECT MAX(_loaded_at) FROM `goji-bi.raw_cashbook.cash_book_raw`);
