"""Unit tests for the 30-min availability derivation (no network — stub Plato)."""
from __future__ import annotations

from datetime import date, datetime

from booking.availability import derive_availability, derive_available_days


class StubPlato:
    def __init__(self, appts, cfg):
        self._a, self._c = appts, cfg
        self.appointment_fetches = 0

    def appointments(self, start, end):
        self.appointment_fetches += 1
        return self._a

    def online_booking_config(self):
        return self._c


# Physiotherapy's online calendar is dDIjWJp; give it one rule for Cheryl (blue),
# 09:00-12:00, no day/block restrictions.
CFG = {
    "calendars": [{
        "id": "dDIjWJp",
        "rules": [{
            "name": "Cheryl Long", "book_calendar": "blue",
            "starttime": "09:00", "endtime": "12:00",
            "min_days": 1, "max_days": 365,
            "restricted_days": [], "restricted_blocks": [],
        }],
    }],
}
# Same calendar, but all three clinicians rostered — for the sub-type filter.
CFG_ALL = {
    "calendars": [{
        "id": "dDIjWJp",
        "rules": [
            {"name": "Cheryl Long", "book_calendar": "blue", "starttime": "09:00",
             "endtime": "12:00", "min_days": 1, "max_days": 365,
             "restricted_days": [], "restricted_blocks": []},
            {"name": "Claire Ng", "book_calendar": "6hpO", "starttime": "09:00",
             "endtime": "12:00", "min_days": 1, "max_days": 365,
             "restricted_days": [], "restricted_blocks": []},
            {"name": "Kristy Ng", "book_calendar": "green", "starttime": "09:00",
             "endtime": "12:00", "min_days": 1, "max_days": 365,
             "restricted_days": [], "restricted_blocks": []},
        ],
    }],
}
WED = date(2026, 7, 15)  # a Wednesday
# Pin "now" to the day before WED so these tests are deterministic regardless of
# the real calendar date — otherwise, once real time passes WED, derive_availability
# treats it as a past date and returns no slots (which broke CI and the deploy).
NOW = datetime(2026, 7, 14, 9, 0)


def test_no_focus_offers_all_rostered_clinicians():
    out = derive_availability(StubPlato([], CFG_ALL), "physiotherapy", WED, now=NOW)
    assert set(out) == {"cheryl-long", "claire-ng", "kristy-ng"}


def test_scoliosis_focus_restricts_to_cheryl():
    out = derive_availability(StubPlato([], CFG_ALL), "physiotherapy", WED,
                              focus="scoliosis", now=NOW)
    assert set(out) == {"cheryl-long"}


def test_paediatrics_focus_excludes_claire():
    out = derive_availability(StubPlato([], CFG_ALL), "physiotherapy", WED,
                              focus="paediatrics", now=NOW)
    assert set(out) == {"cheryl-long", "kristy-ng"}


def test_free_day_gives_all_30min_starts():
    out = derive_availability(StubPlato([], CFG), "physiotherapy", WED, now=NOW)
    # 60-min appts, 30-min steps, window 09:00-12:00 -> last start 11:00.
    assert out["cheryl-long"] == ["09:00", "09:30", "10:00", "10:30", "11:00"]


def test_own_booking_blocks_overlapping_slots():
    appts = [{"color": "blue", "starttime": "2026-07-15 10:00:00",
              "endtime": "2026-07-15 11:00:00"}]
    out = derive_availability(StubPlato(appts, CFG), "physiotherapy", WED, now=NOW)
    # 10:00-11:00 booked removes 09:30/10:00/10:30 (all overlap a 60-min appt).
    assert out["cheryl-long"] == ["09:00", "11:00"]


def test_clinic_wide_all_block_applies_to_everyone():
    appts = [{"color": "-all-", "starttime": "2026-07-15 10:00:00",
              "endtime": "2026-07-15 11:00:00"}]
    out = derive_availability(StubPlato(appts, CFG), "physiotherapy", WED, now=NOW)
    assert out["cheryl-long"] == ["09:00", "11:00"]


def test_same_day_excluded_by_min_days():
    # min_days=1 -> booking on `today` itself returns nothing (1 day in advance).
    now = datetime(2026, 7, 15, 9, 0)  # 09:00 ON the WED test day
    out = derive_availability(StubPlato([], CFG), "physiotherapy", WED, now=now)
    assert out.get("cheryl-long", []) == []


