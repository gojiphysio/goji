"""POST /internal/reschedule: the WhatsApp assistant moves a patient's existing
appointment (same clinician, service and length). Plato is a stub; mail and the
assistant callback are recorded. No network."""
from __future__ import annotations

from datetime import datetime

import pytest

from booking import app as app_mod
from booking import mailer
from booking.booking import BookingError, _service_for, reschedule_appointment
from booking.plato import PlatoClient
from booking.test_booking import CFG, NOW

TOKEN = "s3cret-token"
APPT_ID = "65f0c0ffee00abcdef123456"
PHONE = "+65 9123 4567"
# Thursday 16 July 2026, 10:00-11:00 with Cheryl: 49h after NOW.
ORIGINAL = {
    "_id": APPT_ID, "title": "Jane Tan", "color": "blue", "code_Bottom": "hDWW",
    "starttime": "2026-07-16 10:00:00", "endtime": "2026-07-16 11:00:00",
    "handphone": "91234567", "description": "Physiotherapy. Booked via website.",
}
MOVE = {"phone": PHONE, "old_date": "2026-07-16", "old_time": "10:00",
        "new_date": "2026-07-17", "new_time": "14:00", "dry_run": False}


class StubPlato:
    """Serves each day's rows; records writes."""

    def __init__(self, appts=None):
        self.appts = [dict(a) for a in (appts if appts is not None else [ORIGINAL])]
        self.updates: list[tuple[str, dict, tuple]] = []
        self.fresh_reads: list[tuple[str, bool]] = []

    def appointments(self, start, end, fresh=False):
        self.fresh_reads.append((start, fresh))
        return [a for a in self.appts if start <= a["starttime"][:10] <= end]

    def online_booking_config(self):
        return CFG

    def update_appointment(self, _id, payload, days=()):
        self.updates.append((_id, payload, days))
        return {"success": True}


class NoWritePlato(StubPlato):
    """Any write fails the test."""

    def update_appointment(self, *a, **kw):
        pytest.fail(f"dry run attempted a Plato update: {a}")

    def put(self, *a, **kw):
        pytest.fail(f"dry run attempted a Plato PUT: {a}")

    def post(self, *a, **kw):
        pytest.fail(f"dry run attempted a Plato POST: {a}")

    def create_appointment(self, *a, **kw):
        pytest.fail(f"dry run attempted a Plato create: {a}")

    def delete_appointment(self, *a, **kw):
        pytest.fail(f"dry run attempted a Plato delete: {a}")


@pytest.fixture
def client(monkeypatch):
    calls = {"admin": [], "posted": []}
    monkeypatch.setattr(app_mod, "INTERNAL_TOKEN", TOKEN)
    monkeypatch.setattr(app_mod, "WA_AGENT_URL", "https://wa.example.run.app")
    monkeypatch.setattr(app_mod, "_sgt_now", lambda: NOW)
    monkeypatch.setattr(app_mod.mailer, "send_admin_reschedule_email",
                        lambda r, b: calls["admin"].append((r, b)))
    monkeypatch.setattr(app_mod, "_run_async", lambda fn: fn())

    def post(url, json=None, headers=None, timeout=None):
        calls["posted"].append({"url": url, "json": json, "headers": headers})

        class R:
            status_code = 200
        return R()
    monkeypatch.setattr(app_mod.requests, "post", post)
    stub = StubPlato()
    monkeypatch.setattr(app_mod, "plato", lambda: stub)
    app_mod.app.config["TESTING"] = True
    with app_mod.app.test_client() as c:
        c.calls, c.stub = calls, stub
        yield c


def _use(client, monkeypatch, stub):
    monkeypatch.setattr(app_mod, "plato", lambda: stub)
    client.stub = stub


def _move(c, token=TOKEN, **over):
    headers = {"X-Internal-Token": token} if token is not None else {}
    return c.post("/internal/reschedule", json={**MOVE, **over}, headers=headers)


# ---- auth + request validation ----------------------------------------------

def test_route_is_absent_without_a_configured_token(client, monkeypatch):
    monkeypatch.setattr(app_mod, "INTERNAL_TOKEN", "")
    assert _move(client).status_code == 404
    assert client.stub.updates == []


