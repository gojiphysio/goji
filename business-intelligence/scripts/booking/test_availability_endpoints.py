"""Endpoint behaviour when Plato is struggling (no network — stub the derivation).

The visitor-facing rule: an older answer beats an error screen, and a month that
is merely still loading is a retryable 503, not a failure.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from booking import app as app_mod
from booking.plato import PlatoBusy, PlatoThrottled


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(app_mod, "_avail_cache", {})
    monkeypatch.setattr(app_mod, "_summary_cache", {})
    monkeypatch.setattr(app_mod, "plato", lambda: object())
    app_mod.app.config["TESTING"] = True
    with app_mod.app.test_client() as c:
        yield c


def _raising(exc):
    def fake(*_a, **_kw):
        raise exc
    return fake


DAY = "/api/availability?service=physiotherapy&date=2026-11-07"
MONTH = ("/api/availability-summary?service=physiotherapy&month="
         + datetime.now(app_mod.SGT).strftime("%Y-%m"))  # inside the bookable window


def test_day_serves_the_last_answer_when_plato_fails(client, monkeypatch):
    monkeypatch.setattr(app_mod, "derive_availability",
                        lambda *a, **k: {"claire-ng": ["10:00", "11:00"]})
    assert client.get(DAY).get_json()["times"] == ["10:00", "11:00"]

    # Expire the 45s cache, then break Plato: the old answer should still come back.
    monkeypatch.setattr(app_mod, "AVAIL_TTL_S", 0)
    monkeypatch.setattr(app_mod, "derive_availability", _raising(RuntimeError("429")))
    r = client.get(DAY)
    assert r.status_code == 200 and r.get_json()["times"] == ["10:00", "11:00"]


def test_day_still_errors_when_there_is_nothing_to_fall_back_on(client, monkeypatch):
    monkeypatch.setattr(app_mod, "derive_availability", _raising(RuntimeError("429")))
    assert client.get(DAY).status_code == 502


def test_day_does_not_serve_an_answer_past_the_stale_cap(client, monkeypatch):
    monkeypatch.setattr(app_mod, "derive_availability",
                        lambda *a, **k: {"claire-ng": ["10:00"]})
    client.get(DAY)
    monkeypatch.setattr(app_mod, "AVAIL_TTL_S", 0)
    monkeypatch.setattr(app_mod, "AVAIL_STALE_MAX_S", -1)
    monkeypatch.setattr(app_mod, "derive_availability", _raising(RuntimeError("429")))
    assert client.get(DAY).status_code == 502


def test_month_still_loading_is_a_retryable_503_not_a_failure(client, monkeypatch):
    monkeypatch.setattr(app_mod, "derive_available_days",
                        _raising(PlatoBusy("month still loading")))
    r = client.get(MONTH)
    assert r.status_code == 503
    assert r.get_json()["error"] == "loading"


def test_month_serves_old_shading_rather_than_an_error(client, monkeypatch):
    monkeypatch.setattr(app_mod, "derive_available_days",
                        lambda *a, **k: ["2030-01-05"])
    assert client.get(MONTH).get_json()["available"] == ["2030-01-05"]

    monkeypatch.setattr(app_mod, "SUMMARY_TTL_S", 0)
    for exc in (PlatoBusy("loading"), RuntimeError("429")):
        monkeypatch.setattr(app_mod, "derive_available_days", _raising(exc))
        r = client.get(MONTH)
        assert r.status_code == 200 and r.get_json()["available"] == ["2030-01-05"]


def test_day_out_of_plato_budget_is_a_retryable_503_with_a_wait(client, monkeypatch):
    """The 2026-10 "couldn't load times" errors were all this: a 429 cooldown
    while an ingestion job paged Plato on the same key. The browser waits
    retry_after seconds and asks again instead of giving up."""
    monkeypatch.setattr(app_mod, "derive_availability",
                        _raising(PlatoThrottled("cooling down after a 429", retry_after_s=14.2)))
    r = client.get(DAY)
    assert r.status_code == 503
    assert r.get_json()["error"] == "loading"
    assert r.get_json()["retry_after"] == 15


# --- /internal/refresh-snapshot ---------------------------------------------

class _SnapPlato:
    def __init__(self, fail=None):
        self.windows = []
        self.fail = fail

    def refresh_snapshot(self, start, end):
        self.windows.append((start, end))
        if self.fail:
            raise self.fail
        return {"rows": 3, "window": [start, end], "took_s": 0.1}

    def snapshot_age_s(self):
        return 5.0


@pytest.fixture
def snap(monkeypatch, client):
    monkeypatch.setattr(app_mod, "_snapshot_last_try", float("-inf"))
    p = _SnapPlato()
    monkeypatch.setattr(app_mod, "plato", lambda: p)
    return p


def test_refresh_pages_the_whole_bookable_window(client, snap):
    r = client.post("/internal/refresh-snapshot")
    assert r.status_code == 200 and r.get_json()["ok"]
    (start, end), = snap.windows
    today = datetime.now(app_mod.SGT).date()
    assert start == today.isoformat()
    assert end == (today + app_mod.timedelta(days=app_mod.MAX_ADVANCE_DAYS)).isoformat()


def test_refresh_is_throttled_however_often_it_is_hit(client, snap):
    """Unauthenticated by design, so it must not be a lever for burning the
    clinic's Plato budget: back-to-back hits page Plato once."""
    client.post("/internal/refresh-snapshot")
    r = client.post("/internal/refresh-snapshot")
    assert r.get_json()["skipped"] == "refreshed recently"
    assert len(snap.windows) == 1


def test_refresh_drops_answers_derived_from_the_old_snapshot(client, snap):
    app_mod._avail_cache[("k",)] = (0.0, {})
    app_mod._summary_cache[("k",)] = (0.0, {})
    client.post("/internal/refresh-snapshot")
    assert app_mod._avail_cache == {} and app_mod._summary_cache == {}


def test_a_refresh_plato_cannot_serve_is_a_503(client, snap):
    snap.fail = PlatoBusy("window still loading")
    r = client.post("/internal/refresh-snapshot")
    assert r.status_code == 503
    assert r.get_json()["ok"] is False
