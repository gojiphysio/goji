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

DIAGNOSTIC_LOGGING: set environment variable BOOKING_AVAILABILITY_DEBUG=1 to enable
detailed per-slot logging (clinician, service, date, rule, candidate slots, exclusions,
final slots). Used to diagnose recurring entry issues.
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .config import (
    CLINICIANS,
    HOME_TRAVEL_MINUTES,
    HOME_VISIT_CLINICIAN,
    MAX_ADVANCE_DAYS,
    PHYSIO_FOCUS_CLINICIANS,
    SERVICE_CLINICIANS,
    SERVICES,
    SLOT_MINUTES,
    clinician_by_calendar,
)

SGT = ZoneInfo("Asia/Singapore")
_DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]  # python weekday() order

log = logging.getLogger("booking.availability")
_DIAG = os.environ.get("BOOKING_AVAILABILITY_DEBUG", "").lower() in ("1", "true", "yes")


def _rules_for(cfg: dict, online_calendar_id: str) -> list[dict]:
    for c in cfg.get("calendars", []):
        if c.get("id") == online_calendar_id:
            return c.get("rules", []) or []
    return []


def _overlaps(a_start: datetime, a_end: datetime,
              b_start: datetime, b_end: datetime) -> bool:
    return a_start < b_end and a_end > b_start


def _booked_by_calendar(appointments: list[dict]) -> dict[str, list[tuple[datetime, datetime]]]:
    """Group appointment (start, end) ranges by calendar `color`. `-all-` entries
    (e.g. a clinic-wide meeting) block every clinician."""
    booked: dict[str, list[tuple[datetime, datetime]]] = {}
    for a in appointments:
        try:
            s = datetime.fromisoformat(a["starttime"])
            e = datetime.fromisoformat(a["endtime"])
        except (KeyError, ValueError, TypeError):
            continue
        booked.setdefault(a.get("color", ""), []).append((s, e))
    return booked


def derive_availability(
    plato,
    service_id: str,
    day: date,
    *,
    clinician_id: str | None = None,
    focus: str | None = None,
    home: bool = False,
    now: datetime | None = None,
) -> dict[str, list[str]]:
    """Return {clinician_id: ["HH:MM", ...]} of free 30-min starts for `day`.

    `clinician_id` restricts to one clinician; `focus` (a physiotherapy sub-type)
    restricts to the clinicians who offer it (e.g. scoliosis -> Cheryl only);
    `home` restricts to the home-visit clinician and pads each slot with travel
    time on both sides. `now` (naive SGT) is injectable for testing; defaults to
    the current SGT time.
    """
    booked = _booked_by_calendar(plato.appointments(day.isoformat(), day.isoformat()))
    cfg = plato.online_booking_config()
    return _derive_day(cfg, booked, service_id, day, clinician_id=clinician_id,
                       focus=focus, home=home, now=now)


def derive_available_days(
    plato,
    service_id: str,
    start: date,
    end: date,
    *,
    clinician_id: str | None = None,
    focus: str | None = None,
    home: bool = False,
    now: datetime | None = None,
) -> list[str]:
    """Return the sorted ISO dates in [start, end] with at least one free slot.

    Powers the website calendar's availability shading (and its first-free-date
    pick), so a visitor never has to click through empty dates. One appointments
    fetch covers the whole range — per-day fetches would blow Plato's 20 req/min
    budget for a single month view.
    """
    booked = _booked_by_calendar(
        plato.appointments(start.isoformat(), end.isoformat()))
    cfg = plato.online_booking_config()
    out: list[str] = []
    day = start
    while day <= end:
        avail = _derive_day(cfg, booked, service_id, day,
                            clinician_id=clinician_id, focus=focus, home=home,
                            now=now)
        if any(avail.values()):
            out.append(day.isoformat())
        day += timedelta(days=1)
    return out