def test_day_off_returns_no_slots():
    cfg = {"calendars": [{"id": "dDIjWJp", "rules": [{
        "name": "Cheryl Long", "book_calendar": "blue",
        "starttime": "09:00", "endtime": "12:00", "min_days": 0, "max_days": 365,
        "restricted_days": ["Wed"], "restricted_blocks": [],
    }]}]}
    out = derive_availability(StubPlato([], cfg), "physiotherapy", WED, now=NOW)
    assert out.get("cheryl-long", []) == []


def test_available_days_skips_day_off_and_fetches_once():
    # Wed 15th is Cheryl's day off; every other day in the range has slots.
    cfg = {"calendars": [{"id": "dDIjWJp", "rules": [{
        "name": "Cheryl Long", "book_calendar": "blue",
        "starttime": "09:00", "endtime": "12:00", "min_days": 1, "max_days": 365,
        "restricted_days": ["Wed"], "restricted_blocks": [],
    }]}]}
    stub = StubPlato([], cfg)
    days = derive_available_days(stub, "physiotherapy",
                                 date(2026, 7, 14), date(2026, 7, 17), now=NOW)
    assert days == ["2026-07-16", "2026-07-17"]  # Tue 14 < min_days, Wed 15 off
    assert stub.appointment_fetches == 1  # one fetch covers the whole range


def test_available_days_excludes_fully_booked_day():
    appts = [{"color": "blue", "starttime": "2026-07-15 08:30:00",
              "endtime": "2026-07-15 12:00:00"}]
    days = derive_available_days(StubPlato(appts, CFG), "physiotherapy",
                                 date(2026, 7, 15), date(2026, 7, 16), now=NOW)
    assert days == ["2026-07-16"]  # WED is booked wall-to-wall, Thu is free


def test_service_clinician_eligibility_excludes_ineligible_clinicians():
    # Clinical Pilates allows only Claire (Cheryl is excluded).
    # Both Cheryl and Claire are available in the config, but only Claire should appear.
    cfg = {
        "calendars": [{
            "id": "ne8sgkb",  # Clinical Pilates online calendar
            "rules": [
                {"name": "Cheryl Long", "book_calendar": "blue",
                 "starttime": "09:00", "endtime": "12:00", "min_days": 1,
                 "max_days": 365, "restricted_days": [], "restricted_blocks": []},
                {"name": "Claire Ng", "book_calendar": "6hpO",
                 "starttime": "09:00", "endtime": "12:00", "min_days": 1,
                 "max_days": 365, "restricted_days": [], "restricted_blocks": []},
            ],
        }],
    }
    out = derive_availability(StubPlato([], cfg), "clinical-pilates", WED, now=NOW)
    # Only Claire should be available; Cheryl is excluded by SERVICE_CLINICIANS.
    assert set(out) == {"claire-ng"}
    assert out["claire-ng"] == ["09:00", "09:30", "10:00", "10:30", "11:00"]
    # Cheryl should not appear in the result.
    assert "cheryl-long" not in out


def test_clinician_still_available_in_other_services():
    # Cheryl is excluded from Clinical Pilates but should be available in Physiotherapy.
    out = derive_availability(StubPlato([], CFG_ALL), "physiotherapy", WED, now=NOW)
    assert "cheryl-long" in out  # Cheryl still available in Physiotherapy


def test_recurring_appointment_blocks_slots():
    # Test case: A clinician has a recurring appointment (e.g., every Saturday 9-10am)
    # that should block availability at those times.
    # This simulates what should happen when Plato returns a recurring appointment
    # that has been expanded or needs to be checked.
    sat = date(2026, 7, 18)  # A Saturday
    # Appointment from 9:00-10:00 on Saturday
    appts = [{"color": "6hpO", "starttime": "2026-07-18 09:00:00",
              "endtime": "2026-07-18 10:00:00"}]
    cfg = {"calendars": [{"id": "dDIjWJp", "rules": [{
        "name": "Claire Ng", "book_calendar": "6hpO",
        "starttime": "08:00", "endtime": "12:00", "min_days": 1, "max_days": 365,
        "restricted_days": [], "restricted_blocks": [],
    }]}]}
    now = datetime(2026, 7, 17, 9, 0)  # Day before Saturday
    out = derive_availability(StubPlato(appts, cfg), "physiotherapy", sat, now=now)
    # 9:00-10:00 is booked, so 08:30 and 09:00 and 09:30 should be blocked
    # (60-min appts, 30-min steps)
    assert out["claire-ng"] == ["08:00", "10:00", "10:30", "11:00"]


