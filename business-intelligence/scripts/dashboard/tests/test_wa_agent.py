"""Agent tab (WhatsApp assistant): the fetch_wa_agent_* readers, their wiring
into build_payload and the custom range, and that they degrade to empty while
the marts.wa_agent_* views aren't deployed. No BigQuery: _query is stubbed.

Run from scripts/dashboard/:  python -m pytest tests/ -q
"""
from __future__ import annotations

import base64
import importlib
import os
from datetime import date

import pytest

os.environ.setdefault("DASHBOARD_USER", "founder")
os.environ.setdefault("DASHBOARD_PASS", "founder-pw")
os.environ.setdefault("STAFF_USER", "frontdesk")
os.environ.setdefault("STAFF_PASS", "staff-pw")

app = importlib.import_module("app")

START, END = date(2026, 11, 1), date(2026, 11, 18)
WA_FETCHES = ("fetch_wa_agent_summary", "fetch_wa_agent_outcomes",
              "fetch_wa_agent_weekly", "fetch_wa_agent_autonomy")


def _missing_view(_sql):
    raise RuntimeError("Not found: Table goji-bi:marts.wa_agent_conversations")


SUMMARY_ROW = {
    "conversations": 40, "ended": 32, "open": 8, "agent_success": 20,
    "rescued": 4, "bookings": 9, "median_first_reply_s": 41.6, "cost_usd": 1.2,
    "handled_agent": 25, "handled_agent_then_human": 10, "handled_human": 5,
    "rated_up": 6, "rated_down": 1,
}


# --- degrade to empty --------------------------------------------------------

@pytest.mark.parametrize("name,args,expected", [
    ("fetch_wa_agent_outcomes", (START, END), []),
    ("fetch_wa_agent_weekly", (END,), []),
    ("fetch_wa_agent_autonomy", (), []),
])
def test_list_fetches_degrade_when_views_are_missing(monkeypatch, name, args, expected):
    monkeypatch.setattr(app, "_query", _missing_view)
    assert getattr(app, name)(*args) == expected


def test_summary_degrades_when_view_is_missing(monkeypatch):
    monkeypatch.setattr(app, "_query", _missing_view)
    out = app.fetch_wa_agent_summary(START, END)
    assert out == app._wa_agent_empty()
    assert out["conversations"] == 0
    assert out["success_rate"] is None and out["cost_per_conversation"] is None


def test_summary_with_no_rows_is_empty(monkeypatch):
    monkeypatch.setattr(app, "_query", lambda _sql: [])
    assert app.fetch_wa_agent_summary(START, END) == app._wa_agent_empty()


# --- summary -----------------------------------------------------------------

def test_summary_rates_use_ended_conversations(monkeypatch):
    seen = []
    monkeypatch.setattr(app, "_query", lambda sql: seen.append(sql) or [dict(SUMMARY_ROW)])
    out = app.fetch_wa_agent_summary(START, END)
    assert out["conversations"] == 40
    # 20 pure-agent successes of 32 ended; the 8 open ones are left out.
    assert out["success_rate"] == 62.5
    assert out["rescue_rate"] == 12.5
    assert out["bookings"] == 9
    assert out["median_first_reply_s"] == 41.6
    assert out["cost_per_conversation"] == pytest.approx(0.03)
    assert out["rated_up"] == 6 and out["rated_down"] == 1
    # Ranges are clinic dates and read the conversations view.
    assert "marts.wa_agent_conversations" in seen[0]
    assert "DATE(conversation_start, 'Asia/Singapore') BETWEEN '2026-11-01' AND '2026-11-18'" in seen[0]


def test_summary_with_nothing_ended_has_no_rates(monkeypatch):
    row = dict(SUMMARY_ROW, ended=0, agent_success=0, rescued=0, open=40,
               median_first_reply_s=None)
    monkeypatch.setattr(app, "_query", lambda _sql: [row])
    out = app.fetch_wa_agent_summary(START, END)
    assert out["success_rate"] is None
    assert out["rescue_rate"] is None
    assert out["median_first_reply_s"] is None


def test_summary_with_zero_conversations_has_no_cost_per_conversation(monkeypatch):
    row = {k: 0 for k in SUMMARY_ROW}
    row.update(median_first_reply_s=None, cost_usd=None)
    monkeypatch.setattr(app, "_query", lambda _sql: [row])
    out = app.fetch_wa_agent_summary(START, END)
    assert out["cost_per_conversation"] is None
    assert out["cost_usd"] == 0.0


# --- outcomes, weekly, autonomy ----------------------------------------------

def test_outcomes_keep_any_value_and_drop_empty_rows(monkeypatch):
    monkeypatch.setattr(app, "_query", lambda _sql: [
        {"outcome": "booked", "score": "success", "conversations": 5},
        {"outcome": "unanswered", "score": "failure", "conversations": 2},
        {"outcome": None, "score": None, "conversations": 1},
        {"outcome": "dropped", "score": "soft_failure", "conversations": 0},
    ])
    assert app.fetch_wa_agent_outcomes(START, END) == [
        {"outcome": "booked", "score": "success", "conversations": 5},
        {"outcome": "unanswered", "score": "failure", "conversations": 2},
        {"outcome": "unknown", "score": "open", "conversations": 1},
    ]