@pytest.mark.parametrize("token", ["wrong", "", None, TOKEN + "x"])
def test_wrong_or_missing_token_is_forbidden(client, token):
    r = _move(client, token=token)
    assert r.status_code == 403 and r.get_json()["code"] == "forbidden"
    assert client.stub.updates == []


@pytest.mark.parametrize("value", ["true", "false", 1, 0, None])
def test_dry_run_must_be_a_json_boolean(client, value):
    r = _move(client, dry_run=value)
    assert r.status_code == 400 and r.get_json()["code"] == "invalid"
    assert client.stub.updates == []


@pytest.mark.parametrize("over", [
    {"old_date": "16/07/2026"}, {"new_time": "2pm"}, {"phone": "abc"},
    {"new_date": "2026-07-16", "new_time": "10:00"},  # same slot
    {"new_date": "2026-07-13"},                       # in the past
    {"patient_id": "../x"},
])
def test_invalid_requests_are_400(client, over):
    r = _move(client, **over)
    assert r.status_code == 400 and r.get_json()["code"] == "invalid"


def test_beyond_the_booking_window_is_refused(client):
    r = _move(client, new_date="2026-09-30")  # 78 days after NOW
    assert r.status_code == 400 and r.get_json()["code"] == "too_far"


# ---- finding the original ---------------------------------------------------

def test_no_match_is_404(client):
    r = _move(client, phone="+65 8000 0000")
    assert r.status_code == 404
    assert r.get_json() == {"ok": False, "error": "We couldn't find that appointment.",
                            "code": "not_found"}


def test_wrong_time_is_404(client):
    assert _move(client, old_time="10:30").status_code == 404


@pytest.mark.parametrize("dead", [{"cancelled": 1}, {"void": "1"}, {"status": "Cancelled"},
                                  {"title": "Annual leave"}, {"type": "leave"}])
def test_cancelled_void_or_leave_entries_never_match(client, monkeypatch, dead):
    _use(client, monkeypatch, StubPlato([{**ORIGINAL, **dead}]))
    assert _move(client).status_code == 404


def test_two_matches_are_ambiguous(client, monkeypatch):
    other = {**ORIGINAL, "_id": "other0000001", "color": "6hpO"}
    _use(client, monkeypatch, StubPlato([ORIGINAL, other]))
    r = _move(client)
    assert r.status_code == 409 and r.get_json()["code"] == "ambiguous"
    assert client.stub.updates == []


def test_the_original_is_read_fresh(client):
    _move(client, dry_run=True)
    assert ("2026-07-16", True) in client.stub.fresh_reads


def test_patient_id_picks_the_linked_appointment(client, monkeypatch):
    """A parent and child share a phone: patient_id decides, and an appointment
    linked to someone else is never moved."""
    child = {**ORIGINAL, "patient_id": "child-1"}
    parent = {**ORIGINAL, "_id": "parent000001", "color": "6hpO",
              "patient_id": "parent-1", "handphone": ""}
    _use(client, monkeypatch, StubPlato([child, parent]))
    r = _move(client, patient_id="parent-1", dry_run=True)
    assert r.status_code == 200 and r.get_json()["clinician_name"] == "Claire Ng"
    assert _move(client, patient_id="someone-else").status_code == 404


def test_patient_id_still_finds_an_unlinked_website_booking_by_phone(client):
    r = _move(client, patient_id="p-123", dry_run=True)
    assert r.status_code == 200


# ---- policy -----------------------------------------------------------------

def test_change_within_24h_of_the_original_is_a_late_change(client, monkeypatch):
    monkeypatch.setattr(app_mod, "_sgt_now", lambda: datetime(2026, 7, 15, 10, 1))
    r = _move(client)
    assert r.status_code == 409 and r.get_json()["code"] == "late_change"
    assert client.stub.updates == []


def test_exactly_24h_ahead_is_allowed(client, monkeypatch):
    monkeypatch.setattr(app_mod, "_sgt_now", lambda: datetime(2026, 7, 15, 10, 0))
    assert _move(client, dry_run=True).status_code == 200


def test_home_visits_stay_with_staff(client, monkeypatch):
    _use(client, monkeypatch, StubPlato([{**ORIGINAL, "code_Bottom": "sCla"}]))
    r = _move(client, dry_run=True)
    assert r.status_code == 409 and r.get_json()["code"] == "unsupported"


