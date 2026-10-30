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


# --- acquisition funnel: the "Other" fold keeps the Sankey readable ---------
# _build_funnel_paths is pure given its stream inputs, so we can assert the
# discovery-layer folding without touching BigQuery.

def _flows(result):
    """{(from, to): flow} for easy assertions."""
    return {(e["from"], e["to"]): e["flow"] for e in result["flows"]}


def test_funnel_folds_tiny_discovery_into_other():
    # Weirdo (1 session) is below FUNNEL_DISCOVERY_MIN (2) -> folds into Other.
    # Instagram/Google are above it; Direct is exempt even at 1 session.
    web_channels = {"Instagram": 10, "Google": 5, "Weirdo": 1, "Direct": 1}
    res = app._build_funnel_paths({}, {}, {}, web_channels, {}, {})
    f = _flows(res)
    assert f[("Instagram", "Website")] == 10
    assert f[("Google", "Website")] == 5
    assert f[("Other", "Website")] == 1        # Weirdo folded in
    assert f[("Direct", "Website")] == 1       # Direct never folds
    assert ("Weirdo", "Website") not in f


def test_funnel_folds_multiple_tiny_channels_together():
    web_channels = {"A": 1, "B": 1, "Instagram": 3}
    res = app._build_funnel_paths({}, {}, {}, web_channels, {}, {})
    f = _flows(res)
    assert f[("Other", "Website")] == 2        # A + B combined
    assert f[("Instagram", "Website")] == 3


def test_funnel_empty_streams_degrade_to_no_flows():
    res = app._build_funnel_paths({}, {}, {}, {}, {}, {})
    assert res["flows"] == []


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
# The Leads tab is the source of truth for inbound inquiries (superseding the
# old founder enquiry log and the removed Today/Call-list tabs). Routes are
# frontdesk-only (404 on dashboard) and demand staff/founder
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


# --- Acquisition-funnel Sankey paths (_build_funnel_paths, pure) -------------
# The per-slug click counts come from marts.link_click_events (exercised
# end-to-end per DEPLOY.md). The pure builder that turns those slug counts into
# Source -> Link in bio -> CTA flows is unit-tested here.

def test_build_funnel_paths_links_landings_route_to_link_in_bio():
    # /links landings (split out by fetch_web_channels) arrive on the Link in bio
    # surface, not Website, and replace the tap-inferred Instagram edge, so an
    # Instagram visitor to /links isn't counted on two edges.
    link_clicks = {"wa_by_slug": {"bio-wa": 9, "web-wa": 4}, "book_by_slug": {"bio-book": 3}}
    web_channels = {"website": {"Instagram": 20, "Direct": 10},
                    "links":   {"Instagram": 40, "Direct": 1}}
    f = app._build_funnel_paths(link_clicks, {}, {}, web_channels, {})
    flows = {(d["from"], d["to"]): d["flow"] for d in f["flows"]}
    assert flows[("Instagram", "Website")] == 20
    assert flows[("Instagram", "Link in bio")] == 40      # landings, not 12 taps
    assert flows[("Direct", "Link in bio")] == 1          # Direct is never folded
    assert flows[("Link in bio", "WhatsApp")] == 9
    assert flows[("Link in bio", "Native booking")] == 3
    assert f["sessions"] == 71

    # No /links landings in range (bio.site era): fall back to the tap-inferred edge.
    old = app._build_funnel_paths(link_clicks, {}, {}, {"website": {"Direct": 5}, "links": {}}, {})
    old_flows = {(d["from"], d["to"]): d["flow"] for d in old["flows"]}
    assert old_flows[("Instagram", "Link in bio")] == 12


