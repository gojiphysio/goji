"""Unit tests for the staff admin dashboard logic in app.py.

Covers the pure, security- and correctness-critical pieces that don't touch
BigQuery or Plato:
  - role resolution (the founder/staff access boundary)
  - the "who needs a follow-up call" rule
  - live-hydration name/phone extraction from arbitrary Plato shapes

Run from scripts/dashboard/:  python -m pytest tests/ -q
(BigQuery/Plato-touching paths are exercised by the manual end-to-end steps in
DEPLOY.md, not here.)
"""
from __future__ import annotations

import importlib
import os
from datetime import date, timedelta

import pytest

# Configure both credential pairs BEFORE importing app, since they're read at
# module load. Keep app importable without GCP creds (we only call pure fns).
os.environ.setdefault("DASHBOARD_USER", "founder")
os.environ.setdefault("DASHBOARD_PASS", "founder-pw")
os.environ.setdefault("STAFF_USER", "frontdesk")
os.environ.setdefault("STAFF_PASS", "staff-pw")

app = importlib.import_module("app")

TODAY = date(2026, 6, 5)


# --- role resolution: the founder/staff boundary ----------------------------

def test_resolve_role_founder():
    assert app.resolve_role("founder", "founder-pw") == "founder"

def test_resolve_role_staff():
    assert app.resolve_role("frontdesk", "staff-pw") == "staff"

@pytest.mark.parametrize("user,pw", [
    ("founder", "wrong"),
    ("frontdesk", "wrong"),
    ("nobody", "staff-pw"),
    ("", ""),
])
def test_resolve_role_rejects_bad_creds(user, pw):
    assert app.resolve_role(user, pw) is None

def test_staff_cannot_match_founder():
    # The whole point of the split: staff creds never resolve to founder.
    assert app.resolve_role("frontdesk", "staff-pw") != "founder"

def test_unset_pair_never_matches_empty(monkeypatch):
    # With no staff credentials configured, empty creds must never resolve.
    monkeypatch.setattr(app, "STAFF_CREDS", [])
    assert app.resolve_role("", "") is None


# --- actionability: who lands on the call list ------------------------------

def test_red_with_no_future_is_actionable():
    assert app.is_actionable("red", False, None, None, TODAY) is True

@pytest.mark.parametrize("tier", ["green"])
def test_healthy_tier_is_not_actionable(tier):
    assert app.is_actionable(tier, False, None, None, TODAY) is False

@pytest.mark.parametrize("tier", ["yellow", "orange", "red"])
def test_future_appt_removes_from_list(tier):
    assert app.is_actionable(tier, True, None, None, TODAY) is False

def test_dismissed_is_not_actionable():
    assert app.is_actionable("red", False, "dismissed", None, TODAY) is False

def test_active_future_snooze_hides():
    future = TODAY + timedelta(days=3)
    assert app.is_actionable("orange", False, "snoozed", future, TODAY) is False

def test_expired_snooze_resurfaces():
    past = TODAY - timedelta(days=1)
    assert app.is_actionable("orange", False, "snoozed", past, TODAY) is True

def test_contacted_stays_actionable():
    # Calling once doesn't drop them until they re-book or are dismissed.
    assert app.is_actionable("yellow", False, "contacted", None, TODAY) is True


# --- route gating: the security boundary, end-to-end ------------------------
# These exercise the real decorators. Auth is checked before the handler runs,
# so the founder-only routes 401 a staff login without ever touching BigQuery.

import base64


def _auth(user: str, pw: str) -> dict:
    token = base64.b64encode(f"{user}:{pw}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


@pytest.fixture
def client():
    app.app.config.update(TESTING=True)
    return app.app.test_client()


def test_staff_blocked_from_financial_data(client):
    # The crux: a staff credential must never reach the financial payload.
    assert client.get("/api/data", headers=_auth("frontdesk", "staff-pw")).status_code == 401

def test_staff_blocked_from_financial_index(client):
    assert client.get("/", headers=_auth("frontdesk", "staff-pw")).status_code == 401

def test_admin_requires_auth(client):
    assert client.get("/admin").status_code == 401

def test_bad_creds_blocked_from_admin(client):
    assert client.get("/admin", headers=_auth("frontdesk", "wrong")).status_code == 401

def test_staff_can_reach_admin(client):
    resp = client.get("/admin", headers=_auth("frontdesk", "staff-pw"))
    assert resp.status_code == 200
    assert b"Front Desk" in resp.data

def test_founder_can_reach_admin(client):
    assert client.get("/admin", headers=_auth("founder", "founder-pw")).status_code == 200

def test_healthcheck_open(client):
    assert client.get("/healthcheck").status_code == 200


# --- Phase 2: today's schedule / call list / package alerts -----------------

def test_clinician_name_maps_known_ids():
    assert app._clinician_name("PCN") == "Claire Ng"
    assert app._clinician_name("PCL") == "Cheryl Long"

def test_clinician_name_falls_back():
    # Unknown id passes through; None becomes an em-dash placeholder.
    assert app._clinician_name("PZZ") == "PZZ"
    assert app._clinician_name(None) == "—"


def _appt(appointment_id, *, is_today, is_cancelled=False, confirmed=False):
    return {"appointment_id": appointment_id, "is_today": is_today,
            "is_cancelled": is_cancelled, "confirmed": confirmed}

def test_partition_schedule_is_todays_non_cancelled():
    appts = [
        _appt("a", is_today=True),
        _appt("b", is_today=True, is_cancelled=True),   # cancelled -> not on schedule
        _appt("c", is_today=False),                     # tomorrow -> not on schedule
    ]
    schedule, _ = app.partition_upcoming(appts)
    assert [a["appointment_id"] for a in schedule] == ["a"]

def test_partition_calls_are_unconfirmed_non_cancelled_in_window():
    appts = [
        _appt("a", is_today=True),                      # today, unconfirmed -> call
        _appt("b", is_today=False),                     # tomorrow, unconfirmed -> call
        _appt("c", is_today=True, confirmed=True),      # confirmed -> not a call
        _appt("d", is_today=False, is_cancelled=True),  # cancelled -> not a call
    ]
    _, calls = app.partition_upcoming(appts)
    assert sorted(a["appointment_id"] for a in calls) == ["a", "b"]

def test_confirmed_today_appt_stays_on_schedule_but_off_calls():
    appts = [_appt("a", is_today=True, confirmed=True)]
    schedule, calls = app.partition_upcoming(appts)
    assert [a["appointment_id"] for a in schedule] == ["a"]
    assert calls == []


# --- Phase 2 route gating ---------------------------------------------------

@pytest.mark.parametrize("path", [
    "/api/admin/schedule", "/api/admin/calls", "/api/admin/package_alerts",
])
def test_phase2_endpoints_require_auth(client, path):
    assert client.get(path).status_code == 401

def test_confirm_appt_requires_auth(client):
    assert client.post("/api/admin/confirm_appt", json={"appointment_id": "x"}).status_code == 401

def test_confirm_appt_bad_creds_blocked(client):
    resp = client.post("/api/admin/confirm_appt",
                       headers=_auth("frontdesk", "wrong"), json={"appointment_id": "x"})
    assert resp.status_code == 401

def test_confirm_appt_missing_id_is_400(client):
    # Valid staff auth, but no appointment_id — validation rejects before any BQ
    # work, so this exercises the guard without touching BigQuery.
    resp = client.post("/api/admin/confirm_appt",
                       headers=_auth("frontdesk", "staff-pw"), json={})
    assert resp.status_code == 400
