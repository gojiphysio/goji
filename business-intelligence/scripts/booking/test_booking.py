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
    # the session is for. Use Claire (not Cheryl, who is blocked from Women's Health).
    p = StubPlato()
    res = create_booking(p, {**BASE, "clinician_id": "claire-ng",
                             "physio_focus": "womens-health"}, now=NOW)
    assert res["ok"]
    assert "Type: Women's Health" in p.created[0][0]["description"]


def test_no_physio_focus_means_no_type_line():
    p = StubPlato()
    create_booking(p, {**BASE, "clinician_id": "cheryl-long"}, now=NOW)
    assert "Type:" not in p.created[0][0]["description"]


def test_result_carries_focus_label_and_clinician_email():
    # The result feeds the booking emails: the physio sub-type label is surfaced
    # there, and the matched clinician's inbox is used to CC them.
    p = StubPlato()
    res = create_booking(p, {**BASE, "clinician_id": "cheryl-long",
                             "physio_focus": "general"}, now=NOW)
    assert res["physio_focus"] == "General Musculoskeletal (MSK)"
    assert res["clinician_email"] == "cheryl.long@gojiphysio.com"


def test_result_focus_label_empty_without_focus():
    p = StubPlato()
    res = create_booking(p, {**BASE, "clinician_id": "cheryl-long"}, now=NOW)
    assert res["physio_focus"] == ""


def test_first_available_respects_physio_focus():
    # Scoliosis is Cheryl-only, so first-available must never assign Claire.
    p = StubPlato()
    res = create_booking(p, {**BASE, "clinician_id": "", "physio_focus": "scoliosis"}, now=NOW)
    assert res["clinician_id"] == "cheryl-long"


def test_focus_refuses_a_clinician_who_does_not_offer_it():
    # A direct pick of Claire for a scoliosis session is refused (the website
    # never offers it, but a raw API call could).
    p = StubPlato()
    try:
        create_booking(p, {**BASE, "clinician_id": "claire-ng",
                           "physio_focus": "scoliosis"}, now=NOW)
        assert False, "expected BookingError"
    except BookingError:
        pass
    assert p.created == []  # nothing written


def test_first_available_assigns_a_free_clinician():
    p = StubPlato()
    res = create_booking(p, {**BASE, "clinician_id": ""}, now=NOW)
    # Both Claire and Cheryl are free at 10:00, so the priority order
    # (Kristy -> Claire -> Cheryl) picks Claire over Cheryl.
    assert res["clinician_id"] == "claire-ng"
    assert len(p.created) == 1
    # No explicit pick -> "First available" recorded in the result + flagged
    # earliest-available in the Plato note.
    assert res["clinician_requested"] == "First available"
    assert "Clinician: earliest available" in p.created[0][0]["description"]


def test_first_available_falls_back_to_cheryl_when_claire_is_busy():
    # Claire (6hpO) is booked at 10:00; with Kristy absent from this calendar,
    # first-available must fall back to Cheryl rather than refuse the slot.
    p = StubPlato([{"color": "6hpO", "starttime": "2026-07-15 10:00:00",
                    "endtime": "2026-07-15 11:00:00"}])
    res = create_booking(p, {**BASE, "clinician_id": ""}, now=NOW)
    assert res["clinician_id"] == "cheryl-long"


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


def test_booking_clinician_ineligible_for_service():
    # Cheryl is excluded from Clinical Pilates by SERVICE_CLINICIANS config.
    # Attempting to book her for that service should fail.
    p = StubPlato()
    try:
        create_booking(p, {"service": "clinical-pilates", "date": DAY,
                           "time": "10:00", "format": "clinic",
                           "name": "Jane Tan", "phone": "+65 9123 4567",
                           "email": "jane@example.com",
                           "clinician_id": "cheryl-long"}, now=NOW)
        assert False, "expected BookingError"
    except BookingError:
        pass
    assert p.created == []  # nothing written