def test_build_funnel_paths_discovery_surface_cta_booked():
    link_clicks = {
        "wa_by_slug":   {"ig-wa": 50, "bio-wa": 60, "web-wa": 40, "gbp-wa": 30, "wa": 5},
        # book_by_slug carries both the website /book slugs (*-book) and retired
        # Plato slugs (*-plato) — both now merge into the single "Native booking"
        # CTA, since a *-plato click also lands on the /book form.
        "book_by_slug": {"bio-book": 20, "web-book": 24, "ads-book": 28, "web-plato": 9, "book": 3},
    }
    web_channels = {"Google Ads": 100, "Instagram": 70, "Direct": 55}
    booking_funnel = {"booked": 7}
    f = app._build_funnel_paths(link_clicks, {"new_patients": 47},
                                {"whatsapp": 12, "instagram": 3},
                                web_channels, booking_funnel)
    flows = {(d["from"], d["to"]): d["flow"] for d in f["flows"]}

    # Discovery -> Website (arrival), from the landing beacon (sessions).
    assert flows[("Google Ads", "Website")] == 100
    assert flows[("Direct", "Website")] == 55
    # web-* taps sit under the Website surface; bio-* under Link in bio + IG hop.
    # web-plato (9) merges into the same "Native booking" CTA as web-book (24).
    assert flows[("Website", "WhatsApp")] == 40
    assert flows[("Website", "Native booking")] == 33
    assert ("Website", "Plato booking") not in flows
    assert flows[("Instagram", "Link in bio")] == 80        # bio-wa 60 + bio-book 20
    assert flows[("Link in bio", "WhatsApp")] == 60
    assert flows[("Link in bio", "Native booking")] == 20
    # ig-* is a direct Instagram tap; gbp/ads bypass the site straight to a CTA.
    assert flows[("Instagram", "WhatsApp")] == 50
    assert flows[("Google", "WhatsApp")] == 30           # gbp -> Google
    assert flows[("Ads", "Native booking")] == 28
    # Generic fallback slugs ('wa' / 'book') have no source prefix -> "Other".
    assert flows[("Other", "WhatsApp")] == 5
    assert flows[("Other", "Native booking")] == 3

    # Outcome: Native booking -> Booked = confirmed bookings; WhatsApp -> Booked =
    # won whatsapp leads (non-whatsapp wins are NOT pulled in).
    assert flows[("Native booking", "Booked")] == 7
    assert flows[("WhatsApp", "Booked")] == 12
    assert f["booked_native"] == 7 and f["booked_wa"] == 12

    assert f["wa_taps"] == 185 and f["book_taps"] == 84
    assert f["total_taps"] == 269
    assert f["sessions"] == 225
    assert f["first_visits"] == 47
    assert f["referral_domains"] == {}  # not passed -> defaults empty


def test_build_funnel_paths_referral_domains_passthrough():
    # referral_domains (from fetch_referral_domains) rides through untouched so
    # the frontend can render it as a hover tooltip on the "Referral" swatch.
    domains = {"clinicfinder.sg": 12, "sgparenting.com": 8, "other": 5}
    f = app._build_funnel_paths({}, {}, {}, {}, {}, domains)
    assert f["referral_domains"] == domains


def test_build_funnel_paths_booked_nodes_absent_without_data():
    # No confirmed bookings and no logged wins → no "Booked" edges (the outcome
    # node simply doesn't draw), and the WhatsApp clamp can't go negative.
    f = app._build_funnel_paths(
        {"wa_by_slug": {"ig-wa": 10}, "book_by_slug": {}}, {"new_patients": 4},
        {}, {}, {})
    flows = {(d["from"], d["to"]): d["flow"] for d in f["flows"]}
    assert ("Native booking", "Booked") not in flows
    assert ("WhatsApp", "Booked") not in flows
    assert flows[("Instagram", "WhatsApp")] == 10
    assert f["booked_native"] == 0 and f["booked_wa"] == 0


def test_build_funnel_paths_degrades_without_data():
    # No clicks / kpis / wins / channels / bookings → empty flows and safe nulls.
    f = app._build_funnel_paths({}, {}, {}, {}, {})
    assert f["flows"] == []
    assert f["total_taps"] == 0
    assert f["sessions"] == 0
    assert f["booked_native"] == 0
    assert f["first_visits"] is None


def test_fetch_web_sessions_noop_until_ga4_linked():
    # GA4_DATASET is unset in the test env, so the fetch must short-circuit to
    # zeros WITHOUT touching BigQuery (the Website card stays empty, never errors).
    assert app.GA4_DATASET == ""
    assert app.fetch_web_sessions(TODAY - timedelta(days=30), TODAY) == {"sessions": 0, "pageviews": 0}


