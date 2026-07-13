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
from zoneinfo import ZoneInfo

from .availability import derive_availability
from .config import (
    CLINICIANS,
    HOME_TRAVEL_MINUTES,
    HOME_VISIT_CLINICIAN,
    HOME_VISIT_TYPE_CODE,
    MAX_ADVANCE_DAYS,
    PHYSIO_FOCUS_LABELS,
    SERVICES,
)

_SGT = ZoneInfo("Asia/Singapore")

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^[+\d][\d\s()-]{6,}$")
_TIME_RE = re.compile(r"^\d{2}:\d{2}$")

# Common consumer webmail domains. A booking email like "gmail.con" passes the
# format check above but bounces, so the confirmation and the clinic's own copy
# never arrive. We flag an address whose domain is a single-edit miss of one of
# these (an insert, delete, substitution, or adjacent swap — so "gmail.con" and
# "gmial.com" are both caught). Kept deliberately short (big providers only) and
# to a distance of exactly 1 so a real but unusual domain is never mistaken for a
# typo; short/ambiguous names (me.com, qq.com) are left out because their
# single-edit neighbours include real domains. The website form has the same
# list (see BookingForm.astro); keep the two in sync.
_COMMON_EMAIL_DOMAINS = (
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.com.sg", "ymail.com",
    "hotmail.com", "hotmail.sg", "outlook.com", "outlook.sg", "live.com",
    "icloud.com", "singnet.com.sg",
)


def _osa_distance(a: str, b: str) -> int:
    """Optimal string alignment distance: Levenshtein plus adjacent transposition
    (so a single swapped pair of letters counts as one edit, not two)."""
    if a == b:
        return 0
    lb = len(b)
    prev2: list[int] = []
    prev = list(range(lb + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * lb
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        prev2, prev = prev, cur
    return prev[lb]


def email_typo_suggestion(email: str) -> str | None:
    """If `email`'s domain is a one-edit miss of a common webmail domain, return
    the corrected address (e.g. 'a@gmail.con' -> 'a@gmail.com'); else None."""
    at = email.rfind("@")
    if at < 0:
        return None
    local, domain = email[:at], email[at + 1:].lower()
    if not domain or domain in _COMMON_EMAIL_DOMAINS:
        return None
    for good in _COMMON_EMAIL_DOMAINS:
        if _osa_distance(domain, good) == 1:
            return f"{local}@{good}"
    return None

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

    today = (now or datetime.now(_SGT).replace(tzinfo=None)).date()
    _require(
        (day - today).days <= MAX_ADVANCE_DAYS,
        f"That date is too far ahead. Please choose a date within the next "
        f"{MAX_ADVANCE_DAYS} days.",
        "too_far",
    )

    name = (draft.get("name") or "").strip()
    phone = (draft.get("phone") or "").strip()
    email = (draft.get("email") or "").strip()
    _require(name, "Please enter your name.")
    _require(_PHONE_RE.match(phone), "Please enter a valid phone number.")
    _require(_EMAIL_RE.match(email), "Please enter a valid email.")
    # A well-formed but mistyped domain (gmail.con) would sail through the regex
    # and then bounce, so the confirmation never lands. Reject the obvious ones
    # with a corrective hint. (The website form catches these first; this guards
    # a stale/cached form or a direct API call.)
    suggestion = email_typo_suggestion(email)
    _require(
        not suggestion,
        f"That email looks like a typo — did you mean {suggestion}? "
        "Please correct it so we can send your confirmation.",
        "bad_email",
    )

    address = (draft.get("address") or "").strip()
    _require(not home or address, "Please add the home-visit address.")

    # Optional free-text the patient shares about their condition; capped so a
    # runaway paste can't bloat the Plato appointment note.
    notes = (draft.get("notes") or "").strip()[:1000]

    # Physiotherapy sub-type the patient chose (website's "What type of
    # physiotherapy?" step). Surfaced in the Plato note so the clinic sees what
    # the session is for. Only meaningful for physiotherapy.
    focus_label = (PHYSIO_FOCUS_LABELS.get((draft.get("physio_focus") or "").strip(), "")
                   if service_id == "physiotherapy" else "")

    # What the customer asked for on the form, for the confirmation email: an
    # explicit clinician by name, or "First available" when they let us match.
    # (Home visits are always Cheryl, but we still report what they selected.)
    requested_id = (draft.get("clinician_id") or "").strip()
    requested_name = (CLINICIANS[requested_id]["name"]
                      if requested_id in CLINICIANS else "First available")

    # Candidate clinicians: home = Cheryl only; explicit choice = that one; else
    # anyone offering the service who is free at the slot (availability decides).
    # `clinician_requested` records whether the patient explicitly picked the
    # clinician or we auto-assigned the earliest available one, so the clinic can
    # reallocate as part of clinical ops. (Home visits are Cheryl-only, so
    # there's no patient "choice" to honour there.)
    clinician_requested = False
    if home:
        candidates = [HOME_VISIT_CLINICIAN]
    elif draft.get("clinician_id"):
        _require(draft["clinician_id"] in CLINICIANS, "Unknown clinician.")
        candidates = [draft["clinician_id"]]
        clinician_requested = True
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
                plato, svc, cid, day, time_, home, name, phone, email, address,
                notes, clinician_requested, focus_label)
            return {
                "ok": True,
                "reference": "GOJI-" + visit_id[-6:].upper(),
                "appointment_ids": ids,
                "clinician_id": cid,
                "clinician_name": CLINICIANS[cid]["name"],
                "clinician_requested": requested_name,
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
                         address, notes="", clinician_requested=False,
                         focus_label="") -> tuple[list[str], str]:
    """Create the appointment(s). Returns (all_ids, visit_id). Rolls back on any
    failure so a partial home visit never lingers."""
    clin = CLINICIANS[cid]
    color, doctor, dur = clin["calendar"], clin["doctor"], svc["duration_min"]
    # Physiotherapy sub-type, so the clinic sees what the session is for (the
    # Plato type is the same for every physio booking).
    focus_line = f"\nType: {focus_label}" if focus_label else ""
    # Patient's condition note, appended to the visit description when present.
    note_line = f"\nCondition: {notes}" if notes else ""
    # Flag how the clinician was assigned so the clinic can reallocate. Home
    # visits are Cheryl-only, so the basis line only applies in-clinic.
    clin_line = ""
    if not home:
        clin_line = ("\nClinician: chosen by patient" if clinician_requested
                     else "\nClinician: earliest available")
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
                "title": name,
                "description": (f"HOME VISIT — {svc['title']}. Booked via website.\n"
                                f"Patient: {name} ({phone}).\nAddress: {address}"
                                f"{focus_line}{note_line}"),
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
                                f"{focus_line}{clin_line}{note_line}"),
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
