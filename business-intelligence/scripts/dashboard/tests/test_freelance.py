"""Freelancer per-session pay (Camille Tan, ICT): session classification, fees,
and the Freelancer fees Cash Book line in the P&L. No BigQuery.

Run from scripts/dashboard/:  python -m pytest tests/ -q
"""
from __future__ import annotations

import importlib
import os
from datetime import date

import pytest

os.environ.setdefault("DASHBOARD_USER", "founder")
os.environ.setdefault("DASHBOARD_PASS", "founder-pw")
os.environ.setdefault("STAFF_USER", "frontdesk")
os.environ.setdefault("STAFF_PASS", "staff-pw")

app = importlib.import_module("app")


@pytest.mark.parametrize("sku", ["CP2:1", "PP2:1", "PP2:1-5OP", "PP2:1-1IP", "CP2:1-10", "GJCPSC_2:1_AC"])
def test_two_to_one_skus(sku):
    assert app.session_type(sku) == "2:1"


@pytest.mark.parametrize("sku", ["PHY-INIT", "MB-60", "CorpPT", "CP1:1", "PP1:1-5OP", "PP1:1-10OP", "SC-60", "HV-90",
                                 "GJCPSC_1:1_10P", "GJCPSC_1:1_5P", "GJCPSC_1:1_AC"])
def test_one_to_one_skus(sku):
    assert app.session_type(sku) == "1:1"


@pytest.mark.parametrize("sku", [None, "", "GJGL-G-001", "PP0001", "Late-fee", "EW_GJ_002", "GJ-INV-002"])
def test_unknown_skus_are_not_sessions(sku):
    assert app.session_type(sku) == "other"


def test_camille_rates():
    assert app.PROVIDERS["ICT"] == "Camille Tan"
    assert app.freelance_fee("ICT", "1:1") == 60.0
    assert app.freelance_fee("ICT", "2:1") == 70.0
    assert app.freelance_fee("ICT", "other") == 0.0


def test_salaried_clinicians_earn_no_session_fee():
    for cid in ("PCL", "PCN", "PKN"):
        assert cid not in app.FREELANCE_RATES
        assert app.freelance_fee(cid, "1:1") == 0.0


def test_freelancer_fees_are_a_staff_cost_in_the_pnl():
    lines = [
        {"month": "2026-11-01", "line": name, "in_ebitda": True, "amount": amount}
        for name, amount in [("Payroll", 1000.0), ("CPF", 200.0), ("Rent", 500.0),
                             ("Freelancer fees", 300.0)]
    ]
    revenue = [{"month": "2026-11-01", "recognised": 5000.0, "visits": 100}]
    r = app.build_pnl(lines, revenue, {}, date(2026, 12, 4))
    m = r["months"][0]
    assert m["total_costs"] == 2000.0
    assert m["staff_pct"] == pytest.approx(1500.0 / 5000.0)
    staff = next(g for g in app.PNL_GROUPS if g[0] == "Staff")
    assert "Freelancer fees" in staff[1]