@pytest.mark.parametrize("over", [{"code_Bottom": ""},                         # untyped
                                  {"endtime": "2026-07-16 11:30:00"},          # 90 min
                                  {"color": "zzzz"}])                          # unknown calendar
def test_appointments_we_cant_map_stay_with_staff(client, monkeypatch, over):
    _use(client, monkeypatch, StubPlato([{**ORIGINAL, **over}]))
    r = _move(client, dry_run=True)
    assert r.status_code == 409 and r.get_json()["code"] == "unsupported"


def test_service_is_read_from_type_and_length():
    assert _service_for("hDWW", 60) == ("physiotherapy", "")
    assert _service_for("hDWW", 55) == ("physiotherapy", "55min")
    assert _service_for("hDWW", 85) == ("mummy-baby", "")
    assert _service_for("qLbH", 60) == ("strength-conditioning", "")
    assert _service_for("hDWW", 90) is None


# ---- the new slot -----------------------------------------------------------

def test_taken_new_slot_is_refused(client, monkeypatch):
    clash = {"_id": "x1", "title": "Other", "color": "blue",
             "starttime": "2026-07-17 14:30:00", "endtime": "2026-07-17 15:30:00"}
    _use(client, monkeypatch, StubPlato([ORIGINAL, clash]))
    r = _move(client)
    assert r.status_code == 409 and r.get_json()["code"] == "slot_taken"
    assert client.stub.updates == [] and client.calls["admin"] == []


def test_another_clinicians_booking_does_not_block(client, monkeypatch):
    clash = {"_id": "x1", "title": "Other", "color": "6hpO",
             "starttime": "2026-07-17 14:00:00", "endtime": "2026-07-17 15:00:00"}
    _use(client, monkeypatch, StubPlato([ORIGINAL, clash]))
    assert _move(client).status_code == 200


def test_outside_the_clinicians_hours_is_slot_taken(client):
    r = _move(client, new_time="17:00")  # Cheryl's rule ends 17:00
    assert r.status_code == 409 and r.get_json()["code"] == "slot_taken"


def test_the_new_slot_is_rechecked_fresh(client):
    _move(client, dry_run=True)
    assert ("2026-07-17", True) in client.stub.fresh_reads


def test_moving_over_its_own_current_slot_is_allowed(client):
    """10:00-11:00 -> 10:30-11:30 the same day overlaps the appointment itself;
    that must not count as a clash."""
    r = _move(client, new_date="2026-07-16", new_time="10:30")
    assert r.status_code == 200
    _id, payload, days = client.stub.updates[0]
    assert payload["starttime"] == "2026-07-16 10:30:00"
    assert days == ("2026-07-16", "2026-07-16")


def test_own_slot_is_hidden_but_other_same_day_bookings_still_block(client, monkeypatch):
    clash = {"_id": "x1", "title": "Other", "color": "blue",
             "starttime": "2026-07-16 11:00:00", "endtime": "2026-07-16 12:00:00"}
    _use(client, monkeypatch, StubPlato([ORIGINAL, clash]))
    r = _move(client, new_date="2026-07-16", new_time="10:30")
    assert r.status_code == 409 and r.get_json()["code"] == "slot_taken"


# ---- dry run vs real move ---------------------------------------------------

def test_dry_run_never_writes_or_notifies(client, monkeypatch):
    _use(client, monkeypatch, NoWritePlato())
    r = _move(client, dry_run=True)
    assert r.status_code == 200
    assert r.get_json() == {
        "ok": True, "dry_run": True, "reference": "GOJI-123456",
        "clinician_name": "Cheryl Long", "service": "Physiotherapy",
        "old_date": "2026-07-16", "old_time": "10:00",
        "new_date": "2026-07-17", "new_time": "14:00",
    }
    assert client.calls["admin"] == [] and client.calls["posted"] == []


def test_real_move_puts_only_the_new_times_and_a_note(client):
    r = _move(client)
    assert r.status_code == 200 and r.get_json()["dry_run"] is False
    assert client.stub.updates == [(APPT_ID, {
        "starttime": "2026-07-17 14:00:00",
        "endtime": "2026-07-17 15:00:00",
        "description": ("Physiotherapy. Booked via website.\n"
                        "Moved via WhatsApp assistant from 2026-07-16 10:00."),
    }, ("2026-07-16", "2026-07-17"))]


