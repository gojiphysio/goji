"""/internal/confirm: a WhatsApp reminder's Confirm tap marks the appointment
Confirmed in Plato (code_Right). No network: Plato is a fake."""
from __future__ import annotations

from datetime import datetime

import pytest

from booking import app as app_mod
from booking.booking import CONFIRMED_CODE, BookingError, confirm_appointment

NOW = datetime(2026, 11, 26, 9, 0)
APPT = {"_id": "abc123", "starttime": "2026-11-28 10:00:00", "endtime": "2026-11-28 11:00:00",
        "title": "Sarah Tan", "handphone": "+65 9123 4567", "patient_id": "", "code_Right": ""}


class FakePlato:
    def __init__(self, appt=None, patient=None):
        self.appt, self.patient = appt or dict(APPT), patient or {}
        self.puts: list = []

    def get(self, path, **kw):
        if path.startswith("/patient/"):
            return [self.patient]
        return [self.appt]  # Plato answers with a one-item list

    def update_appointment(self, aid, payload, days=()):
        self.puts.append((aid, payload))
        return {"success": True}


def test_tap_marks_the_appointment_confirmed():
    p = FakePlato()
    r = confirm_appointment(p, {"appointment_id": "abc123", "phone": "6591234567"}, now=NOW)
    assert p.puts == [("abc123", {"code_Right": CONFIRMED_CODE})]
    assert r["ok"] and not r["already"] and r["reference"] == "GOJI-ABC123"


def test_already_confirmed_writes_nothing():
    p = FakePlato({**APPT, "code_Right": CONFIRMED_CODE})
    assert confirm_appointment(p, {"appointment_id": "abc123", "phone": "91234567"},
                               now=NOW)["already"]
    assert p.puts == []


def test_linked_patient_matched_by_profile_phone():
    p = FakePlato({**APPT, "handphone": "", "patient_id": "p1"},
                  patient={"name": "Sarah Tan", "handphone": "91234567"})
    confirm_appointment(p, {"appointment_id": "abc123", "phone": "+6591234567"}, now=NOW)
    assert p.puts


@pytest.mark.parametrize("appt, phone, code", [
    (APPT, "+6588887777", "not_found"),                            # someone else's
    ({**APPT, "cancelled": 1}, "91234567", "not_found"),
    ({**APPT, "starttime": "2026-11-25 10:00:00"}, "91234567", "past"),
])
def test_refusals(appt, phone, code):
    p = FakePlato(appt)
    with pytest.raises(BookingError) as e:
        confirm_appointment(p, {"appointment_id": "abc123", "phone": phone}, now=NOW)
    assert e.value.code == code and p.puts == []


def test_dry_run_writes_nothing():
    p = FakePlato()
    confirm_appointment(p, {"appointment_id": "abc123", "phone": "91234567"},
                        now=NOW, dry_run=True)
    assert p.puts == []


def test_route_needs_the_token_and_maps_errors(monkeypatch):
    monkeypatch.setattr(app_mod, "INTERNAL_TOKEN", "tok")
    monkeypatch.setattr(app_mod, "_sgt_now", lambda: NOW)
    fake = FakePlato()
    monkeypatch.setattr(app_mod, "plato", lambda: fake)
    c = app_mod.app.test_client()
    body = {"appointment_id": "abc123", "phone": "91234567"}
    assert c.post("/internal/confirm", json=body).status_code == 403
    r = c.post("/internal/confirm", json=body, headers={"X-Internal-Token": "tok"})
    assert r.status_code == 200 and r.get_json()["ok"]
    r = c.post("/internal/confirm", json={**body, "phone": "88887777"},
               headers={"X-Internal-Token": "tok"})
    assert r.status_code == 404
