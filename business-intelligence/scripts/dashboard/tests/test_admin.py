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


# --- Front-desk worklists: clinician naming + package alerts ----------------

def test_clinician_name_maps_known_ids():
    assert app._clinician_name("PCN") == "Claire Ng"
    assert app._clinician_name("PCL") == "Cheryl Long"

def test_clinician_name_falls_back():
    # Unknown id passes through; None becomes an em-dash placeholder.
    assert app._clinician_name("PZZ") == "PZZ"
    assert app._clinician_name(None) == "—"


# Package Alerts is the one Plato-mirror-free worklist still served here; its
# route (and legacy alias) must demand auth on the frontdesk subdomain.
@pytest.mark.parametrize("path", [
    "/api/frontdesk/package_alerts", "/api/admin/package_alerts",
])
def test_package_alerts_require_auth(frontdesk_client, path):
    assert frontdesk_client.get(path).status_code == 401


# --- Leads pipeline ---------------------------------------------------------
# The Leads tab replaces the founder enquiry log and the removed Today/Call-list
# tabs. Routes are frontdesk-only (404 on dashboard) and demand staff/founder
# auth; the POST validates lead_id + stage + channel before any BigQuery work.

def test_leads_get_requires_auth(frontdesk_client):
    assert frontdesk_client.get("/api/frontdesk/leads").status_code == 401

def test_leads_404_on_dashboard_subdomain(client):
    # Pinned to the frontdesk subdomain — must not exist on dashboard.*.
    assert client.get("/api/frontdesk/leads", headers=_auth("founder", "founder-pw")).status_code == 404

def test_leads_save_requires_auth(frontdesk_client):
    assert frontdesk_client.post("/api/frontdesk/leads",
                                 json={"lead_id": "x", "stage": "inquiry"}).status_code == 401

def test_leads_save_bad_creds_blocked(frontdesk_client):
    resp = frontdesk_client.post("/api/frontdesk/leads",
                                 headers=_auth("frontdesk", "wrong"),
                                 json={"lead_id": "x", "stage": "inquiry"})
    assert resp.status_code == 401

@pytest.mark.parametrize("body", [
    {},                                       # nothing
    {"lead_id": "x"},                         # missing stage
    {"stage": "inquiry"},                     # missing lead_id
    {"lead_id": "x", "stage": "bogus"},       # not a valid stage
    {"lead_id": "x", "stage": "inquiry", "channel": "telegram"},  # unknown channel
])
def test_leads_save_validates_before_bq(frontdesk_client, body):
    # Valid staff auth, but a malformed body — the guard rejects with 400 before
    # record_lead touches BigQuery.
    resp = frontdesk_client.post("/api/frontdesk/leads",
                                 headers=_auth("frontdesk", "staff-pw"), json=body)
    assert resp.status_code == 400

def test_leads_save_accepts_optional_name(frontdesk_client, monkeypatch):
    # Name is optional: a lead saves with or without one, and the value (or None)
    # is passed through to record_lead. Patch record_lead so no BigQuery is hit.
    calls = []
    monkeypatch.setattr(app, "record_lead", lambda *a, **k: calls.append(k))
    auth = _auth("frontdesk", "staff-pw")

    r1 = frontdesk_client.post("/api/frontdesk/leads", headers=auth,
                               json={"lead_id": "1", "stage": "inquiry",
                                     "name": "Jane", "contact": "+65"})
    assert r1.status_code == 200
    assert calls[-1]["name"] == "Jane"

    r2 = frontdesk_client.post("/api/frontdesk/leads", headers=auth,
                               json={"lead_id": "2", "stage": "inquiry", "contact": "+65"})
    assert r2.status_code == 200
    assert calls[-1]["name"] is None


def test_lead_stage_and_channel_vocab():
    # The funnel vocabulary the UI and SQL agree on.
    assert app.OPEN_LEAD_STAGES <= app.VALID_LEAD_STAGES
    assert {"won", "lost"} <= app.VALID_LEAD_STAGES
    assert "whatsapp" in app.VALID_LEAD_CHANNELS
    assert "instagram" in app.VALID_LEAD_CHANNELS


# --- Marketing funnel assembler (_build_funnel, pure) -----------------------
# The lead aggregation lives in SQL (exercised end-to-end per DEPLOY.md). The
# pure assembler that shapes stages + conversion rates is unit-tested here.

