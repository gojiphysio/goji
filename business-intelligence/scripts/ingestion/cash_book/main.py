#!/usr/bin/env python3
"""
Cloud Run Job: snapshot the Cash Book Google Sheet into raw_cashbook.cash_book_raw.

The Cash Book is the hand-kept ledger of every bank movement, and the source of
the P&L's cost lines. Rows have no stable id and get edited and deleted, so each
run appends the whole sheet under one _loaded_at and stg.cash_book reads only the
latest snapshot. That is what makes a corrected or deleted row flow through.

Only numbers, dates, the P&L line and a credit source type are loaded. The
Counterpart and Purpose columns are never stored: the credit side holds patient
names, and marts.dim_patient_contact is the one sanctioned PII table.

Auth: the job's own service account via ADC. Share the sheet read-only with
ingestion-sa@, so there is no secret to mint, store or rotate.

Env vars:
  CASH_BOOK_SHEET_ID  Google Sheet id                 (required)
  CASH_BOOK_TAB       Tab name                        default: In/Out
  BQ_PROJECT          Target BQ project               default: goji-bi
  BQ_DATASET          Target dataset                  default: raw_cashbook
  BQ_TABLE            Target table                    default: cash_book_raw

Exit codes: 0 on success, 1 on config error, 2 on BQ failure, 3 on Sheets failure.
"""
from __future__ import annotations

import logging
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

from google.cloud import bigquery

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("cash-book-ingest")

SHEETS_BASE = "https://sheets.googleapis.com/v4/spreadsheets"
TIMEOUT_S = 30
# Google Sheets date serials count days from this epoch.
SHEETS_EPOCH = date(1899, 12, 30)

REQUIRED_HEADERS = ("date", "debit", "credit", "balance", "p&l line",
                    "covers from", "covers to")


class SheetFormatError(Exception):
    """The sheet no longer has the shape this job reads."""


def env(name: str, default: str | None = None, required: bool = True) -> str:
    v = os.environ.get(name, default)
    if required and not v:
        log.error(f"missing env var: {name}")
        sys.exit(1)
    return v  # type: ignore[return-value]


def parse_amount(value) -> float | None:
    """Parse a money cell: 1000, '$ 1,000.00', '(15.00)', ''. None if unreadable."""
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = re.sub(r"[$,\s]", "", str(value))
    if not text:
        return 0.0
    negative = text.startswith("(") and text.endswith(")")
    cleaned = text.strip("()")
    if not cleaned:
        return 0.0
    try:
        amount = float(cleaned)
    except ValueError:
        return None
    return -amount if negative else amount


