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
    """A test client on the founder dashboard subdomain (APP_MODE=dashboard)."""
    app.app.config.update(TESTING=True)
    return app.app.test_client()


@pytest.fixture
def frontdesk_client(monkeypatch):
    """A test client on the front-desk subdomain (APP_MODE=frontdesk)."""
    monkeypatch.setattr(app, "APP_MODE", "frontdesk")
    app.app.config.update(TESTING=True)
    return app.app.test_client()


def test_staff_blocked_from_financial_data(client):
    # The crux: a staff credential must never reach the financial payload.
    assert client.get("/api/data", headers=_auth("frontdesk", "staff-pw")).status_code == 401

def test_staff_blocked_from_financial_index(client):
    assert client.get("/", headers=_auth("frontdesk", "staff-pw")).status_code == 401

def test_healthcheck_open(client):
    assert client.get("/healthcheck").status_code == 200


# --- subdomain split: exactly two surfaces ----------------------------------
# Founders use dashboard.* (APP_MODE=dashboard); the front desk uses frontdesk.*
# (APP_MODE=frontdesk). Each subdomain 404s the other's routes — the route does
# not exist there at all, regardless of credentials.

def test_ops_routes_404_on_dashboard_subdomain(client):
    # The ops portal must NOT be reachable on the founder dashboard subdomain.
    assert client.get("/api/frontdesk/schedule", headers=_auth("founder", "founder-pw")).status_code == 404

def test_legacy_admin_404s_on_dashboard_subdomain(client):
    # The legacy /admin path is frontdesk-only; 404 on the dashboard subdomain.
    assert client.get("/admin", headers=_auth("founder", "founder-pw")).status_code == 404

def test_financial_routes_404_on_frontdesk_subdomain(frontdesk_client):
    # Financial data must never be reachable on the front-desk subdomain.
    assert frontdesk_client.get("/api/data", headers=_auth("founder", "founder-pw")).status_code == 404

def test_no_redundant_frontdesk_path(frontdesk_client):
    # The portal is at / on frontdesk.*; there is no /frontdesk page route.
    assert frontdesk_client.get("/frontdesk", headers=_auth("frontdesk", "staff-pw")).status_code == 404


# --- front-desk portal access: served at / on the frontdesk subdomain -------

def test_frontdesk_root_requires_auth(frontdesk_client):
    assert frontdesk_client.get("/").status_code == 401

def test_bad_creds_blocked_from_frontdesk_root(frontdesk_client):
    assert frontdesk_client.get("/", headers=_auth("frontdesk", "wrong")).status_code == 401

def test_staff_can_reach_frontdesk_root(frontdesk_client):
    resp = frontdesk_client.get("/", headers=_auth("frontdesk", "staff-pw"))
    assert resp.status_code == 200
    assert b"Front Desk" in resp.data

def test_founder_can_reach_frontdesk_root(frontdesk_client):
    assert frontdesk_client.get("/", headers=_auth("founder", "founder-pw")).status_code == 200

def test_legacy_admin_redirects_to_root_on_frontdesk(frontdesk_client):
    # /admin is deprecated: it 301-redirects to / so old bookmarks don't break.
    resp = frontdesk_client.get("/admin")
    assert resp.status_code == 301
    assert resp.headers["Location"].endswith("/")


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


# --- Phase 2 route gating (on the frontdesk subdomain) ----------------------

@pytest.mark.parametrize("path", [
    "/api/frontdesk/schedule", "/api/frontdesk/calls", "/api/frontdesk/package_alerts",
])
def test_phase2_endpoints_require_auth(frontdesk_client, path):
    assert frontdesk_client.get(path).status_code == 401

@pytest.mark.parametrize("path", [
    "/api/admin/schedule", "/api/admin/calls", "/api/admin/package_alerts",
])
def test_phase2_legacy_aliases_require_auth(frontdesk_client, path):
    # Legacy /api/admin/* aliases still resolve (and still demand auth).
    assert frontdesk_client.get(path).status_code == 401

def test_confirm_appt_requires_auth(frontdesk_client):
    assert frontdesk_client.post("/api/frontdesk/confirm_appt", json={"appointment_id": "x"}).status_code == 401

