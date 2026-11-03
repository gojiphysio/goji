"""Unit tests for the Cash Book P&L: the pure assembly in build_pnl, the access
boundary on its route, and the Excel export. No BigQuery.

Run from scripts/dashboard/:  python -m pytest tests/ -q
"""
from __future__ import annotations

import base64
import importlib
import io
import os
from datetime import date

import pytest
from openpyxl import load_workbook

os.environ.setdefault("DASHBOARD_USER", "founder")
os.environ.setdefault("DASHBOARD_PASS", "founder-pw")
os.environ.setdefault("STAFF_USER", "frontdesk")
os.environ.setdefault("STAFF_PASS", "staff-pw")

app = importlib.import_module("app")

TODAY = date(2026, 11, 4)
SUMMARY = {
    "sheet_total_debit": 100.0, "sheet_total_credit": 200.0, "sheet_balance": 100.0,
    "book_debit": 100.0, "book_credit": 200.0, "as_of": "2026-11-03",
    "uncategorised_count": 0, "uncategorised_amount": 0, "unreadable_rows": 0,
}


def line(month, name, amount, in_ebitda=True):
    return {"month": f"{month}-01", "line": name, "in_ebitda": in_ebitda, "amount": amount}


def rev(month, recognised=0.0, **kw):
    return {"month": f"{month}-01", "recognised": recognised, "visits": 100, **kw}


def closed_lines(month, payroll=1000.0, cpf=200.0, rent=500.0, **extra):
    rows = [line(month, "Payroll", payroll), line(month, "CPF", cpf), line(month, "Rent", rent)]
    return rows + [line(month, k.replace("_", " "), v) for k, v in extra.items()]


def by_month(result):
    return {m["month"]: m for m in result["months"]}


def test_no_rows_is_unavailable():
    assert app.build_pnl([], [], {}, TODAY) == {"available": False}


def test_ebitda_is_revenue_minus_all_lines():
    r = app.build_pnl(closed_lines("2026-09", Ads=300.0), [rev("2026-09", 5000.0)], SUMMARY, TODAY)
    m = by_month(r)["2026-09"]
    assert m["total_costs"] == 2000.0
    assert m["ebitda"] == 3000.0
    assert m["margin"] == pytest.approx(0.6)


def test_card_fees_are_a_cost_even_though_absent_from_the_cash_book():
    r = app.build_pnl(closed_lines("2026-09"), [rev("2026-09", 5000.0, card_fees=100.0)], SUMMARY, TODAY)
    m = by_month(r)["2026-09"]
    assert m["lines"]["Card fees"] == 100.0
    assert m["ebitda"] == 5000.0 - 1700.0 - 100.0


def test_month_missing_payroll_is_provisional_and_not_the_headline():
    rows = closed_lines("2026-09") + [line("2026-10", "Rent", 500.0), line("2026-10", "CPF", 200.0)]
    r = app.build_pnl(rows, [rev("2026-09", 5000.0), rev("2026-10", 6000.0)], SUMMARY, TODAY)
    oct_ = by_month(r)["2026-10"]
    assert oct_["status"] == "provisional"
    assert oct_["missing"] == ["Payroll"]
    assert r["latest_closed"] == "2026-09"


def test_month_not_yet_ended_is_provisional_even_with_all_lines():
    r = app.build_pnl(closed_lines("2026-09") + closed_lines("2026-11"),
                      [rev("2026-09", 1.0), rev("2026-11", 1.0)], SUMMARY, TODAY)
    assert by_month(r)["2026-11"]["status"] == "provisional"
    assert r["latest_closed"] == "2026-09"


def test_starts_at_first_closed_month_dropping_pre_opening():
    rows = [line("2026-04", "Payroll", 3148.31)] + closed_lines("2026-05")
    r = app.build_pnl(rows, [rev("2026-04", 7524.0), rev("2026-05", 24218.0)], SUMMARY, TODAY)
    assert [m["month"] for m in r["months"]] == ["2026-05"]


