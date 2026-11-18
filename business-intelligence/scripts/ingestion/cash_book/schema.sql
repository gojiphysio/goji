-- raw_cashbook.cash_book_raw: append-only snapshots of the Cash Book Google Sheet.
-- Run once before deploying the ingestion job and the stg/marts views.
--
-- One row per (sheet_row, _loaded_at). Each run writes the whole sheet, and
-- stg.cash_book reads only the latest _loaded_at, so edited and deleted rows
-- flow through. Rows have no stable id to dedupe on.
--
-- Deliberately has no Counterpart or Purpose column: the sheet's credit side
-- holds patient names, and marts.dim_patient_contact is the one sanctioned PII
-- table. sheet_row traces any figure back to the sheet.

CREATE SCHEMA IF NOT EXISTS `goji-bi.raw_cashbook`
  OPTIONS(location = "asia-southeast1");

CREATE TABLE IF NOT EXISTS `goji-bi.raw_cashbook.cash_book_raw` (
  _loaded_at TIMESTAMP NOT NULL
    OPTIONS(description = "UTC timestamp of the snapshot. All rows of one run share it"),
  sheet_row INT64 NOT NULL
    OPTIONS(description = "1-indexed row in the sheet, to trace a figure back"),
  entry_date DATE
    OPTIONS(description = "Date the money moved. NULL if the cell was unreadable"),
  debit FLOAT64 NOT NULL OPTIONS(description = "Money out"),
  credit FLOAT64 NOT NULL OPTIONS(description = "Money in"),
  pnl_line STRING OPTIONS(description = "The sheet's P&L line dropdown. NULL if blank"),
  covers_from DATE OPTIONS(description = "Start of the period the row pays for, if set"),
  covers_to DATE OPTIONS(description = "End of the period the row pays for, if set"),
  source_type STRING
    OPTIONS(description = "Credits only: plato_payout, direct_payment, financing, non_operating, cost_refund"),
  parse_issue STRING OPTIONS(description = "bad_date or bad_amount if a cell was unreadable"),
  sheet_total_debit FLOAT64 OPTIONS(description = "The sheet's own debit total, for reconciliation"),
  sheet_total_credit FLOAT64 OPTIONS(description = "The sheet's own credit total, for reconciliation"),
  sheet_balance FLOAT64 OPTIONS(description = "The sheet's own closing balance")
)
PARTITION BY DATE(_loaded_at)
OPTIONS(
  description = "Raw snapshots of the Cash Book sheet. Append-only. Latest snapshot wins in stg.cash_book."
);