def test_fetch_instagram_reach_degrades_without_table(monkeypatch):
    # Marketing card must stay empty (never error) until marketing_ingest has run
    # and marts.fct_instagram_reach exists.
    def _boom(*a, **k):
        raise RuntimeError("Not found: Table goji-bi:marts.fct_instagram_reach")
    monkeypatch.setattr(app, "_query", _boom)
    assert app.fetch_instagram_reach(TODAY - timedelta(days=30), TODAY) == {"reach": 0}


def test_fetch_instagram_reach_returns_latest_snapshot(monkeypatch):
    # Reach is de-duplicated: the fetch returns the latest reading (a snapshot),
    # not a range sum. The query already ORDER BY metric_date DESC LIMIT 1, so the
    # first row is authoritative.
    monkeypatch.setattr(app, "_query", lambda *a, **k: [{"reach": 4200}])
    assert app.fetch_instagram_reach(TODAY - timedelta(days=30), TODAY) == {"reach": 4200}


# --- provider-attribution alert dismissals (persistent, server-side) --------

def test_mismatch_dismiss_requires_auth(client):
    assert client.post("/api/mismatch/dismiss",
                       json={"action": "dismiss", "items": [{"invoice_id": "x"}]}).status_code == 401


def test_mismatch_dismiss_404_on_frontdesk_subdomain(frontdesk_client):
    # Founder alert surface — gated routes 404 on the public/front-desk surfaces.
    assert frontdesk_client.post("/api/mismatch/dismiss",
                                 headers=_auth("founder", "founder-pw"),
                                 json={"action": "dismiss", "items": [{"invoice_id": "x"}]}).status_code == 404


@pytest.mark.parametrize("body", [
    {},                                              # nothing
    {"action": "dismiss"},                           # no items
    {"action": "dismiss", "items": []},              # empty items
    {"action": "dismiss", "items": [{"reason": "no id"}]},  # item without invoice_id
    {"action": "bogus", "items": [{"invoice_id": "x"}]},    # unknown action
])
def test_mismatch_dismiss_validates_before_bq(client, body):
    # Valid founder auth, malformed body — rejected 400 before record touches BQ.
    resp = client.post("/api/mismatch/dismiss", headers=_auth("founder", "founder-pw"), json=body)
    assert resp.status_code == 400


def test_mismatch_dismiss_records_each_item(client, monkeypatch):
    # A valid dismiss-all writes one event per item, carrying the snapshot and
    # the mapped action. Patch record_mismatch_dismissal so no BigQuery is hit.
    calls = []
    monkeypatch.setattr(app, "record_mismatch_dismissal",
                        lambda invoice_id, action, **k: calls.append((invoice_id, action, k)))
    resp = client.post("/api/mismatch/dismiss", headers=_auth("founder", "founder-pw"),
                       json={"action": "dismiss", "items": [
                           {"invoice_id": "inv-1", "patient": "V. Maung", "total": 729.0},
                           {"invoice_id": "inv-2"}]})
    assert resp.status_code == 200
    assert [c[0] for c in calls] == ["inv-1", "inv-2"]
    assert {c[1] for c in calls} == {"dismissed"}
    # snapshot is threaded through so the history tab can render it later
    assert calls[0][2]["snapshot"]["patient"] == "V. Maung"


def test_mismatch_restore_maps_action(client, monkeypatch):
    calls = []
    monkeypatch.setattr(app, "record_mismatch_dismissal",
                        lambda invoice_id, action, **k: calls.append((invoice_id, action)))
    resp = client.post("/api/mismatch/dismiss", headers=_auth("founder", "founder-pw"),
                       json={"action": "restore", "items": [{"invoice_id": "inv-1"}]})
    assert resp.status_code == 200
    assert calls == [("inv-1", "restored")]