def parse_date(value, fallback_year: int | None = None) -> date | None:
    """Parse a date cell: a Sheets serial, '11 Jan 2026', or '2026-01-11'.

    A date typed without a year ('2 Nov') takes fallback_year, the year of the
    row above, since the ledger runs in date order. None if unreadable.
    """
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return SHEETS_EPOCH + timedelta(days=int(value))
    text = str(value).strip()
    for fmt in ("%d %b %Y", "%d %B %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    if fallback_year:
        for fmt in ("%d %b", "%d %B"):
            try:
                return datetime.strptime(f"{text} {fallback_year}", f"{fmt} %Y").date()
            except ValueError:
                continue
    return None


def credit_source(line: str | None, purpose: str) -> str:
    """Classify a credit without keeping its text, which may be a patient's name."""
    if line == "Financing":
        return "financing"
    if line == "Non-operating":
        return "non_operating"
    if line:
        return "cost_refund"
    if "plato" in purpose.lower():
        return "plato_payout"
    return "direct_payment"


def _find_columns(values: list[list]) -> tuple[int, dict[str, int]]:
    """Locate the header row and map column names to indexes.

    Read by header name so a column moved or inserted by hand can't silently
    shift the numbers. There are two 'Purpose' columns; the credit one is the
    first after 'Credit'.
    """
    for i, row in enumerate(values):
        names = [str(c).strip().lower() for c in row]
        if "date" in names and "debit" in names and "credit" in names:
            missing = [h for h in REQUIRED_HEADERS if h not in names]
            if missing:
                raise SheetFormatError(f"missing headers: {missing}")
            cols = {h: names.index(h) for h in REQUIRED_HEADERS}
            credit_at = cols["credit"]
            after_credit = names[credit_at + 1:]
            if "purpose" not in after_credit:
                raise SheetFormatError("no Purpose column after Credit")
            cols["credit purpose"] = credit_at + 1 + after_credit.index("purpose")
            return i, cols
    raise SheetFormatError("no header row with Date, Debit and Credit")


def _cell(row: list, index: int):
    return row[index] if index < len(row) else ""


def extract_rows(values: list[list], loaded_at: str) -> list[dict]:
    """Turn the sheet's cells into raw rows. Pure, so tests need no network.

    Only rows with an amount are kept, which skips the running-balance filler
    below the last entry. A row whose date or amount can't be read is kept with
    parse_issue set rather than dropped, so the P&L reconciliation shows it.
    """
    header_at, cols = _find_columns(values)
    totals = values[header_at - 1] if header_at > 0 else []
    total_debit = parse_amount(_cell(totals, cols["debit"]))
    total_credit = parse_amount(_cell(totals, cols["credit"]))
    balance = parse_amount(_cell(totals, cols["balance"]))

    rows: list[dict] = []
    last_year: int | None = None
    for i, row in enumerate(values[header_at + 1:], start=header_at + 2):
        debit = parse_amount(_cell(row, cols["debit"]))
        credit = parse_amount(_cell(row, cols["credit"]))
        if debit == 0 and credit == 0:
            continue

        entry_date = parse_date(_cell(row, cols["date"]), fallback_year=last_year)
        if entry_date:
            last_year = entry_date.year
        issue = None
        if entry_date is None:
            issue = "bad_date"
        if debit is None or credit is None:
            issue = "bad_amount"

        line = str(_cell(row, cols["p&l line"])).strip() or None
        rows.append({
            "_loaded_at": loaded_at,
            "sheet_row": i,
            "entry_date": entry_date.isoformat() if entry_date else None,
            "debit": debit or 0.0,
            "credit": credit or 0.0,
            "pnl_line": line,
            "covers_from": _iso(parse_date(_cell(row, cols["covers from"]))),
            "covers_to": _iso(parse_date(_cell(row, cols["covers to"]))),
            "source_type": (credit_source(line, str(_cell(row, cols["credit purpose"])))
                            if credit else None),
            "parse_issue": issue,
            "sheet_total_debit": total_debit,
            "sheet_total_credit": total_credit,
            "sheet_balance": balance,
        })
    return rows


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


def fetch_values(sheet_id: str, tab: str) -> list[list]:
    """Read the tab's cells. UNFORMATTED_VALUE returns real dates as serials."""
    import google.auth
    from google.auth.transport.requests import AuthorizedSession

    creds, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    session = AuthorizedSession(creds)
    r = session.get(
        f"{SHEETS_BASE}/{sheet_id}/values/{quote(tab, safe='')}",
        params={"valueRenderOption": "UNFORMATTED_VALUE",
                "dateTimeRenderOption": "SERIAL_NUMBER"},
        timeout=TIMEOUT_S,
    )
    r.raise_for_status()
    return r.json().get("values", [])


def main() -> None:
    sheet_id = env("CASH_BOOK_SHEET_ID")
    tab = env("CASH_BOOK_TAB", "In/Out", required=False)
    bq_project = env("BQ_PROJECT", "goji-bi", required=False)
    bq_dataset = env("BQ_DATASET", "raw_cashbook", required=False)
    bq_table = env("BQ_TABLE", "cash_book_raw", required=False)

    table_ref = f"{bq_project}.{bq_dataset}.{bq_table}"
    loaded_at_iso = datetime.now(timezone.utc).isoformat()
    log.info(f"tab={tab} target={table_ref}")

    try:
        rows = extract_rows(fetch_values(sheet_id, tab), loaded_at_iso)
    except SheetFormatError as e:
        log.error(f"cash book format changed, nothing loaded: {e}")
        sys.exit(3)
    except Exception as e:
        log.exception(f"sheet read failed: {e}")
        sys.exit(3)

    # An empty read must not become the latest snapshot and blank the P&L.
    if not rows:
        log.error("sheet returned no rows, nothing loaded")
        sys.exit(3)

    issues = [r["sheet_row"] for r in rows if r["parse_issue"]]
    if issues:
        log.warning(f"rows with unreadable cells: {issues}")

    log.info(f"loading {len(rows)} rows into {table_ref}")
    try:
        bq = bigquery.Client(project=bq_project)
        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
            schema=[
                bigquery.SchemaField("_loaded_at", "TIMESTAMP", mode="REQUIRED"),
                bigquery.SchemaField("sheet_row", "INT64", mode="REQUIRED"),
                bigquery.SchemaField("entry_date", "DATE"),
                bigquery.SchemaField("debit", "FLOAT64", mode="REQUIRED"),
                bigquery.SchemaField("credit", "FLOAT64", mode="REQUIRED"),
                bigquery.SchemaField("pnl_line", "STRING"),
                bigquery.SchemaField("covers_from", "DATE"),
                bigquery.SchemaField("covers_to", "DATE"),
                bigquery.SchemaField("source_type", "STRING"),
                bigquery.SchemaField("parse_issue", "STRING"),
                bigquery.SchemaField("sheet_total_debit", "FLOAT64"),
                bigquery.SchemaField("sheet_total_credit", "FLOAT64"),
                bigquery.SchemaField("sheet_balance", "FLOAT64"),
            ],
        )
        bq.load_table_from_json(rows, table_ref, job_config=job_config).result()
    except Exception as e:
        log.exception(f"bq load failed: {e}")
        sys.exit(2)
    log.info("done")


if __name__ == "__main__":
    main()