def test_weekly_success_rate_per_week(monkeypatch):
    monkeypatch.setattr(app, "_query", lambda _sql: [
        {"week": date(2026, 11, 2), "conversations": 12, "ended": 10, "agent_success": 7},
        {"week": date(2026, 11, 9), "conversations": 3, "ended": 0, "agent_success": 0},
    ])
    weeks = app.fetch_wa_agent_weekly(END)
    assert weeks[0] == {"week": "2026-11-02", "conversations": 12, "ended": 10,
                        "agent_success": 7, "success_rate": 70.0}
    assert weeks[1]["success_rate"] is None


def test_autonomy_shares_and_badges(monkeypatch):
    seen = []
    monkeypatch.setattr(app, "_query", lambda sql: seen.append(sql) or [{
        "intent": "price", "proposals": 40, "auto_sent": 10, "drafted": 28, "escalated": 2,
        "drafts_sent_unchanged": 24, "drafts_edited": 1, "rescues": 0,
        "auto_share": 0.25, "ready_to_promote": True, "demoted": None,
    }])
    [row] = app.fetch_wa_agent_autonomy()
    assert (row["auto_pct"], row["draft_pct"], row["escalate_pct"]) == (25.0, 70.0, 5.0)
    assert row["unchanged_pct"] == 96.0
    assert row["ready_to_promote"] is True and row["demoted"] is False
    assert f"LIMIT {app.WA_AUTONOMY_MAX_ROWS}" in seen[0]


def test_autonomy_without_sent_drafts_has_no_unchanged_share(monkeypatch):
    monkeypatch.setattr(app, "_query", lambda _sql: [{
        "intent": "hours", "proposals": 3, "auto_sent": 3, "drafted": 0, "escalated": 0,
        "drafts_sent_unchanged": 0, "drafts_edited": 0, "rescues": 0,
        "auto_share": 1.0, "ready_to_promote": False, "demoted": False,
    }])
    assert app.fetch_wa_agent_autonomy()[0]["unchanged_pct"] is None


# --- payload wiring ----------------------------------------------------------

def _stub_other_fetches(monkeypatch):
    """Every non-agent fetch_* returns an empty dict, so build_payload runs
    without BigQuery and only the agent readers touch _query."""
    for name in dir(app):
        if name.startswith("fetch_") and name not in WA_FETCHES:
            monkeypatch.setattr(app, name, lambda *a, **k: {})


def test_build_payload_degrades_agent_data_when_views_are_missing(monkeypatch):
    _stub_other_fetches(monkeypatch)
    monkeypatch.setattr(app, "_query", _missing_view)
    payload = app.build_payload()
    assert payload["wa_agent_weekly"] == []
    assert payload["wa_agent_autonomy"] == []
    for key, r in payload["ranges"].items():
        assert r["wa_agent"] == app._wa_agent_empty()
        assert r["wa_agent_outcomes"] == []
        if key == "all":
            assert r["wa_agent_prev"] is None
        else:
            assert r["wa_agent_prev"] == app._wa_agent_empty()


def test_build_payload_carries_agent_data_per_range(monkeypatch):
    _stub_other_fetches(monkeypatch)

    def fake(sql):
        if "wa_agent_intent_autonomy" in sql:
            return []
        if "GROUP BY outcome" in sql:
            return [{"outcome": "booked", "score": "success", "conversations": 3}]
        if "GROUP BY week" in sql:
            return []
        return [dict(SUMMARY_ROW)]

    monkeypatch.setattr(app, "_query", fake)
    payload = app.build_payload()
    r = payload["ranges"]["30d"]
    assert r["wa_agent"]["conversations"] == 40
    assert r["wa_agent_prev"]["conversations"] == 40
    assert r["wa_agent_outcomes"][0]["outcome"] == "booked"


def _auth(user, pw):
    return {"Authorization": "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()}


def test_custom_range_carries_agent_data(monkeypatch):
    _stub_other_fetches(monkeypatch)
    monkeypatch.setattr(app, "_query", _missing_view)
    client = app.app.test_client()
    resp = client.get("/api/range?start=2026-11-01&end=2026-11-18",
                      headers=_auth("founder", "founder-pw"))
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["wa_agent"] == app._wa_agent_empty()
    assert body["wa_agent_prev"] == app._wa_agent_empty()
    assert body["wa_agent_outcomes"] == []


def test_agent_data_stays_founder_only(monkeypatch):
    # The Agent tab ships inside the founder payload: staff never reach it.
    client = app.app.test_client()
    assert client.get("/api/data", headers=_auth("frontdesk", "staff-pw")).status_code == 401
    assert client.get("/api/range?start=2026-11-01&end=2026-11-18",
                      headers=_auth("frontdesk", "staff-pw")).status_code == 401
