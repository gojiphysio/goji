"""
Expand Plato recurring-appointment rules onto a specific day.

Plato returns a recurring appointment as ONE row dated at its FIRST occurrence,
carrying a `recur` rule; it does NOT expand future instances in a date-range
`GET /appointment` query (proven against live data: a weekly series' master is
the only row — no per-week instance rows exist). So availability MUST expand the
rule itself. Otherwise a recurring block or appointment created weeks ago is
invisible on a future date and its slot is wrongly offered — the clinic hit this
with Kristy's alternate-Wednesday time-off (a biweekly calendar block).

`recur` is a JSON value on the appointment (a string like the ones below, or the
literal string "null" when the event doesn't repeat). Shape (iCal-ish):

  {"days": ["WE"], "freq": 2, "interval": 2, "until": 20260930, "ex": [20260722]}

- days:     weekday codes it repeats on (MO TU WE TH FR SA SU)
- freq:     2 = weekly (the only value the clinic uses today)
- interval: every N weeks (default 1; 2 = alternate weeks)
- until:    last date inclusive, YYYYMMDD int
- ex:       excluded dates, YYYYMMDD ints (skipped occurrences)

Only weekly cadence is modelled, matching 100% of the clinic's live recurrences.
A non-weekly rule (should one ever appear) still gets its weekday/`until`/`ex`
honoured; `interval` is treated as weeks. The bias throughout is to over-block
rather than under-block — a missed block means a double-booking.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

_WD = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


def parse_recur(value) -> dict | None:
    """Normalise Plato's `recur` field to a dict, or None when it doesn't repeat.
    Accepts a dict, a JSON string, or the literal "null"/empty."""
    if not value or value == "null":
        return None
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value)
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _ymd(n) -> date | None:
    """YYYYMMDD int (Plato's `until`/`ex` form) -> date, or None if unparseable."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        return None
    try:
        return date(n // 10000, (n // 100) % 100, n % 100)
    except ValueError:
        return None


def recurs_on(recur: dict, first_start: datetime, day: date) -> bool:
    """True if the rule anchored at `first_start` (the master's starttime) has an
    occurrence on `day`."""
    if not isinstance(recur, dict):
        return False
    start_date = first_start.date()
    if day < start_date:
        return False  # a recurrence can't precede its first occurrence

    until = _ymd(recur.get("until"))
    if until and day > until:
        return False

    if day in {_ymd(x) for x in (recur.get("ex") or [])}:
        return False  # an explicitly excluded occurrence

    wanted = {_WD[d] for d in (recur.get("days") or []) if d in _WD}
    if wanted:
        if day.weekday() not in wanted:
            return False
    elif day.weekday() != start_date.weekday():
        # No weekday list -> repeat on the anchor's own weekday.
        return False

    try:
        interval = int(recur.get("interval") or 1)
    except (TypeError, ValueError):
        interval = 1
    interval = max(interval, 1)

    # Weekly cadence: the whole-week gap between the anchor's week and `day`'s
    # week must be a multiple of `interval`. Anchor on each week's Monday so the
    # multiple is clean regardless of weekday.
    a_mon = start_date - timedelta(days=start_date.weekday())
    d_mon = day - timedelta(days=day.weekday())
    weeks = (d_mon - a_mon).days // 7
    return weeks >= 0 and weeks % interval == 0