def test_future_months_from_annual_spreads_are_dropped():
    rows = closed_lines("2026-09") + [line("2027-03", "Insurance", 10.0)]
    r = app.build_pnl(rows, [rev("2026-09", 1.0)], SUMMARY, TODAY)
    assert [m["month"] for m in r["months"]] == ["2026-09"]


def test_unbilled_utilities_carry_prior_month_and_are_labelled():
    rows = closed_lines("2026-09", Utilities=511.32) + closed_lines("2026-10")
    r = app.build_pnl(rows, [rev("2026-09", 1.0), rev("2026-10", 1.0)], SUMMARY, TODAY)
    oct_ = by_month(r)["2026-10"]
    assert oct_["lines"]["Utilities"] == 511.32
    assert oct_["estimated"] == ["Utilities"]
    assert by_month(r)["2026-09"]["estimated"] == []


def test_utilities_are_not_estimated_with_no_prior_bill():
    r = app.build_pnl(closed_lines("2026-05"), [rev("2026-05", 1.0)], SUMMARY, TODAY)
    assert "Utilities" not in by_month(r)["2026-05"]["lines"]


def test_uncategorised_rows_count_as_cost_and_are_reported():
    rows = closed_lines("2026-09", Uncategorised=50.0)
    summary = {**SUMMARY, "uncategorised_count": 2, "uncategorised_amount": 50.0}
    r = app.build_pnl(rows, [rev("2026-09", 1000.0)], summary, TODAY)
    assert by_month(r)["2026-09"]["total_costs"] == 1750.0
    assert r["checks"]["uncategorised_count"] == 2
    assert r["checks"]["uncategorised_amount"] == 50.0


def test_reconciliation_flags_a_gap_to_the_sheet_totals():
    ok = app.build_pnl(closed_lines("2026-09"), [], SUMMARY, TODAY)
    assert ok["checks"]["reconciled"] is True
    bad = app.build_pnl(closed_lines("2026-09"), [], {**SUMMARY, "book_credit": 198.0}, TODAY)
    assert bad["checks"]["reconciled"] is False
    assert bad["checks"]["credit_gap"] == 2.0


def test_below_ebitda_lines_never_reach_costs():
    rows = closed_lines("2026-09") + [
        line("2026-09", "Capex", 1000.0, False),
        line("2026-09", "Deposit", 500.0, False),
        line("2026-09", "Financing", -225000.0, False),
    ]
    r = app.build_pnl(rows, [rev("2026-09", 1.0)], SUMMARY, TODAY)
    assert by_month(r)["2026-09"]["total_costs"] == 1700.0
    assert r["capex_total"] == 1000.0
    assert r["deposits_total"] == 500.0
    assert r["loans_outstanding"] == 225000.0


def test_trailing_3m_needs_three_closed_months():
    rows = closed_lines("2026-07") + closed_lines("2026-08") + closed_lines("2026-09")
    revs = [rev("2026-07", 2700.0), rev("2026-08", 2700.0), rev("2026-09", 2700.0)]
    months = by_month(app.build_pnl(rows, revs, SUMMARY, TODAY))
    assert months["2026-08"]["trailing_3m_ebitda"] is None
    assert months["2026-09"]["trailing_3m_ebitda"] == 3000.0


def test_trailing_3m_is_none_when_a_month_in_the_window_is_provisional():
    rows = (closed_lines("2026-07") + closed_lines("2026-08") + closed_lines("2026-09")
            + [line("2026-10", "Rent", 500.0)])
    revs = [rev(m, 2700.0) for m in ("2026-07", "2026-08", "2026-09", "2026-10")]
    assert by_month(app.build_pnl(rows, revs, SUMMARY, TODAY))["2026-10"]["trailing_3m_ebitda"] is None


