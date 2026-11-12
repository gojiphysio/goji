"""/api/book bot check: honeypot, minimum fill time, Cloudflare Turnstile.
No Plato, mail, BigQuery or Cloudflare: all stubbed."""
from __future__ import annotations

import pytest

from booking import app as app_mod

DRAFT = {"service": "physiotherapy", "date": "2026-07-15", "time": "10:00",
         "name": "Jane Tan", "phone": "+65 9123 4567", "email": "jane@example.com",
         "session_id": "s1", "elapsed_ms": 45000}


@pytest.fixture
def client(monkeypatch):
    calls = {"booked": 0, "tracked": []}
    monkeypatch.setattr(app_mod, "_hits", {})
    monkeypatch.setattr(app_mod, "TURNSTILE_SECRET", "")
    monkeypatch.setattr(app_mod, "_track_async",
                        lambda stage, *a, **kw: calls["tracked"].append((stage, kw.get("detail"))))
    monkeypatch.setattr(app_mod, "plato", lambda: None)
    monkeypatch.setattr(app_mod.mailer, "send_admin_booking_email", lambda *a: None)
    monkeypatch.setattr(app_mod.mailer, "send_customer_booking_email", lambda *a: None)

    def create(_p, _d):
        calls["booked"] += 1
        return {"reference": "GOJI-ABC123"}
    monkeypatch.setattr(app_mod, "create_booking", create)
    app_mod.app.config["TESTING"] = True
    with app_mod.app.test_client() as c:
        c.calls = calls
        yield c


def _book(c, **over):
    return c.post("/api/book", json={**DRAFT, **over},
                  headers={"X-Forwarded-For": "9.9.9.9, 1.2.3.4"})


class _Resp:
    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body


def _turnstile(monkeypatch, body=None, exc=None):
    """Turn Turnstile on and stub Cloudflare's answer; returns the calls made."""
    sent = []
    monkeypatch.setattr(app_mod, "TURNSTILE_SECRET", "secret")

    def post(url, data=None, timeout=None):
        sent.append((url, data))
        if exc:
            raise exc
        return _Resp(body)
    monkeypatch.setattr(app_mod.requests, "post", post)
    return sent


def test_a_normal_submission_books(client):
    assert _book(client).status_code == 200
    assert client.calls["booked"] == 1


def test_filled_honeypot_is_refused_before_plato(client):
    r = _book(client, company_url="http://spam.example")
    assert r.status_code == 400 and r.get_json()["code"] == "bot_check"
    assert client.calls["booked"] == 0
    assert ("book_error", "bot_honeypot") in client.calls["tracked"]


def test_instant_submission_is_refused(client):
    r = _book(client, elapsed_ms=400)
    assert r.status_code == 400 and r.get_json()["code"] == "bot_check"
    assert client.calls["booked"] == 0


def test_missing_fill_time_is_tolerated(client):
    """An open tab may still be running the form from before this shipped."""
    draft = {k: v for k, v in DRAFT.items() if k != "elapsed_ms"}
    r = client.post("/api/book", json=draft, headers={"X-Forwarded-For": "1.2.3.4"})
    assert r.status_code == 200


def test_turnstile_off_needs_no_token(client):
    assert _book(client).status_code == 200


def test_turnstile_on_refuses_a_missing_token(client, monkeypatch):
    sent = _turnstile(monkeypatch, {"success": True})
    r = _book(client)
    assert r.status_code == 400 and r.get_json()["code"] == "bot_check"
    assert sent == [] and client.calls["booked"] == 0
    assert ("book_error", "bot_captcha_missing") in client.calls["tracked"]


def test_turnstile_on_refuses_a_rejected_token(client, monkeypatch):
    _turnstile(monkeypatch, {"success": False, "error-codes": ["invalid-input-response"]})
    r = _book(client, turnstile_token="forged")
    assert r.status_code == 400 and client.calls["booked"] == 0


def test_turnstile_on_books_with_a_valid_token(client, monkeypatch):
    sent = _turnstile(monkeypatch, {"success": True})
    assert _book(client, turnstile_token="tok").status_code == 200
    url, data = sent[0]
    assert url == app_mod.TURNSTILE_VERIFY_URL
    assert data == {"secret": "secret", "response": "tok", "remoteip": "1.2.3.4"}


def test_cloudflare_outage_does_not_close_the_form(client, monkeypatch):
    _turnstile(monkeypatch, exc=ConnectionError("down"))
    assert _book(client, turnstile_token="tok").status_code == 200


def test_bot_attempts_count_toward_the_hourly_limit(client):
    for _ in range(app_mod.BOOK_ATTEMPTS_PER_IP_HOUR):
        assert _book(client, company_url="x").status_code == 400
    assert _book(client).status_code == 429