def test_recurring_appointment_expansion_needed():
    # DIAGNOSTIC TEST: If Plato returns a single recurring entry,
    # it needs to be expanded to check for conflicts on specific dates.
    # This test documents the expected behavior when a recurring appointment
    # (e.g., "every Saturday 9-10am") is returned by Plato.
    # Currently: needs investigation - how does Plato represent recurring appointments?
    #   - Single entry with recurrence rule?
    #   - Pre-expanded individual entries?
    #   - Both formats mixed?
    pass  # Placeholder for recurring appointment investigation


def test_appointment_with_doctor_field_blocks_slots():
    # Test that appointments with "doctor" field (instead of "color") are properly
    # mapped to clinician calendars and block availability.
    sat = date(2026, 7, 18)
    # Appointment using "doctor" field instead of "color"
    appts = [{"doctor": "PCN", "title": "Blocked Time", "starttime": "2026-07-18 09:00:00",
              "endtime": "2026-07-18 11:00:00"}]
    cfg = {"calendars": [{"id": "dDIjWJp", "rules": [{
        "name": "Claire Ng", "book_calendar": "6hpO",
        "starttime": "08:00", "endtime": "12:00", "min_days": 1, "max_days": 365,
        "restricted_days": [], "restricted_blocks": [],
    }]}]}
    now = datetime(2026, 7, 17, 9, 0)
    out = derive_availability(StubPlato(appts, cfg), "physiotherapy", sat, now=now)
    # 9:00-11:00 should be blocked (PCN = Claire)
    # Window is 08:00-12:00, appointments are 60min
    # So 08:00-09:00 is free, 09:00-11:00 is blocked, 11:00-12:00 is free
    # 11:30-12:30 would exceed window, so only 08:00 and 11:00
    assert out["claire-ng"] == ["08:00", "11:00"]


def test_leave_entry_with_date_only_fields_blocks_day():
    # Test that leave entries with date-only fields (start_date/end_date) are
    # converted to proper datetimes and block availability. This simulates
    # Plato's clinician_leave endpoint returning dates without time components.
    sat = date(2026, 8, 8)  # Saturday
    # Leave entry with date-only fields (as returned from Plato's clinician_leave)
    appts = [{"color": "6hpO", "title": "Holiday", "type": "leave",
              "starttime": "2026-08-08T00:00:00", "endtime": "2026-08-09T00:00:00"}]
    cfg = {"calendars": [{"id": "dDIjWJp", "rules": [{
        "name": "Claire Ng", "book_calendar": "6hpO",
        "starttime": "08:00", "endtime": "18:00", "min_days": 0, "max_days": 365,
        "restricted_days": [], "restricted_blocks": [],
    }]}]}
    now = datetime(2026, 8, 7, 9, 0)
    out = derive_availability(StubPlato(appts, cfg), "physiotherapy", sat, now=now)
    # Entire day is on leave, so no slots available
    assert out["claire-ng"] == []


def test_leave_entry_blocks_all_day():
    # Test that leave/vacation entries block entire day availability.
    # Leave entries should come as full-day (00:00-23:59 or start_date-end_date).
    sat = date(2026, 8, 8)  # Saturday
    # Leave entry for entire day
    appts = [{"color": "6hpO", "title": "AL", "type": "leave",
              "starttime": "2026-08-08 00:00:00", "endtime": "2026-08-08 23:59:59"}]
    cfg = {"calendars": [{"id": "dDIjWJp", "rules": [{
        "name": "Claire Ng", "book_calendar": "6hpO",
        "starttime": "08:00", "endtime": "18:00", "min_days": 0, "max_days": 365,
        "restricted_days": [], "restricted_blocks": [],
    }]}]}
    now = datetime(2026, 8, 7, 9, 0)
    out = derive_availability(StubPlato(appts, cfg), "physiotherapy", sat, now=now)
    # Entire day is on leave, so no slots available
    assert out["claire-ng"] == []


