"""POST /internal/cancel: the WhatsApp assistant cancels a patient's existing
appointment with 24 hours' notice or more. Plato is a stub; mail is recorded.
No network."""
from __future__ import annotations

from datetime import datetime

import pytest

from booking import app as app_mod
from booking.test_reschedule import APPT_ID, ORIGINAL, PHONE, TOKEN, NoWritePlato, StubPlato
from booking.test_booking import NOW

CANCEL = {"phone": PHONE, "date": "2026-07-16", "time": "10:00", "dry_run": False}


class DeletingPlato(StubPlato):
    def __init__(self, appts=None):
        super().__init__(appts)
        self.deleted: list[tuple[str, tuple]] = []

    def delete_appointment(self, _id, days=()):
        self.deleted.append((_id, days))
        return {"success": True}


@pytest.fixture
def client(monkeypatch):
    admin = []
    monkeypatch.setattr(app_mod, "INTERNAL_TOKEN", TOKEN)
    monkeypatch.setattr(app_mod, "_sgt_now", lambda: NOW)
    monkeypatch.setattr(app_mod.mailer, "send_admin_cancel_email",
                        lambda r, b: admin.append((r, b)))
    stub = DeletingPlato()
    monkeypatch.setattr(app_mod, "plato", lambda: stub)
    app_mod.app.config["TESTING"] = True
    with app_mod.app.test_client() as c:
        c.admin, c.stub = admin, stub
        yield c


def _use(client, monkeypatch, stub):
    monkeypatch.setattr(app_mod, "plato", lambda: stub)
    client.stub = stub


def _cancel(c, token=TOKEN, **over):
    headers = {"X-Internal-Token": token} if token is not None else {}
    return c.post("/internal/cancel", json={**CANCEL, **over}, headers=headers)


def test_route_is_absent_without_a_configured_token(client, monkeypatch):
    monkeypatch.setattr(app_mod, "INTERNAL_TOKEN", "")
    assert _cancel(client).status_code == 404
    assert client.stub.deleted == []


@pytest.mark.parametrize("token", ["wrong", "", None])
def test_wrong_or_missing_token_is_forbidden(client, token):
    assert _cancel(client, token=token).status_code == 403
    assert client.stub.deleted == []


@pytest.mark.parametrize("over", [{"dry_run": "false"}, {"date": "16/07/2026"},
                                  {"time": "10am"}, {"phone": "abc"}, {"patient_id": "../x"}])
def test_invalid_requests_are_400(client, over):
    r = _cancel(client, **over)
    assert r.status_code == 400 and r.get_json()["code"] == "invalid"
    assert client.stub.deleted == []


def test_cancel_deletes_the_appointment_and_emails_the_clinic(client):
    r = _cancel(client)
    body = r.get_json()
    assert r.status_code == 200 and body["ok"] and body["dry_run"] is False
    assert body["reference"] == "GOJI-" + APPT_ID[-6:].upper()
    assert body["date"] == "2026-07-16" and body["time"] == "10:00"
    assert body["service"] == "Physiotherapy"
    assert client.stub.deleted == [(APPT_ID, ("2026-07-16",))]
    assert len(client.admin) == 1


def test_dry_run_writes_and_sends_nothing(client, monkeypatch):
    _use(client, monkeypatch, NoWritePlato())
    r = _cancel(client, dry_run=True)
    assert r.status_code == 200 and r.get_json()["dry_run"] is True
    assert client.admin == []


def test_someone_elses_appointment_is_not_found(client):
    r = _cancel(client, phone="+65 8000 0000")
    assert r.status_code == 404 and r.get_json()["code"] == "not_found"
    assert client.stub.deleted == []


def test_within_24h_is_a_late_change_for_staff(client, monkeypatch):
    monkeypatch.setattr(app_mod, "_sgt_now", lambda: datetime(2026, 7, 15, 10, 1))
    r = _cancel(client)
    assert r.status_code == 409 and r.get_json()["code"] == "late_change"
    assert client.stub.deleted == []


def test_exactly_24h_ahead_is_allowed(client, monkeypatch):
    monkeypatch.setattr(app_mod, "_sgt_now", lambda: datetime(2026, 7, 15, 10, 0))
    assert _cancel(client).status_code == 200


def test_home_visits_stay_with_staff(client, monkeypatch):
    _use(client, monkeypatch, DeletingPlato([{**ORIGINAL, "code_Bottom": "sCla"}]))
    r = _cancel(client)
    assert r.status_code == 409 and r.get_json()["code"] == "unsupported"
    assert client.stub.deleted == []


def test_unknown_calendar_stays_with_staff(client, monkeypatch):
    _use(client, monkeypatch, DeletingPlato([{**ORIGINAL, "color": "zzzz"}]))
    r = _cancel(client)
    assert r.status_code == 409 and r.get_json()["code"] == "unsupported"


def test_plato_refusing_the_delete_is_a_502(client, monkeypatch):
    class Refusing(DeletingPlato):
        def delete_appointment(self, _id, days=()):
            return {"success": False}
    _use(client, monkeypatch, Refusing())
    r = _cancel(client)
    assert r.status_code == 502 and r.get_json()["code"] == "plato_error"
    assert client.admin == []