def test_confirm_appt_bad_creds_blocked(frontdesk_client):
    resp = frontdesk_client.post("/api/frontdesk/confirm_appt",
                       headers=_auth("frontdesk", "wrong"), json={"appointment_id": "x"})
    assert resp.status_code == 401

def test_confirm_appt_missing_id_is_400(frontdesk_client):
    # Valid staff auth, but no appointment_id — validation rejects before any BQ
    # work, so this exercises the guard without touching BigQuery.
    resp = frontdesk_client.post("/api/frontdesk/confirm_appt",
                       headers=_auth("frontdesk", "staff-pw"), json={})
    assert resp.status_code == 400


# --- Marketing tab: founder-only operating-tool routes ----------------------
# The Marketing tab lives on the founder dashboard subdomain. Its /api/marketing
# routes follow the same boundary as /api/data: founder-only, and 404 (not even
# reachable) on the frontdesk subdomain.

def test_marketing_ops_requires_auth(client):
    assert client.get("/api/marketing/ops").status_code == 401

def test_marketing_ops_blocks_staff(client):
    # A staff credential must never reach the founder Marketing data.
    assert client.get("/api/marketing/ops", headers=_auth("frontdesk", "staff-pw")).status_code == 401

def test_marketing_ops_404_on_frontdesk_subdomain(frontdesk_client):
    # Founder-only route: doesn't exist on the front-desk subdomain.
    assert frontdesk_client.get("/api/marketing/ops",
                                headers=_auth("founder", "founder-pw")).status_code == 404
    assert frontdesk_client.post("/api/marketing/ops", headers=_auth("founder", "founder-pw"),
                                 json={"item_type": "checklist", "item_key": "x"}).status_code == 404

def test_marketing_ops_save_requires_auth(client):
    assert client.post("/api/marketing/ops",
                       json={"item_type": "checklist", "item_key": "x"}).status_code == 401

@pytest.mark.parametrize("body", [
    {},                                     # nothing
    {"item_type": "bogus", "item_key": "x"},  # not a known item_type
    {"item_type": "checklist"},             # missing item_key
    {"item_key": "x"},                      # missing item_type
])
def test_marketing_ops_save_validates_before_bq(client, body):
    # Valid founder auth, but a malformed body — the guard rejects with 400
    # before record_marketing_ops touches BigQuery.
    resp = client.post("/api/marketing/ops", headers=_auth("founder", "founder-pw"), json=body)
    assert resp.status_code == 400


# --- click-to-WhatsApp redirect (public) ------------------------------------

@pytest.fixture
def _no_click_logging(monkeypatch):
    # Keep the redirect tests hermetic: don't spawn the BQ-writing thread.
    monkeypatch.setattr(app, "_record_link_click_async", lambda *a, **k: None)


def test_whatsapp_redirect_known_slug(client, monkeypatch, _no_click_logging):
    # A configured number + known slug 302s to a wa.me deep link with the
    # channel's prefilled message. No auth required — it's a public route.
    monkeypatch.setattr(app, "WHATSAPP_NUMBER", "6580000000")
    resp = client.get("/r/ig")
    assert resp.status_code == 302
    loc = resp.headers["Location"]
    assert loc.startswith("https://wa.me/6580000000?text=")
    assert "Instagram" in loc  # the prefilled message is URL-encoded but readable


def test_whatsapp_redirect_unknown_slug_falls_back(client, monkeypatch, _no_click_logging):
    # Unknown slug (or unconfigured number) must never dead-end — it falls back
    # to the site URL rather than erroring.
    monkeypatch.setattr(app, "WHATSAPP_NUMBER", "6580000000")
    monkeypatch.setattr(app, "WHATSAPP_FALLBACK_URL", "https://example.test/site")
    resp = client.get("/r/bogus")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "https://example.test/site"


def test_whatsapp_redirect_is_public(client, _no_click_logging):
    # The redirect must work with no credentials at all (it's the link people
    # click from Instagram/Google/etc.).
    assert client.get("/r/web").status_code == 302
