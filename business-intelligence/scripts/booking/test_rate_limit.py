"""/api/book abuse limits (2026-11-12: a scanner created real Plato bookings).
No Plato, mail or BigQuery: create_booking and the side effects are stubbed."""
from __future__ import annotations

import pytest

from booking import app as app_mod
from booking.booking import BookingError

DRAFT = {"service": "physiotherapy", "date": "2026-07-15", "time": "10:00",
         "name": "Jane Tan", "phone": "+65 9123 4567", "email": "jane@example.com"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(app_mod, "_hits", {})
    monkeypatch.setattr(app_mod, "_track_async", lambda *a, **kw: None)
    monkeypatch.setattr(app_mod, "plato", lambda: None)
    monkeypatch.setattr(app_mod.mailer, "send_admin_booking_email", lambda *a: None)
    monkeypatch.setattr(app_mod.mailer, "send_customer_booking_email", lambda *a: None)
    app_mod.app.config["TESTING"] = True
    with app_mod.app.test_client() as c:
        yield c


def _ok(monkeypatch):
    monkeypatch.setattr(app_mod, "create_booking",
                        lambda _p, _d: {"reference": "GOJI-ABC123"})


def _book(c, ip="1.2.3.4", **over):
    return c.post("/api/book", json={**DRAFT, **over},
                  headers={"X-Forwarded-For": f"9.9.9.9, {ip}"})


def test_same_phone_is_capped_per_day(client, monkeypatch):
    _ok(monkeypatch)
    assert _book(client, ip="1.1.1.1").status_code == 200
    assert _book(client, ip="2.2.2.2", email="b@example.com").status_code == 200
    r = _book(client, ip="3.3.3.3", email="c@example.com")
    assert r.status_code == 429 and r.get_json()["code"] == "rate_limited"


def test_one_shared_ip_is_not_capped(client, monkeypatch):
    """SG mobile carriers put many customers behind one IP (CGNAT): different
    people booking from the same address must all get through."""
    _ok(monkeypatch)
    for i in range(10):
        assert _book(client, ip="5.5.5.5", phone=f"+65 8000 00{i:02d}",
                     email=f"p{i}@example.com").status_code == 200


def test_failed_attempts_from_one_ip_are_not_capped(client, monkeypatch):
    def fail(_p, _d):
        raise BookingError("That time is no longer available.", "slot_taken")
    monkeypatch.setattr(app_mod, "create_booking", fail)
    for _ in range(15):
        assert _book(client).status_code == 409