def test_dismissed_invoices_drop_out_of_live_alert(monkeypatch):
    # The core promise: a dismissed invoice never reappears in the live alert,
    # even while it still mismatches in the mart. Feed canned mismatch rows and
    # a dismissed-id set; only the undismissed one should survive.
    import datetime as _dt
    rows = [
        {"invoice_id": "inv-1", "invoice_label": "GLM-1", "invoice_date": _dt.date(2026, 6, 22),
         "patient_id": "p1", "initial_lastname": "V. Maung", "invoice_clinician_id": "PKN",
         "appt_clinician_ids": ["PCL"], "status": "mismatch",
         "created_by": "u", "last_edited_by": "u", "total": 729.0},
        {"invoice_id": "inv-2", "invoice_label": "GLM-2", "invoice_date": _dt.date(2026, 6, 23),
         "patient_id": "p2", "initial_lastname": "A. Tan", "invoice_clinician_id": "PKN",
         "appt_clinician_ids": ["PCL"], "status": "mismatch",
         "created_by": "u", "last_edited_by": "u", "total": 100.0},
    ]
    monkeypatch.setattr(app, "_query", lambda *a, **k: rows)
    monkeypatch.setattr(app, "fetch_dismissed_mismatch_ids", lambda: {"inv-1"})
    out = app.fetch_invoice_doctor_mismatches()
    ids = [m["invoice_id"] for m in out["mismatches"]]
    assert ids == ["inv-2"]


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
    # Retired *-plato slugs now alias to the native /book form — we no longer
    # support a separate Plato-booking flow, so old published links redirect to
    # the one booking flow we actually track.
    monkeypatch.setattr(app, "SITE_BOOKING_URL", "https://www.gojiphysio.com/book")
    resp = client.get("/r/web-plato")
    assert resp.status_code == 302
    assert resp.headers["Location"].startswith("https://www.gojiphysio.com/book?")


def test_per_channel_slugs_resolve_by_kind(client, monkeypatch, _no_click_logging):
    # Slugs are "<channel>-<destination>": the -wa slug -> wa.me, the matching
    # -plato slug now resolves the same as -book (the native booking form).
    monkeypatch.setattr(app, "WHATSAPP_NUMBER", "6580000000")
    monkeypatch.setattr(app, "SITE_BOOKING_URL", "https://www.gojiphysio.com/book")
    assert client.get("/r/bio-wa").headers["Location"].startswith("https://wa.me/6580000000?text=")
    assert client.get("/r/web-plato").headers["Location"].startswith("https://www.gojiphysio.com/book?")
    assert client.get("/r/bio-plato").headers["Location"].startswith("https://www.gojiphysio.com/book?")
    # Sanity: kind buckets are consistent with the slug naming.
    assert app.LINK_SLUG_KIND["bio-wa"] == "whatsapp"
    assert app.LINK_SLUG_KIND["bio-plato"] == "book"


def test_booking_falls_back_when_unset(client, monkeypatch, _no_click_logging):
    # Until SITE_BOOKING_URL is set, a booking slug (incl. retired -plato) falls
    # back to the site so a published link never dead-ends (cid/src still append
    # — harmless query params on the fallback homepage).
    monkeypatch.setattr(app, "SITE_BOOKING_URL", "")
    monkeypatch.setattr(app, "WHATSAPP_FALLBACK_URL", "https://example.test/site")
    resp = client.get("/r/web-plato")
    assert resp.status_code == 302
    assert resp.headers["Location"].startswith("https://example.test/site")


def test_book_redirect_goes_to_site_booking_form(client, monkeypatch, _no_click_logging):
    # The current booking CTA: a *-book slug 302s to our own /book form, with the
    # click-id + channel passed through (?cid&src) so the landing beacon can join
    # the click to the on-site booking session (origin→booking attribution).
    monkeypatch.setattr(app, "SITE_BOOKING_URL", "https://www.gojiphysio.com/book")
    resp = client.get("/r/web-book")
    assert resp.status_code == 302
    loc = resp.headers["Location"]
    assert loc.startswith("https://www.gojiphysio.com/book?")
    from urllib.parse import urlparse, parse_qs
    q = parse_qs(urlparse(loc).query)
    assert q["src"] == ["web-book"]
    assert len(q["cid"][0]) >= 8  # a uuid passthrough
    assert app.LINK_SLUG_KIND["web-book"] == "book"


def test_whatsapp_redirect_has_no_click_id_passthrough(client, monkeypatch, _no_click_logging):
    # The cid/src passthrough only applies to on-site /book targets; a wa.me deep
    # link must stay clean (the click_id can't join anything on WhatsApp's side).
    monkeypatch.setattr(app, "WHATSAPP_NUMBER", "6580000000")
    resp = client.get("/r/web-wa")
    assert resp.status_code == 302
    assert "cid=" not in resp.headers["Location"]