def test_no_description_field_means_no_description_sent(client, monkeypatch):
    bare = {k: v for k, v in ORIGINAL.items() if k != "description"}
    _use(client, monkeypatch, StubPlato([bare]))
    _move(client)
    assert set(client.stub.updates[0][1]) == {"starttime", "endtime"}


def test_variant_length_is_kept(client, monkeypatch):
    _use(client, monkeypatch, StubPlato([{**ORIGINAL, "endtime": "2026-07-16 10:55:00"}]))
    _move(client)
    assert client.stub.updates[0][1]["endtime"] == "2026-07-17 14:55:00"


def test_real_move_emails_the_clinic_and_calls_the_assistant(client):
    _move(client)
    (result, body), = client.calls["admin"]
    assert result["old_date"] == "2026-07-16" and result["new_time"] == "14:00"
    assert body["phone"] == PHONE
    (posted,) = client.calls["posted"]
    assert posted["url"] == "https://wa.example.run.app/internal/booking-confirmed"
    assert posted["headers"] == {"X-Internal-Token": TOKEN}
    assert posted["json"] == {"phone": PHONE, "reference": "GOJI-123456",
                              "service": "Physiotherapy", "date": "2026-07-17",
                              "time": "14:00", "clinician_name": "Cheryl Long",
                              "source": "whatsapp", "first_name": "",
                              "send_template": False, "form_token": ""}


def test_plato_write_failure_is_502_and_notifies_nobody(client, monkeypatch):
    class Failing(StubPlato):
        def update_appointment(self, *a, **kw):
            raise RuntimeError("plato down")
    _use(client, monkeypatch, Failing())
    r = _move(client)
    assert r.status_code == 502 and r.get_json()["code"] == "plato_error"
    assert client.calls["admin"] == [] and client.calls["posted"] == []


def test_plato_read_failure_is_502(client, monkeypatch):
    class Down(StubPlato):
        def appointments(self, *a, **kw):
            raise RuntimeError("plato down")
    _use(client, monkeypatch, Down())
    r = _move(client)
    assert r.status_code == 502 and r.get_json()["code"] == "plato_error"


def test_plato_rejecting_the_put_is_a_plato_error():
    class Rejects(StubPlato):
        def update_appointment(self, *a, **kw):
            return {"success": False}
    with pytest.raises(BookingError) as e:
        reschedule_appointment(Rejects(), MOVE, now=NOW)
    assert e.value.code == "plato_error"


# ---- Plato client: the write clears the availability caches -----------------

class RecordingClient(PlatoClient):
    def __init__(self):
        super().__init__(db="test", token="test-token")
        self.puts: list[tuple[str, dict]] = []

    def put(self, path, payload):
        self.puts.append((path, payload))
        return {}


def test_update_appointment_puts_and_clears_caches():
    p = RecordingClient()
    p._appts_cache[("2026-07-16", "2026-07-16")] = (0.0, [ORIGINAL])
    p._partial[("2026-07-01", "2026-07-31")] = (0.0, 2, [])
    p.update_appointment(APPT_ID, {"starttime": "2026-07-17 14:00:00"},
                         days=("2026-07-16", "2026-07-17"))
    assert p.puts == [(f"appointment/{APPT_ID}", {"starttime": "2026-07-17 14:00:00"})]
    assert p._appts_cache == {} and p._partial == {}
    assert set(p._dirty_days) == {"2026-07-16", "2026-07-17"}


# ---- the clinic notice ------------------------------------------------------

def test_admin_reschedule_email(monkeypatch):
    sent = []
    monkeypatch.setattr(mailer, "SMTP_PASS", "x")
    monkeypatch.setattr(mailer, "_send", lambda msg, what, ref: sent.append(msg))
    result = reschedule_appointment(StubPlato(), {**MOVE, "dry_run": True}, now=NOW,
                                    dry_run=True)
    mailer.send_admin_reschedule_email(result, MOVE)
    (msg,) = sent
    assert msg["Subject"].startswith("Rescheduled via WhatsApp assistant")
    assert msg["Cc"] == "cheryl.long@gojiphysio.com"
    body = msg.get_content()
    assert "2026-07-16 10:00" in body and "2026-07-17 14:00" in body
    assert "GOJI-123456" in body
