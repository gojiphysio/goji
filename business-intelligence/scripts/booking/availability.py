"""
30-minute availability derivation.

We do NOT use Plato's `onlineapptbooking/slots` (it's locked to a 60-min
interval). Instead we read each clinician's rules from `onlineapptbooking/list`
(working hours, days off, restricted blocks, min/max booking window) and subtract
their real booked appointments (`GET /appointment`), stepping in 30-min slots.

A slot at time T is offered iff [T, T+duration] is inside the clinician's window,
outside every restricted block, and free of any existing appointment on that
clinician's calendar. For home visits, the free interval is widened by the travel
padding on both sides, and only Cheryl is considered.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .config import (
    CLINICIANS,
    HOME_TRAVEL_MINUTES,
    HOME_VISIT_CLINICIAN,
    SERVICES,
    SLOT_MINUTES,
    clinician_by_calendar,
)

SGT = ZoneInfo("Asia/Singapore")
_DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]  # python weekday() order


def _rules_for(cfg: dict, online_calendar_id: str) -> list[dict]:
    for c in cfg.get("calendars", []):
        if c.get("id") == online_calendar_id:
            return c.get("rules", []) or []
    return []


def _overlaps(a_start: datetime, a_end: datetime,
              b_start: datetime, b_end: datetime) -> bool:
    return a_start < b_end and a_end > b_start


def derive_availability(
    plato,
    service_id: str,
    day: date,
    *,
    clinician_id: str | None = None,
    home: bool = False,
    now: datetime | None = None,
) -> dict[str, list[str]]:
    """Return {clinician_id: ["HH:MM", ...]} of free 30-min starts for `day`.

    `clinician_id` restricts to one clinician; `home` restricts to the home-visit
    clinician and pads each slot with travel time on both sides. `now` (naive SGT)
    is injectable for testing; defaults to the current SGT time.
    """
    svc = SERVICES.get(service_id)
    if not svc:
        raise ValueError(f"unknown service {service_id!r}")
    if home and not svc["supports_home"]:
        return {}

    dur = timedelta(minutes=svc["duration_min"])
    pad = timedelta(minutes=HOME_TRAVEL_MINUTES if home else 0)
    step = timedelta(minutes=SLOT_MINUTES)
    dow = _DOW[day.weekday()]
    _now = now if now is not None else datetime.now(SGT).replace(tzinfo=None)
    today = _now.date()

    def at(hhmm: str) -> datetime:
        h, m = (int(x) for x in hhmm.split(":"))
        return datetime(day.year, day.month, day.day, h, m)

    # Booked ranges per calendar `color`, from the day's real appointments.
    # `-all-` entries (e.g. a clinic-wide "Clinical Meeting") block EVERY
    # clinician and are applied on top of each clinician's own bookings.
    booked: dict[str, list[tuple[datetime, datetime]]] = {}
    for a in plato.appointments(day.isoformat(), day.isoformat()):
        try:
            s = datetime.fromisoformat(a["starttime"])
            e = datetime.fromisoformat(a["endtime"])
        except (KeyError, ValueError, TypeError):
            continue
        booked.setdefault(a.get("color", ""), []).append((s, e))
    clinic_wide = booked.get("-all-", [])

    cfg = plato.online_booking_config()
    out: dict[str, list[str]] = {}

    for rule in _rules_for(cfg, svc["online_calendar"]):
        color = rule.get("book_calendar")
        cid = clinician_by_calendar(color or "")
        if not cid:
            continue
        if home and cid != HOME_VISIT_CLINICIAN:
            continue
        if clinician_id and cid != clinician_id:
            continue
        if dow in (rule.get("restricted_days") or []):
            continue

        # Booking must be at least `min_days` ahead (Plato's rule; 1 = no same-day)
        # and within `max_days`.
        delta = (day - today).days
        if delta < (rule.get("min_days") or 0):
            continue
        if delta > (rule.get("max_days") or 365):
            continue

        # Window = the clinician's rule hours, clamped by any online-hours
        # override (e.g. Cheryl's online bookings don't start until 09:00).
        meta = CLINICIANS[cid]
        win_start = max(at(rule.get("starttime", "08:00")),
                        at(meta["online_start"]) if meta.get("online_start") else at("00:00"))
        win_end = min(at(rule.get("endtime", "18:00")),
                      at(meta["online_end"]) if meta.get("online_end") else at("23:59"))
        blocks = [
            (at(b["starttime"]), at(b["endtime"]))
            for b in (rule.get("restricted_blocks") or [])
            if b.get("day") == dow
        ]
        taken = booked.get(color, []) + clinic_wide

        slots: list[str] = []
        t = win_start
        while t + dur <= win_end:
            occ_start, occ_end = t - pad, t + dur + pad
            free = occ_start >= win_start  # travel-before must fit the working day
            if free and day == today and t <= _now:
                free = False  # no past slots (same-day is also gated by min_days)
            if free and any(_overlaps(occ_start, occ_end, bs, be) for bs, be in blocks):
                free = False
            if free and any(_overlaps(occ_start, occ_end, bs, be) for bs, be in taken):
                free = False
            if free:
                slots.append(t.strftime("%H:%M"))
            t += step
        out[cid] = slots

    return out