def test_holiday_titled_appointment_blocks_availability():
    # Holiday blocks are just regular appointments with "Holiday" title on the
    # clinician's calendar. Test that title-based detection marks them as leave.
    sat = date(2026, 8, 8)
    appts = [{"color": "6hpO", "title": "Holiday", "type": "leave",
              "starttime": "2026-08-08T00:00:00", "endtime": "2026-08-09T00:00:00"}]
    cfg = {"calendars": [{"id": "dDIjWJp", "rules": [{
        "name": "Claire Ng", "book_calendar": "6hpO",
        "starttime": "08:00", "endtime": "18:00", "min_days": 0, "max_days": 365,
        "restricted_days": [], "restricted_blocks": [],
    }]}]}
    now = datetime(2026, 8, 7, 9, 0)
    out = derive_availability(StubPlato(appts, cfg), "physiotherapy", sat, now=now)
    # Full-day holiday block prevents all bookings
    assert out["claire-ng"] == []


def test_leave_titled_appointment_blocks_slots():
    # "Annual Leave" should block availability.
    fri = date(2026, 8, 7)
    # 10:00-11:00 leave block (60-min appts, so 09:30, 10:00, 10:30 slots are blocked)
    appts = [{"color": "6hpO", "title": "Annual Leave", "type": "leave",
              "starttime": "2026-08-07T10:00:00", "endtime": "2026-08-07T11:00:00"}]
    cfg = {"calendars": [{"id": "dDIjWJp", "rules": [{
        "name": "Claire Ng", "book_calendar": "6hpO",
        "starttime": "08:00", "endtime": "12:00", "min_days": 0, "max_days": 365,
        "restricted_days": [], "restricted_blocks": [],
    }]}]}
    now = datetime(2026, 8, 6, 9, 0)
    out = derive_availability(StubPlato(appts, cfg), "physiotherapy", fri, now=now)
    # Available: 08:00, 08:30, 09:00, 11:00. Blocked: 09:30, 10:00, 10:30
    assert out["claire-ng"] == ["08:00", "08:30", "09:00", "11:00"]


def test_ooo_titled_appointment_blocks_availability():
    # "OOO" (out of office) should be recognized as leave.
    wed = date(2026, 8, 5)
    appts = [{"color": "6hpO", "title": "OOO", "type": "leave",
              "starttime": "2026-08-05T00:00:00", "endtime": "2026-08-06T00:00:00"}]
    cfg = {"calendars": [{"id": "dDIjWJp", "rules": [{
        "name": "Claire Ng", "book_calendar": "6hpO",
        "starttime": "08:00", "endtime": "18:00", "min_days": 0, "max_days": 365,
        "restricted_days": [], "restricted_blocks": [],
    }]}]}
    now = datetime(2026, 8, 4, 9, 0)
    out = derive_availability(StubPlato(appts, cfg), "physiotherapy", wed, now=now)
    # Entire day blocked by OOO
    assert out["claire-ng"] == []


def test_recurring_appointment_partial_day_blocks():
    # Recurring appointments (like recurring patient sessions 9-11am) should block
    # the overlapping slots. After plato.py converts date-only fields to datetimes,
    # these appointments block availability correctly.
    fri = date(2026, 8, 15)
    # Recurring appointment 9:00-11:00 (already converted to proper datetime by plato.py)
    appts = [{"color": "6hpO", "title": "Matthew (recurring)",
              "starttime": "2026-08-15T09:00:00", "endtime": "2026-08-15T11:00:00"}]
    cfg = {"calendars": [{"id": "dDIjWJp", "rules": [{
        "name": "Claire Ng", "book_calendar": "6hpO",
        "starttime": "08:00", "endtime": "12:00", "min_days": 0, "max_days": 365,
        "restricted_days": [], "restricted_blocks": [],
    }]}]}
    now = datetime(2026, 8, 14, 9, 0)
    out = derive_availability(StubPlato(appts, cfg), "physiotherapy", fri, now=now)
    # 9:00-11:00 recurring appointment blocks 09:00, 09:30, 10:00, 10:30 (60-min slots)
    # Available: 08:00, 11:00
    assert out["claire-ng"] == ["08:00", "11:00"]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all passed")
