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
    monkeypatch.setattr(app, "STAFF_USER", "")
    monkeypatch.setattr(app, "STAFF_PASS", "")
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


# --- PII extraction from Plato patient records ------------------------------

def test_extract_name_from_dict():
    assert app._extract_full_name({"name": {"first": "Charles", "last": "Wong"}}) == "Charles Wong"

def test_extract_name_from_string():
    assert app._extract_full_name({"name": "Madonna"}) == "Madonna"

def test_extract_name_missing():
    assert app._extract_full_name({}) is None

@pytest.mark.parametrize("record,expected", [
    ({"mobile": "+6591234567"}, "+6591234567"),
    ({"phone": "98765432"}, "98765432"),
    ({"handphone": " 8123 4567 "}, "8123 4567"),
    ({"contact": {"number": "+6590001111"}}, "+6590001111"),
    ({"name": "no phone here"}, None),
])
def test_extract_phone_variants(record, expected):
    assert app._extract_phone(record) == expected


# --- live hydration: retry on throttle, never cache a failure -----------------
# Why this matters: a Plato 429 used to fall back to initials AND get cached for
# 15 min, so a throttled patient stayed on initials. These lock in the fix.

class _FakeResp:
    def __init__(self, code, payload=None):
        self.status_code = code
        self._payload = payload or {}
    def json(self):
        return self._payload


def test_contact_retries_after_429_then_succeeds(monkeypatch):
    app._contact_cache.clear()
    monkeypatch.setattr(app.time, "sleep", lambda *a, **k: None)  # no real backoff in tests
    calls = {"n": 0}

    class FakeSession:
        def get(self, url, timeout=None):
            calls["n"] += 1
            if calls["n"] == 1:
                return _FakeResp(429)
            return _FakeResp(200, {"name": {"first": "Charles", "last": "Wong"},
                                   "mobile": "9123 4567"})

    monkeypatch.setattr(app, "_plato", lambda: FakeSession())
    pid, info = app._fetch_one_contact("p1")
    assert info["full_name"] == "Charles Wong"
    assert info["phone"] == "9123 4567"
    assert calls["n"] == 2                 # retried once after the 429
    assert "p1" in app._contact_cache      # a real 200 IS cached


def test_contact_failure_is_not_cached(monkeypatch):
    app._contact_cache.clear()
    monkeypatch.setattr(app.time, "sleep", lambda *a, **k: None)

    class AlwaysThrottled:
        def get(self, url, timeout=None):
            return _FakeResp(429)

    monkeypatch.setattr(app, "_plato", lambda: AlwaysThrottled())
    pid, info = app._fetch_one_contact("p2")
    assert info == {}                      # degrades to initials this load
    assert "p2" not in app._contact_cache  # but NOT cached -> next load retries


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
