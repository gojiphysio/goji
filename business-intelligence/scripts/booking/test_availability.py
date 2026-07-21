"""Unit tests for the 30-min availability derivation (no network — stub Plato)."""
from __future__ import annotations

from datetime import date, datetime

from booking.availability import derive_availability


class StubPlato:
    def __init__(self, appts, cfg, broad=None):
        self._a, self._c = appts, cfg
        # Recurring masters + multi-day blocks the background sweep would return.
        self._broad = broad if broad is not None else []

    def appointments(self, start, end):
        return self._a

    def appointments_broad(self, start, end):
        return self._broad

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


def test_recurring_block_from_earlier_week_blocks_slots():
    # A weekly Wednesday 10:00-11:00 block whose series STARTED three weeks before
    # WED. Plato returns it only on its first date, so the single-day fetch is
    # empty — the background sweep overlay must still block 10:00 on WED.
    broad = [{"color": "blue", "title": "Block",
              "starttime": "2026-06-24 10:00:00", "endtime": "2026-06-24 11:00:00",
              "recur": '{"days": ["WE"], "freq": 2, "until": 20260805, "interval": 1}'}]
    out = derive_availability(StubPlato([], CFG, broad=broad), "physiotherapy",
                              WED, now=NOW)
    assert out["cheryl-long"] == ["09:00", "11:00"]


def test_biweekly_block_off_week_stays_open():
    # Kristy's real case in miniature: alternate-week block anchored 2026-07-01.
    # WED (07-15) is +2 weeks (ON) -> blocked; 07-08 is +1 week (OFF) -> open.
    broad = [{"color": "blue", "title": "Block",
              "starttime": "2026-07-01 10:00:00", "endtime": "2026-07-01 11:00:00",
              "recur": '{"days": ["WE"], "freq": 2, "until": 20260930, "interval": 2}'}]
    on_week = derive_availability(StubPlato([], CFG, broad=broad), "physiotherapy",
                                  WED, now=NOW)
    assert on_week["cheryl-long"] == ["09:00", "11:00"]
    off = date(2026, 7, 8)
    off_week = derive_availability(StubPlato([], CFG, broad=broad), "physiotherapy",
                                   off, now=datetime(2026, 7, 7, 9, 0))
    assert off_week["cheryl-long"] == ["09:00", "09:30", "10:00", "10:30", "11:00"]


def test_recurrence_excluded_or_past_until_does_not_block():
    for recur in (
        '{"days": ["WE"], "freq": 2, "until": 20260805, "interval": 1, "ex": [20260715]}',
        '{"days": ["WE"], "freq": 2, "until": 20260701, "interval": 1}',
    ):
        broad = [{"color": "blue", "title": "Block",
                  "starttime": "2026-06-10 10:00:00", "endtime": "2026-06-10 11:00:00",
                  "recur": recur}]
        out = derive_availability(StubPlato([], CFG, broad=broad), "physiotherapy",
                                  WED, now=NOW)
        assert out["cheryl-long"] == ["09:00", "09:30", "10:00", "10:30", "11:00"]


def test_multi_day_block_started_earlier_blocks_whole_day():
    # A non-recurring block spanning Mon-Fri that STARTED before WED; the single
    # -day fetch misses it (starttime is Monday), the sweep must block WED.
    broad = [{"color": "blue", "title": "Block", "recur": "null",
              "starttime": "2026-07-13 08:00:00", "endtime": "2026-07-17 20:00:00"}]
    out = derive_availability(StubPlato([], CFG, broad=broad), "physiotherapy",
                              WED, now=NOW)
    assert out.get("cheryl-long", []) == []


def test_clinic_wide_recurrence_blocks_everyone():
    # A recurring clinic-wide (-all-) meeting from an earlier week blocks every
    # rostered clinician on WED. 10:00-11:00 sits inside the 09:00-12:00 window.
    broad = [{"color": "-all-", "title": "Team Learning",
              "starttime": "2026-06-24 10:00:00", "endtime": "2026-06-24 11:00:00",
              "recur": '{"days": ["WE"], "freq": 2, "until": 20260930, "interval": 1}'}]
    out = derive_availability(StubPlato([], CFG_ALL, broad=broad), "physiotherapy",
                              WED, now=NOW)
    for cid in ("cheryl-long", "claire-ng", "kristy-ng"):
        assert out[cid] == ["09:00", "11:00"]


def test_broad_sweep_error_is_swallowed():
    # If the sweep source raises, availability must still return the per-day result
    # (best-effort overlay) rather than break.
    class Boom(StubPlato):
        def appointments_broad(self, start, end):
            raise RuntimeError("plato down")
    out = derive_availability(Boom([], CFG), "physiotherapy", WED, now=NOW)
    assert out["cheryl-long"] == ["09:00", "09:30", "10:00", "10:30", "11:00"]


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