def test_ratios_and_break_even():
    r = app.build_pnl(closed_lines("2026-10", payroll=28972.72, cpf=10788.0, rent=10598.07),
                      [{"month": "2026-10-01", "recognised": 60671.4, "visits": 241}], SUMMARY, TODAY)
    m = by_month(r)["2026-10"]
    assert m["staff_pct"] == pytest.approx(0.655, abs=0.001)
    assert m["staff_rent_pct"] == pytest.approx(0.830, abs=0.001)
    assert m["revenue_per_visit"] == pytest.approx(251.75, abs=0.01)
    assert m["breakeven_visits"] == pytest.approx(m["total_costs"] / 251.75, abs=0.01)


def test_zero_revenue_month_has_no_ratios_rather_than_crashing():
    m = by_month(app.build_pnl(closed_lines("2026-09"), [], SUMMARY, TODAY))["2026-09"]
    assert m["margin"] is None and m["staff_pct"] is None and m["breakeven_visits"] is None


def test_deferred_accumulates_from_before_the_first_shown_month():
    rows = [line("2026-04", "Payroll", 1.0)] + closed_lines("2026-05") + closed_lines("2026-06")
    revs = [rev("2026-04", package_sold=100.0, package_burned=10.0),
            rev("2026-05", package_sold=50.0, package_burned=20.0),
            rev("2026-06", package_sold=0.0, package_burned=30.0)]
    months = by_month(app.build_pnl(rows, revs, SUMMARY, TODAY))
    assert months["2026-05"]["deferred"] == 120.0
    assert months["2026-06"]["deferred"] == 90.0


def test_month_end_handles_month_lengths_and_year_end():
    assert app._month_end("2026-02") == date(2026, 2, 28)
    assert app._month_end("2028-02") == date(2028, 2, 29)
    assert app._month_end("2026-12") == date(2026, 12, 31)


def test_fetch_degrades_when_tables_are_missing(monkeypatch):
    def boom(_sql):
        raise RuntimeError("Not found: Table goji-bi:marts.fct_pnl_monthly")
    monkeypatch.setattr(app, "_query", boom)
    monkeypatch.setattr(app, "_disk_cache_get", lambda _key: None)
    app._cache.pop("pnl_monthly", None)
    assert app.fetch_pnl_monthly() == {"available": False}


def basic_auth(user, password):
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(app, "fetch_pnl_monthly", lambda: {"available": False})
    return app.app.test_client()


def test_route_allows_founder(client):
    assert client.get("/api/pnl_monthly", headers=basic_auth("founder", "founder-pw")).status_code == 200


def test_route_rejects_staff(client):
    assert client.get("/api/pnl_monthly", headers=basic_auth("frontdesk", "staff-pw")).status_code == 401


def test_route_rejects_anonymous(client):
    assert client.get("/api/pnl_monthly").status_code == 401


@pytest.mark.parametrize("mode", ["frontdesk", "links"])
def test_route_does_not_exist_on_other_subdomains(client, monkeypatch, mode):
    monkeypatch.setattr(app, "APP_MODE", mode)
    assert client.get("/api/pnl_monthly", headers=basic_auth("founder", "founder-pw")).status_code == 404


def test_excel_export_carries_the_real_lines():
    blob = app._xlsx_pl_statement({
        "period": {"label": "Oct 2026", "start": "2026-10-01", "end": "2026-10-31", "days": 31},
        "view": "cash",
        "revenue": 60671.4,
        "groups": [
            {"name": "Staff", "lines": [{"name": "Payroll", "amount": 28972.72},
                                        {"name": "CPF", "amount": 10788.0}]},
            {"name": "Clinic ops", "lines": [{"name": "Card fees", "amount": 1040.58}]},
        ],
    })
    ws = load_workbook(io.BytesIO(blob)).active
    cells = {str(r[0].value).strip(): r for r in ws.iter_rows() if r[0].value}
    assert cells["Payroll"][1].value == 28972.72
    assert cells["Card fees"][1].value == 1040.58
    assert cells["Total operating expenses"][2].value == pytest.approx(40801.30)
    assert cells["Operating profit / (loss) — EBITDA"][2].value == pytest.approx(19870.10)