def _derive_day(
    cfg: dict,
    booked: dict[str, list[tuple[datetime, datetime]]],
    service_id: str,
    day: date,
    *,
    clinician_id: str | None = None,
    focus: str | None = None,
    home: bool = False,
    now: datetime | None = None,
) -> dict[str, list[str]]:
    """The per-day core of derive_availability, on pre-fetched Plato data.

    `booked` may span more days than `day` (the range derivation fetches a whole
    month at once) — overlap checks only ever match same-day times.
    """
    svc = SERVICES.get(service_id)
    if not svc:
        raise ValueError(f"unknown service {service_id!r}")
    if home and not svc["supports_home"]:
        return {}

    # A physiotherapy sub-type opens only its clinicians' calendars. Ignored for
    # non-physio services and unknown sub-types (treated as "no restriction").
    focus_allowed = (PHYSIO_FOCUS_CLINICIANS.get(focus or "")
                     if service_id == "physiotherapy" else None)

    # Service-specific clinician roster: if defined, only these clinicians can
    # provide this service (e.g. Cheryl removed from Clinical Pilates).
    service_clinicians = SERVICE_CLINICIANS.get(service_id)

    dur = timedelta(minutes=svc["duration_min"])
    pad = timedelta(minutes=HOME_TRAVEL_MINUTES if home else 0)
    step = timedelta(minutes=SLOT_MINUTES)
    dow = _DOW[day.weekday()]
    _now = now if now is not None else datetime.now(SGT).replace(tzinfo=None)
    today = _now.date()

    def at(hhmm: str) -> datetime:
        h, m = (int(x) for x in hhmm.split(":"))
        return datetime(day.year, day.month, day.day, h, m)

    # Clinic-wide `-all-` blocks apply on top of each clinician's own bookings.
    clinic_wide = booked.get("-all-", [])

    out: dict[str, list[str]] = {}

    for rule in _rules_for(cfg, svc["online_calendar"]):
        color = rule.get("book_calendar")
        cid = clinician_by_calendar(color or "")
        if not cid:
            continue

        # Early exclusion checks
        if home and cid != HOME_VISIT_CLINICIAN:
            continue
        if clinician_id and cid != clinician_id:
            continue
        if focus_allowed is not None and cid not in focus_allowed:
            continue
        if service_clinicians is not None and cid not in service_clinicians:
            continue
        if dow in (rule.get("restricted_days") or []):
            if _DIAG:
                log.info(f"  {cid}: day-off ({dow})")
            continue

        # Booking must be at least `min_days` ahead (Plato's rule; 1 = no same-day)
        # and within `max_days`.
        delta = (day - today).days
        if delta < (rule.get("min_days") or 0):
            if _DIAG:
                log.info(f"  {cid}: outside min_days window (delta={delta}, min={rule.get('min_days', 0)})")
            continue
        if delta > min(rule.get("max_days") or 365, MAX_ADVANCE_DAYS):
            if _DIAG:
                log.info(f"  {cid}: outside max_days window (delta={delta}, max={min(rule.get('max_days', 365), MAX_ADVANCE_DAYS)})")
            continue

        if _DIAG:
            log.info(f"== {service_id} / {day} ({dow}) / {cid} ==")
            log.info(f"  rule: {rule.get('name')} (calendar={color})")
            start_h = rule.get('starttime', '08:00')
            end_h = rule.get('endtime', '18:00')
            log.info(f"  rule hours: {start_h}-{end_h}")

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

        if _DIAG:
            win_start_str = win_start.strftime('%H:%M')
            win_end_str = win_end.strftime('%H:%M')
            log.info(f"  final window: {win_start_str}-{win_end_str} (after online_start/end override)")
            if blocks:
                blocks_str = [f"{s.strftime('%H:%M')}-{e.strftime('%H:%M')}" for s, e in blocks]
                log.info(f"  restricted blocks: {blocks_str}")
            log.info(f"  taken slots ({color}): {len(taken)} appointments")
            if taken:
                taken_str = [f"{s.strftime('%H:%M:%S')}-{e.strftime('%H:%M:%S')}" for s, e in taken[:5]]
                log.info(f"    {taken_str}")

        slots: list[str] = []
        t = win_start
        while t + dur <= win_end:
            occ_start, occ_end = t - pad, t + dur + pad
            free = occ_start >= win_start  # travel-before must fit the working day
            exclusion = None
            if free and day == today and t <= _now:
                free = False  # no past slots (same-day is also gated by min_days)
                exclusion = "past"
            if free and any(_overlaps(occ_start, occ_end, bs, be) for bs, be in blocks):
                free = False
                exclusion = "restricted_block"
            if free and any(_overlaps(occ_start, occ_end, bs, be) for bs, be in taken):
                free = False
                exclusion = "booked"
            if free:
                slots.append(t.strftime("%H:%M"))
            elif _DIAG and False:  # set to True to log every excluded slot (verbose)
                log.debug(f"    {t.strftime('%H:%M')} excluded: {exclusion}")
            t += step

        if _DIAG:
            slots_str = ', '.join(slots[:10]) if slots else '(none)'
            ellipsis = '...' if len(slots) > 10 else ''
            log.info(f"  final slots: {len(slots)} ({slots_str}{ellipsis})")

        out[cid] = slots

    if _DIAG:
        log.info(f"AVAILABILITY SUMMARY: service={service_id} date={day} found {sum(len(s) for s in out.values())} total slots across {len(out)} clinicians")

    return out
