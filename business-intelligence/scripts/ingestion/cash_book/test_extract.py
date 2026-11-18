"""Unit tests for the cash_book parsers. Pure — no network / no BQ."""
from datetime import date

import pytest

from main import SheetFormatError, credit_source, extract_rows, parse_amount, parse_date

HEADER = ["", "Date", "Counterpart", "Debit", "Purpose", "Credit", "Purpose",
          "Balance", "Status", "Logged by", "", "P&L line", "Covers from", "Covers to"]
TOTALS = ["", "", "", 100.0, "", 330.0, "", 230.0]
LOADED_AT = "2026-11-03T00:00:00+00:00"


def sheet(*rows):
    return [["Cash Book for Goji Health Pte Ltd"], [], TOTALS, HEADER, *rows]


def test_parse_amount_handles_numbers_and_text():
    assert parse_amount(1000) == 1000.0
    assert parse_amount("$ 1,000.00") == 1000.0
    assert parse_amount("$ (15.00)") == -15.0
    assert parse_amount("(15.00)") == -15.0
    assert parse_amount("") == 0.0
    assert parse_amount(None) == 0.0


def test_parse_amount_unreadable_is_none():
    assert parse_amount("n/a") is None


def test_parse_date_serial_and_text():
    assert parse_date(46336) == date(2026, 11, 10)
    assert parse_date("11 Jan 2026") == date(2026, 1, 11)
    assert parse_date("2026-01-11") == date(2026, 1, 11)


def test_parse_date_without_year_takes_fallback():
    assert parse_date("2 Nov", fallback_year=2026) == date(2026, 11, 2)


def test_parse_date_without_year_and_no_fallback_is_none():
    assert parse_date("2 Nov") is None


def test_row_without_year_inherits_year_from_row_above():
    rows = extract_rows(sheet(
        ["", "31 Oct 2026", "DBS", 10, "Account Fee", "", "", "", "", "", "", "Bank fees"],
        ["", "2 Nov", "", "", "", 2000, "IRAS", "", "", "", "", "Non-operating"],
    ), LOADED_AT)
    assert rows[1]["entry_date"] == "2026-11-02"
    assert rows[1]["parse_issue"] is None


def test_columns_are_read_by_header_name_not_position():
    moved = ["", "Date", "Debit", "Credit", "Purpose", "Balance",
             "P&L line", "Covers from", "Covers to"]
    rows = extract_rows([
        ["", "", 10, 0, "", 0], moved,
        ["", "1 May 2026", 10, "", "", "", "Rent"],
    ], LOADED_AT)
    assert rows[0]["debit"] == 10.0
    assert rows[0]["pnl_line"] == "Rent"


def test_missing_required_header_raises():
    bad = [h for h in HEADER if h != "P&L line"]
    with pytest.raises(SheetFormatError):
        extract_rows([TOTALS, bad], LOADED_AT)


def test_no_header_row_raises():
    with pytest.raises(SheetFormatError):
        extract_rows([["nothing", "here"]], LOADED_AT)


def test_covers_dates_and_totals_are_carried():
    rows = extract_rows(sheet(
        ["", "3 Jun 2026", "Goji Team", 18889.83, "GIRO Payroll - May", "", "", "", "", "", "",
         "Payroll", "2026-04-26", "2026-05-25"],
    ), LOADED_AT)
    assert rows[0]["covers_from"] == "2026-04-26"
    assert rows[0]["covers_to"] == "2026-05-25"
    assert rows[0]["sheet_row"] == 5
    assert rows[0]["sheet_total_debit"] == 100.0
    assert rows[0]["sheet_total_credit"] == 330.0
    assert rows[0]["sheet_balance"] == 230.0


def test_balance_filler_rows_are_skipped():
    rows = extract_rows(sheet(
        ["", "1 May 2026", "", 10, "Fee", "", "", "", "", "", "", "Bank fees"],
        ["", "", "", "", "", "", "", 7362.89],
    ), LOADED_AT)
    assert len(rows) == 1


def test_unreadable_date_is_kept_and_flagged():
    rows = extract_rows(sheet(
        ["", "sometime", "", 10, "Fee", "", "", "", "", "", "", "Bank fees"],
    ), LOADED_AT)
    assert rows[0]["entry_date"] is None
    assert rows[0]["parse_issue"] == "bad_date"


def test_unreadable_amount_is_kept_and_flagged():
    rows = extract_rows(sheet(
        ["", "1 May 2026", "", "tbc", "Fee", 10, "x"],
    ), LOADED_AT)
    assert rows[0]["parse_issue"] == "bad_amount"


@pytest.mark.parametrize("line,purpose,expected", [
    ("Financing", "Shareholder Loan", "financing"),
    ("Non-operating", "IRAS", "non_operating"),
    ("Rent", "Landlord refund", "cost_refund"),
    (None, "Plato Disbursement", "plato_payout"),
    (None, "Soh Gek Yen Iris", "direct_payment"),
])
def test_credit_source(line, purpose, expected):
    assert credit_source(line, purpose) == expected


def test_patient_names_and_free_text_never_reach_output_rows():
    rows = extract_rows(sheet(
        ["", "1 Aug 2026", "Some Counterpart", "", "", 330, "Soh Gek Yen Iris", "", "Done", "Cheryl"],
        ["", "2 Aug 2026", "Lim Jia Wei", 50, "Refund to Lim Jia Wei", "", "", "", "Done", "Chris",
         "No receipt.", "Other"],
    ), LOADED_AT)
    blob = repr(rows)
    for text in ("Soh Gek", "Iris", "Lim Jia", "Counterpart", "Refund", "Cheryl", "Chris", "receipt"):
        assert text not in blob
    assert rows[0]["source_type"] == "direct_payment"


def test_output_columns_are_the_pii_free_set():
    rows = extract_rows(sheet(["", "1 May 2026", "", 10, "Fee"]), LOADED_AT)
    assert set(rows[0]) == {
        "_loaded_at", "sheet_row", "entry_date", "debit", "credit", "pnl_line",
        "covers_from", "covers_to", "source_type", "parse_issue",
        "sheet_total_debit", "sheet_total_credit", "sheet_balance",
    }