def test_book_slug_counts_as_a_booking_click():
    # *-book clicks bucket into book_by_slug so they show as booking-link clicks.
    rows = {"web-book": 5, "bio-book": 3, "web-wa": 9}
    # emulate fetch_link_clicks' split without touching BigQuery
    book = {s: n for s, n in rows.items() if app.LINK_SLUG_KIND.get(s) in ("book", "booking")}
    assert book == {"web-book": 5, "bio-book": 3}


def test_pay_slug_goes_to_stripe_with_click_id(client, monkeypatch, _no_click_logging):
    # Shop slugs 302 to the item's Stripe Payment Link, carrying the click_id as
    # client_reference_id so a purchase joins back to the click.
    monkeypatch.setattr(app, "SHOP_PAY_URLS", {"cpsc-5": "https://buy.stripe.com/test_abc"})
    loc = client.get("/r/web-pay-cpsc-5").headers["Location"]
    assert loc.startswith("https://buy.stripe.com/test_abc?client_reference_id=")
    assert app.LINK_SLUG_KIND["web-pay-cpsc-5"] == "pay"


def test_pay_slug_without_link_falls_back_to_shop(client, monkeypatch, _no_click_logging):
    monkeypatch.setattr(app, "SHOP_PAY_URLS", {})
    assert client.get("/r/web-pay-gift-voucher").headers["Location"] == app.SHOP_FALLBACK_URL


def test_pay_clicks_are_not_counted_as_whatsapp(monkeypatch):
    rows = [{"slug": "web-pay-cpsc-5", "clicks": 4}, {"slug": "web-wa", "clicks": 2}]
    monkeypatch.setattr(app, "_query", lambda sql, *a, **k: rows)
    lc = app.fetch_link_clicks(TODAY, TODAY)
    assert lc["wa_by_slug"] == {"web-wa": 2}
    assert lc["whatsapp"] == 2 and lc["booking"] == 0


def test_fetch_link_clicks_counts_real_taps_only(monkeypatch):
    # Bots, tooling and stale on-site sessions must be filtered in the query,
    # not after it: raw taps were up to 8x real in Oct 2026.
    seen = {}

    def _fake(sql, *a, **k):
        seen["sql"] = sql
        return [{"slug": "web-wa", "clicks": 4}, {"slug": "gbp-book", "clicks": 2},
                {"slug": ".env", "clicks": 17}]
    monkeypatch.setattr(app, "_query", _fake)
    r = app.fetch_link_clicks(TODAY - timedelta(days=30), TODAY)
    assert r["wa_by_slug"] == {"web-wa": 4} and r["book_by_slug"] == {"gbp-book": 2}
    sql = seen["sql"]
    assert "REGEXP_CONTAINS(LOWER(c.user_agent)" in sql and "nexus 5x build/mmb29p" in sql
    assert "INTERVAL 6 HOUR" in sql and "STARTS_WITH(c.slug, 'web-')" in sql


def test_bot_ua_re_matches_tooling_not_phones():
    import re
    bot = re.compile(app.BOT_UA_RE)
    for ua in ("Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P) AppleWebKit/537.36 Chrome/153.0",
               "Mozilla/5.0 (compatible; bingbot/2.0)", "facebookexternalhit/1.1",
               "Mozilla/5.0 (compatible; GojiSiteAudit/1.0)", "python-requests/2.32"):
        assert bot.search(ua.lower()), ua
    for ua in ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1",
               "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 Chrome/141.0 Mobile Safari/537.36"):
        assert not bot.search(ua.lower()), ua


def test_booking_funnel_labels_include_details():
    # The "Entered details" stage must sit between time_selected and submitted.
    stages = [s for s, _ in app.BOOKING_FUNNEL_STAGES]
    assert stages.index("time_selected") < stages.index("details") < stages.index("submitted")
    assert dict(app.BOOKING_FUNNEL_STAGES)["details"] == "Entered details"


def test_booking_funnel_date_picked_sits_between_service_and_time():
    # "Picked date" (step-2 instrumentation, 2026-07) slots into the flow order.
    stages = [s for s, _ in app.BOOKING_FUNNEL_STAGES]
    assert stages.index("service_selected") < stages.index("date_picked") < stages.index("time_selected")
    assert dict(app.BOOKING_FUNNEL_STAGES)["date_picked"] == "Picked date"


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
