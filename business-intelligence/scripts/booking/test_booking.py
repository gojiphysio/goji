"""Unit tests for create_booking (stub Plato — no network, no writes to Plato)."""
from __future__ import annotations

from datetime import datetime

from booking.booking import BookingError, create_booking

DAY = "2026-07-15"          # a future Wednesday
NOW = datetime(2026, 7, 14, 9, 0)  # day before -> lead-time is a no-op

# physiotherapy -> dDIjWJp; Cheryl (blue) + Claire (6hpO), 09:00-17:00, no limits.
CFG = {"calendars": [{"id": "dDIjWJp", "rules": [
    {"name": "Cheryl Long", "book_calendar": "blue", "starttime": "09:00",
     "endtime": "17:00", "restricted_days": [], "restricted_blocks": []},
    {"name": "Claire Ng", "book_calendar": "6hpO", "starttime": "09:00",
     "endtime": "17:00", "restricted_days": [], "restricted_blocks": []},
]}]}

BASE = {"service": "physiotherapy", "date": DAY, "time": "10:00",
        "format": "clinic", "name": "Jane Tan", "phone": "+65 9123 4567",
        "email": "jane@example.com"}


class StubPlato:
    def __init__(self, appts=None, fail_on_create=None):
        self.appts = appts or []
        self.created: list[tuple[dict, str]] = []
        self.deleted: list[str] = []
        self._n = 0
        self.fail_on_create = fail_on_create

    def appointments(self, start, end):
        return self.appts

    def online_booking_config(self):
        return CFG

    def create_appointment(self, payload):
        self._n += 1
        if self.fail_on_create == self._n:
            raise RuntimeError("simulated plato failure")
        _id = f"id{self._n:03d}"
        self.created.append((payload, _id))
        return {"success": True, "_id": _id}

    def delete_appointment(self, _id):
        self.deleted.append(_id)
        return {"success": True}


def test_clinic_booking_success():
    p = StubPlato()
    res = create_booking(p, {**BASE, "clinician_id": "cheryl-long"}, now=NOW)
    assert res["ok"] and res["clinician_id"] == "cheryl-long"
    assert len(p.created) == 1
    payload = p.created[0][0]
    assert payload["color"] == "blue" and payload["code_Bottom"] == "hDWW"
    assert payload["connect"] is True
    assert payload["starttime"] == "2026-07-15 10:00:00"
    assert payload["endtime"] == "2026-07-15 11:00:00"
    assert res["reference"].startswith("GOJI-")
    # An explicit clinician pick is recorded by name in the result + flagged in
    # the Plato note so the clinic can reallocate.
    assert res["clinician_requested"] == "Cheryl Long"
    assert "Clinician: chosen by patient" in payload["description"]


def test_conflicting_slot_is_refused():
    p = StubPlato([{"color": "blue", "starttime": "2026-07-15 10:00:00",
                    "endtime": "2026-07-15 11:00:00"}])
    try:
        create_booking(p, {**BASE, "clinician_id": "cheryl-long"}, now=NOW)
        assert False, "expected BookingError"
    except BookingError as e:
        assert e.code == "slot_taken"
    assert p.created == []  # nothing written


def test_home_visit_creates_three_blocks():
    p = StubPlato()
    res = create_booking(p, {**BASE, "format": "home", "clinician_id": "claire-ng",
                             "address": "123B Lentor, S788887"}, now=NOW)
    # home forces Cheryl even though Claire was requested
    assert res["clinician_id"] == "cheryl-long" and res["home"] is True
    assert len(p.created) == 3
    titles = [c[0]["title"] for c in p.created]
    assert titles[0].startswith("Travel") and titles[2].startswith("Travel")
    assert titles[1] == "Jane Tan"  # visit title is just the name, no "(home visit)"
    visit = p.created[1][0]
    assert visit["code_Bottom"] == "sCla" and "123B Lentor" in visit["description"]
    assert p.created[0][0]["starttime"] == "2026-07-15 09:30:00"  # travel-before
    assert p.created[2][0]["endtime"] == "2026-07-15 11:30:00"    # travel-after


def test_home_visit_rolls_back_on_failure():
    p = StubPlato(fail_on_create=3)  # travel-after fails
    try:
        create_booking(p, {**BASE, "format": "home", "address": "123B Lentor"}, now=NOW)
        assert False, "expected failure"
    except BookingError:
        pass
    assert p.deleted == ["id001", "id002"]  # the two created were rolled back


def test_condition_notes_land_in_description():
    p = StubPlato()
    res = create_booking(p, {**BASE, "clinician_id": "cheryl-long",
                             "notes": "Right knee pain after running."}, now=NOW)
    assert res["ok"]
    assert "Condition: Right knee pain after running." in p.created[0][0]["description"]


def test_empty_notes_are_a_no_op():
    p = StubPlato()
    create_booking(p, {**BASE, "clinician_id": "cheryl-long", "notes": "   "}, now=NOW)
    assert "Condition:" not in p.created[0][0]["description"]


def test_physio_focus_is_written_to_note():
    # The physio sub-type is surfaced in the Plato note so the clinic sees what
    # the session is for.
    p = StubPlato()
    res = create_booking(p, {**BASE, "clinician_id": "cheryl-long",
                             "physio_focus": "womens-health"}, now=NOW)
    assert res["ok"]
    assert "Type: Women's Health" in p.created[0][0]["description"]


def test_no_physio_focus_means_no_type_line():
    p = StubPlato()
    create_booking(p, {**BASE, "clinician_id": "cheryl-long"}, now=NOW)
    assert "Type:" not in p.created[0][0]["description"]


def test_first_available_assigns_a_free_clinician():
    p = StubPlato()
    res = create_booking(p, {**BASE, "clinician_id": ""}, now=NOW)
    assert res["clinician_id"] in ("cheryl-long", "claire-ng")
    assert len(p.created) == 1
    # No explicit pick -> "First available" recorded in the result + flagged
    # earliest-available in the Plato note.
    assert res["clinician_requested"] == "First available"
    assert "Clinician: earliest available" in p.created[0][0]["description"]


def test_typo_email_is_refused():
    # A substitution (.con) and an adjacent swap (gmial) are both caught.
    for bad in ("jane@gmail.con", "jane@gmial.com"):
        p = StubPlato()
        try:
            create_booking(p, {**BASE, "clinician_id": "cheryl-long",
                               "email": bad}, now=NOW)
            assert False, f"expected BookingError for {bad}"
        except BookingError as e:
            assert e.code == "bad_email"
        assert p.created == []  # nothing written for a mistyped email


def test_unusual_but_valid_email_is_accepted():
    # A real, uncommon domain must not be mistaken for a typo.
    p = StubPlato()
    res = create_booking(p, {**BASE, "clinician_id": "cheryl-long",
                             "email": "jane@lentormodern.sg"}, now=NOW)
    assert res["ok"]


def test_booking_beyond_60_days_is_refused():
    # 61 days after NOW's date -> past the 60-day window.
    p = StubPlato()
    try:
        create_booking(p, {**BASE, "date": "2026-09-14",
                           "clinician_id": "cheryl-long"}, now=NOW)
        assert False, "expected BookingError"
    except BookingError as e:
        assert e.code == "too_far"
    assert p.created == []  # nothing written


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all passed")
