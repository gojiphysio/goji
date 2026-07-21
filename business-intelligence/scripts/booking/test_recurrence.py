"""Unit tests for the Plato recurrence-rule expansion (pure, no network)."""
from __future__ import annotations

from datetime import date, datetime

from booking.recurrence import parse_recur, recurs_on

# Anchor: Wednesday 2026-07-01 10:00. Weekly WED rule unless a test overrides.
ANCHOR = datetime(2026, 7, 1, 10, 0)


def _rule(**over):
    r = {"days": ["WE"], "freq": 2, "interval": 1, "until": 20260930}
    r.update(over)
    return r


def test_parse_recur_variants():
    assert parse_recur(None) is None
    assert parse_recur("null") is None
    assert parse_recur("") is None
    assert parse_recur('{"days": ["WE"], "interval": 1}') == {"days": ["WE"], "interval": 1}
    assert parse_recur({"days": ["WE"]}) == {"days": ["WE"]}
    assert parse_recur("not json") is None


def test_matches_same_weekday_future_week():
    assert recurs_on(_rule(), ANCHOR, date(2026, 7, 15))  # 2 weeks on


def test_before_anchor_is_false():
    assert not recurs_on(_rule(), ANCHOR, date(2026, 6, 24))


def test_wrong_weekday_is_false():
    assert not recurs_on(_rule(), ANCHOR, date(2026, 7, 16))  # a Thursday


def test_after_until_is_false():
    assert not recurs_on(_rule(until=20260708), ANCHOR, date(2026, 7, 15))


def test_until_is_inclusive():
    assert recurs_on(_rule(until=20260715), ANCHOR, date(2026, 7, 15))


def test_excluded_date_is_false():
    assert not recurs_on(_rule(ex=[20260715]), ANCHOR, date(2026, 7, 15))


def test_biweekly_on_and_off_weeks():
    r = _rule(interval=2)
    assert recurs_on(r, ANCHOR, date(2026, 7, 15))       # +2 weeks -> on
    assert not recurs_on(r, ANCHOR, date(2026, 7, 8))    # +1 week  -> off
    assert recurs_on(r, ANCHOR, date(2026, 7, 29))       # +4 weeks -> on


def test_multiple_weekdays():
    r = _rule(days=["MO", "WE"])
    assert recurs_on(r, ANCHOR, date(2026, 7, 15))       # Wed
    assert recurs_on(r, ANCHOR, date(2026, 7, 13))       # Mon (same week)


def test_no_days_falls_back_to_anchor_weekday():
    r = {"freq": 2, "interval": 1, "until": 20260930}    # no `days`
    assert recurs_on(r, ANCHOR, date(2026, 7, 15))       # Wed like the anchor
    assert not recurs_on(r, ANCHOR, date(2026, 7, 14))   # Tue


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all passed")
