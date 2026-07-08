"""
create_booking — the safe write path into Plato.

Plato's POST /appointment does NOT reject conflicting bookings (proven live), so
every write is guarded: we re-derive availability for the exact slot INSIDE a
per-clinician lock, and only then create. Home visits create three appointments
(travel / visit / travel) atomically — any failure rolls back the rest.

This module does the Plato-side work only and returns a result dict; the Flask
app layers the admin email + funnel logging on top (keeps this unit-testable
with a stub Plato, no email/BigQuery deps).
"""
from __future__ import annotations

import re
import threading
from datetime import date, datetime, timedelta

from .availability import derive_availability
from .config import (
    CLINICIANS,
    HOME_TRAVEL_MINUTES,
    HOME_VISIT_CLINICIAN,
    HOME_VISIT_TYPE_CODE,
    SERVICES,
)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^[+\d][\d\s()-]{6,}$")
_TIME_RE = re.compile(r"^\d{2}:\d{2}$")

# One lock per clinician calendar, created lazily. Serialises the check->write so
# two concurrent requests can't both pass the availability check for one slot.
# (The booking service runs single-instance so these locks are authoritative.)
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(cid: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(cid, threading.Lock())


class BookingError(Exception):
    def __init__(self, message: str, code: str = "invalid"):
        super().__init__(message)
        self.code = code


def _require(cond, message: str, code: str = "invalid") -> None:
    if not cond:
        raise BookingError(message, code)


def _dt(day: date, hhmm: str, offset_min: int = 0) -> str:
    """Plato datetime string for `day` at `hhmm` (+/- offset), 'YYYY-MM-DD HH:MM:SS'."""
    h, m = (int(x) for x in hhmm.split(":"))
    t = datetime(day.year, day.month, day.day, h, m) + timedelta(minutes=offset_min)
    return t.strftime("%Y-%m-%d %H:%M:%S")


def create_booking(plato, draft: dict, *, now: datetime | None = None) -> dict:
    """Validate + create a booking. Raises BookingError on any problem.

    draft keys: service, date (YYYY-MM-DD), time (HH:MM), format ('clinic'|'home'),
    name, phone, email, clinician_id (optional; '' = first available), address
    (required for home).
    """
    service_id = (draft.get("service") or "").strip()
    svc = SERVICES.get(service_id)
    _require(svc, "Please choose a valid service.")

    home = (draft.get("format") or "clinic").strip() == "home"
    _require(not home or svc["supports_home"], "This service is in-clinic only.")

    try:
        day = date.fromisoformat((draft.get("date") or "").strip())
    except ValueError:
        raise BookingError("Please choose a valid date.")
    time_ = (draft.get("time") or "").strip()
    _require(_TIME_RE.match(time_), "Please choose a valid time.")

    name = (draft.get("name") or "").strip()
    phone = (draft.get("phone") or "").strip()
    email = (draft.get("email") or "").strip()
    _require(name, "Please enter your name.")
    _require(_PHONE_RE.match(phone), "Please enter a valid phone number.")
    _require(_EMAIL_RE.match(email), "Please enter a valid email.")

    address = (draft.get("address") or "").strip()
    _require(not home or address, "Please add the home-visit address.")

    # Optional free-text the patient shares about their condition; capped so a
    # runaway paste can't bloat the Plato appointment note.
    notes = (draft.get("notes") or "").strip()[:1000]

    # Candidate clinicians: home = Cheryl only; explicit choice = that one; else
    # anyone offering the service who is free at the slot (availability decides).
    if home:
        candidates = [HOME_VISIT_CLINICIAN]
    elif draft.get("clinician_id"):
        _require(draft["clinician_id"] in CLINICIANS, "Unknown clinician.")
        candidates = [draft["clinician_id"]]
    else:
        avail = derive_availability(plato, service_id, day, home=home, now=now)
        candidates = [cid for cid, slots in avail.items() if time_ in slots]
        _require(candidates, "That time is no longer available.", "slot_taken")

    last_err: BookingError | None = None
    for cid in candidates:
        with _lock_for(cid):
            avail = derive_availability(plato, service_id, day,
                                       clinician_id=cid, home=home, now=now)
            if time_ not in avail.get(cid, []):
                last_err = BookingError("That time is no longer available.", "slot_taken")
                continue
            ids, visit_id = _create_appointments(
                plato, svc, cid, day, time_, home, name, phone, email, address, notes)
            return {
                "ok": True,
                "reference": "GOJI-" + visit_id[-6:].upper(),
                "appointment_ids": ids,
                "clinician_id": cid,
                "clinician_name": CLINICIANS[cid]["name"],
                "service": svc["title"],
                "date": day.isoformat(),
                "time": time_,
                "home": home,
            }
    raise last_err or BookingError("That time is no longer available.", "slot_taken")


def _post(plato, payload: dict) -> str:
    r = plato.create_appointment(payload) or {}
    _id = r.get("_id")
    if not r.get("success") or not _id:
        raise BookingError("Plato did not accept the appointment.", "plato_error")
    return _id


def _create_appointments(plato, svc, cid, day, time_, home, name, phone, email,
                         address, notes="") -> tuple[list[str], str]:
    """Create the appointment(s). Returns (all_ids, visit_id). Rolls back on any
    failure so a partial home visit never lingers."""
    clin = CLINICIANS[cid]
    color, doctor, dur = clin["calendar"], clin["doctor"], svc["duration_min"]
    # Patient's condition note, appended to the visit description when present.
    note_line = f"\nCondition: {notes}" if notes else ""
    created: list[str] = []
    try:
        if home:
            created.append(_post(plato, {
                "title": "Travel (home visit)",
                "description": f"Travel to home visit — {svc['title']}",
                "starttime": _dt(day, time_, -HOME_TRAVEL_MINUTES),
                "endtime": _dt(day, time_),
                "color": color, "doctor": doctor,
            }))
            visit_id = _post(plato, {
                "title": f"{name} (home visit)",
                "description": (f"HOME VISIT — {svc['title']}. Booked via website.\n"
                                f"Patient: {name} ({phone}).\nAddress: {address}"
                                f"{note_line}"),
                "starttime": _dt(day, time_),
                "endtime": _dt(day, time_, dur),
                "color": color, "doctor": doctor,
                "code_Bottom": HOME_VISIT_TYPE_CODE,
                "email": email, "handphone": phone, "connect": True,
            })
            created.append(visit_id)
            created.append(_post(plato, {
                "title": "Travel (home visit)",
                "description": f"Travel from home visit — {svc['title']}",
                "starttime": _dt(day, time_, dur),
                "endtime": _dt(day, time_, dur + HOME_TRAVEL_MINUTES),
                "color": color, "doctor": doctor,
            }))
        else:
            visit_id = _post(plato, {
                "title": name,
                "description": (f"{svc['title']}. Booked via website.\n"
                                f"Patient: {name} ({phone})."
                                f"{note_line}"),
                "starttime": _dt(day, time_),
                "endtime": _dt(day, time_, dur),
                "color": color, "doctor": doctor,
                "code_Bottom": svc["type_code"],
                "email": email, "handphone": phone, "connect": True,
            })
            created.append(visit_id)
        return created, visit_id
    except Exception:
        # Roll back any blocks already created so a partial home visit never lingers.
        for _id in created:
            try:
                plato.delete_appointment(_id)
            except Exception:
                pass
        raise BookingError(
            "Could not complete the booking. Please try again or message us.",
            "plato_error",
        )