def test_first_available_respects_service_clinician_eligibility():
    # Clinical Pilates is restricted to Claire by SERVICE_CLINICIANS.
    # "First available" for Clinical Pilates should assign Claire, never Cheryl.
    # Config for Clinical Pilates with both Cheryl and Claire.
    cfg_pilates = {
        "calendars": [{
            "id": "ne8sgkb",
            "rules": [
                {"name": "Cheryl Long", "book_calendar": "blue", "starttime": "09:00",
                 "endtime": "17:00", "restricted_days": [], "restricted_blocks": []},
                {"name": "Claire Ng", "book_calendar": "6hpO", "starttime": "09:00",
                 "endtime": "17:00", "restricted_days": [], "restricted_blocks": []},
            ],
        }],
    }

    class StubPlatoCP(StubPlato):
        def online_booking_config(self):
            return cfg_pilates

    p = StubPlatoCP()
    res = create_booking(p, {"service": "clinical-pilates", "date": DAY,
                             "time": "10:00", "format": "clinic",
                             "name": "Jane Tan", "phone": "+65 9123 4567",
                             "email": "jane@example.com",
                             "clinician_id": ""}, now=NOW)
    # Should be assigned to Claire, not Cheryl (even though Cheryl might be free).
    assert res["clinician_id"] == "claire-ng"


def test_30min_paediatric_variant_duration():
    # Paediatric physiotherapy with 30-min variant should create a 30-min slot.
    p = StubPlato()
    res = create_booking(p, {**BASE, "clinician_id": "cheryl-long",
                             "physio_focus": "paediatrics", "variant": "30min"}, now=NOW)
    assert res["ok"]
    payload = p.created[0][0]
    assert payload["starttime"] == "2026-07-15 10:00:00"
    assert payload["endtime"] == "2026-07-15 10:30:00"  # 30 mins later


def test_55min_paediatric_variant_duration():
    # Paediatric physiotherapy with 55-min variant should create a 55-min slot.
    p = StubPlato()
    res = create_booking(p, {**BASE, "clinician_id": "cheryl-long",
                             "physio_focus": "paediatrics", "variant": "55min"}, now=NOW)
    assert res["ok"]
    payload = p.created[0][0]
    assert payload["starttime"] == "2026-07-15 10:00:00"
    assert payload["endtime"] == "2026-07-15 10:55:00"  # 55 mins later


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all passed")


def test_private_pilates_books_camille_with_private_pilates_type(monkeypatch):
    # Stand-in online calendar id (the real one does not exist in Plato yet).
    from booking.config import SERVICES
    monkeypatch.setitem(SERVICES["private-pilates"], "online_calendar", "PRIV")
    cfg = {"calendars": [{"id": "PRIV", "rules": [
        {"name": "Camille Tan", "book_calendar": "pF9S", "starttime": "09:00",
         "endtime": "17:00", "restricted_days": [], "restricted_blocks": []},
    ]}]}

    class StubPlatoPP(StubPlato):
        def online_booking_config(self):
            return cfg

    p = StubPlatoPP()
    res = create_booking(p, {"service": "private-pilates", "date": DAY,
                             "time": "10:00", "format": "clinic",
                             "name": "Jane Tan", "phone": "+65 9123 4567",
                             "email": "jane@example.com",
                             "clinician_id": ""}, now=NOW)
    assert res["ok"] and res["clinician_id"] == "camille-tan"
    payload = p.created[0][0]
    assert payload["color"] == "pF9S" and payload["doctor"] == "ICT"
    assert payload["code_Bottom"] == "N1z9"
    assert "Private Pilates" in payload["description"]


def test_booking_physio_cannot_be_chosen_for_private_pilates():
    p = StubPlato()
    try:
        create_booking(p, {"service": "private-pilates", "date": DAY,
                           "time": "10:00", "format": "clinic",
                           "name": "Jane Tan", "phone": "+65 9123 4567",
                           "email": "jane@example.com",
                           "clinician_id": "claire-ng"}, now=NOW)
        assert False, "expected BookingError"
    except BookingError:
        pass
    assert p.created == []