def test_build_funnel_shape_and_conversions():
    raw = {"enquired": 100, "booked": 40, "won": 30, "retain": 60}
    f = app._build_funnel(
        raw,
        link_clicks={"total": 250},
        kpis={"new_patients": 45, "active_patients": 120},
        google_ads={"impressions": 9000},
    )
    # Charted stages = the grain-consistent lead pipeline only.
    keys = [s["key"] for s in f["stages"]]
    assert keys == ["enquire", "book", "active"]

    stage = {s["key"]: s for s in f["stages"]}
    assert stage["enquire"]["value"] == 100
    assert stage["enquire"]["context"] == 250        # tracked link taps
    assert stage["active"]["value"] == 30            # lead-attributed first visits
    assert stage["active"]["context"] == 45          # all-source first visits

    # Charted conversions are stage[i+1]/stage[i] and always <=100% (won<=booked<=enquired).
    assert f["conv"]["enquire_book"] == 0.4
    assert f["conv"]["book_active"] == 0.75

    # Reach/Engage/Retention are context, not charted stages.
    assert f["context"]["reach"] == 9000             # ad impressions
    assert f["context"]["engage"] is None            # pending integration
    # Retention is repeat/active (both all-source); repeat <= active so <=100%.
    assert f["context"]["repeat_rate"] == 0.5        # 60 / 120


def test_build_funnel_degrades_without_sources():
    # No clicks/ads/kpis and zero leads → no division by zero, nulls not crashes.
    f = app._build_funnel({"enquired": 0, "booked": 0, "won": 0, "retain": 0},
                          link_clicks={}, kpis={}, google_ads={})
    stage = {s["key"]: s for s in f["stages"]}
    assert stage["enquire"]["context"] is None       # no click total
    assert f["conv"]["enquire_book"] is None          # 0 denominator → None, not error
    assert f["context"]["reach"] is None             # no impressions → pending
    assert f["context"]["repeat_rate"] is None       # 0 active patients → None, not error


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
    # A configured number + known WhatsApp slug 302s to a wa.me deep link with
    # the channel's prefilled message. No auth required — it's a public route.
    monkeypatch.setattr(app, "WHATSAPP_NUMBER", "6580000000")
    resp = client.get("/r/ig-wa")
    assert resp.status_code == 302
    loc = resp.headers["Location"]
    assert loc.startswith("https://wa.me/6580000000?text=")
    assert "Instagram" in loc  # the prefilled message is URL-encoded but readable


def test_booking_redirect_known_slug(client, monkeypatch, _no_click_logging):
    # A booking slug 302s to the Plato booking URL when configured.
    monkeypatch.setattr(app, "PLATO_BOOKING_URL", "https://book.plato.test/goji")
    resp = client.get("/r/web-plato")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "https://book.plato.test/goji"


def test_per_channel_slugs_resolve_by_kind(client, monkeypatch, _no_click_logging):
    # Slugs are "<channel>-<destination>": the -wa slug -> wa.me, the matching
    # -plato slug -> Plato.
    monkeypatch.setattr(app, "WHATSAPP_NUMBER", "6580000000")
    monkeypatch.setattr(app, "PLATO_BOOKING_URL", "https://book.plato.test/goji")
    assert client.get("/r/bio-wa").headers["Location"].startswith("https://wa.me/6580000000?text=")
    assert client.get("/r/web-plato").headers["Location"] == "https://book.plato.test/goji"
    assert client.get("/r/bio-plato").headers["Location"] == "https://book.plato.test/goji"
    # Sanity: kind buckets are consistent with the slug naming.
    assert app.LINK_SLUG_KIND["bio-wa"] == "whatsapp"
    assert app.LINK_SLUG_KIND["bio-plato"] == "booking"


def test_booking_falls_back_when_unset(client, monkeypatch, _no_click_logging):
    # Until PLATO_BOOKING_URL is set, the booking slug falls back to the site.
    monkeypatch.setattr(app, "PLATO_BOOKING_URL", "")
    monkeypatch.setattr(app, "WHATSAPP_FALLBACK_URL", "https://example.test/site")
    resp = client.get("/r/web-plato")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "https://example.test/site"


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
    assert client.get("/r/web-wa").status_code == 302


def test_root_slug_not_exposed_in_dashboard_mode(client):
    # The bare /<slug> redirect (go.gojiphysio.com/ig) is registered ONLY in
    # links mode. On the dashboard surface it must not exist, so the internal
    # tool never serves public-style short links. /r/<slug> stays available.
    assert client.get("/ig").status_code == 404
