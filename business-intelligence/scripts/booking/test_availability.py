"""Unit tests for the 30-min availability derivation (no network — stub Plato)."""
from __future__ import annotations

from datetime import date, datetime

from booking.availability import derive_availability


class StubPlato:
    def __init__(self, appts, cfg):
        self._a, self._c = appts, cfg

    def appointments(self, start, end):
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


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all passed")
