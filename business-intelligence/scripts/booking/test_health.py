"""Unit tests for the readiness endpoint (no network — stub Plato).

/healthcheck stayed 200 through the 2026-09-01 outage while /book was
unusable. /healthcheck/deep is the signal the uptime check watches, so these
pin exactly when it goes red.
"""
from __future__ import annotations

import pytest

from booking import app as app_mod


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(app_mod, "_deep_cache", None, raising=False)
    app_mod.app.config["TESTING"] = True
    with app_mod.app.test_client() as c:
        yield c


def _stub_days(monkeypatch, result):
    """Swap the derivation for a canned answer (or an exception to raise)."""
    def fake(*_a, **_kw):
        if isinstance(result, Exception):
            raise result
        return result
    monkeypatch.setattr(app_mod, "derive_available_days", fake)
    monkeypatch.setattr(app_mod, "plato", lambda: object())


def test_liveness_never_touches_plato(client, monkeypatch):
    _stub_days(monkeypatch, RuntimeError("Plato is down"))
    assert client.get("/healthcheck").status_code == 200


def test_deep_is_green_when_dates_are_bookable(client, monkeypatch):
    _stub_days(monkeypatch, ["2026-09-04", "2026-09-05"])
    r = client.get("/healthcheck/deep")
    assert r.status_code == 200
    assert r.get_json()["ok"] is True
    assert r.get_json()["bookable_dates"] == 2
    assert r.get_json()["first_available"] == "2026-09-04"


def test_deep_goes_red_when_derivation_throws(client, monkeypatch):
    """The exact shape of the outage: Plato 429s / returns a poisoned config,
    derive throws, and the visitor sees "We couldn't load times just now"."""
    _stub_days(monkeypatch, RuntimeError("429 Client Error: Too Many Requests"))
    r = client.get("/healthcheck/deep")
    assert r.status_code == 503
    body = r.get_json()
    assert body["ok"] is False
    assert body["reason"] == "derivation_failed"
    assert "429" in body["error"]


def test_deep_goes_red_on_an_empty_calendar(client, monkeypatch):
    """Runs clean but offers nothing — to a visitor that is still an outage."""
    _stub_days(monkeypatch, [])
    r = client.get("/healthcheck/deep")
    assert r.status_code == 503
    assert r.get_json()["reason"] == "no_bookable_dates"


def test_deep_result_is_cached(client, monkeypatch):
    """The check costs Plato budget; repeated hits must not spend it."""
    calls = []

    def fake(*_a, **_kw):
        calls.append(1)
        return ["2026-09-04"]

    monkeypatch.setattr(app_mod, "derive_available_days", fake)
    monkeypatch.setattr(app_mod, "plato", lambda: object())
    for _ in range(5):
        assert client.get("/healthcheck/deep").status_code == 200
    assert len(calls) == 1


def test_deep_caches_failures_too(client, monkeypatch):
    """A red check must not re-hammer Plato while it is already struggling."""
    calls = []

    def fake(*_a, **_kw):
        calls.append(1)
        raise RuntimeError("boom")

    monkeypatch.setattr(app_mod, "derive_available_days", fake)
    monkeypatch.setattr(app_mod, "plato", lambda: object())
    for _ in range(5):
        assert client.get("/healthcheck/deep").status_code == 503
    assert len(calls) == 1
