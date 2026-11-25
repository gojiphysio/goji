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
import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .availability import _calendar_color_for_appointment, derive_availability
from .config import (
    CLINICIANS,
    FIRST_AVAILABLE_PRIORITY,
    HOME_TRAVEL_MINUTES,
    HOME_VISIT_CLINICIAN,
    HOME_VISIT_TYPE_CODE,
    MAX_ADVANCE_DAYS,
    PHYSIO_FOCUS_CLINICIANS,
    SAME_DAY_BOOK_LEAD_MINUTES,
    PHYSIO_FOCUS_LABELS,
    SERVICE_CLINICIANS,
    SERVICES,
    clinician_by_calendar,
)
from .plato import _is_leave_title

_SGT = ZoneInfo("Asia/Singapore")

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^[+\d][\d\s()-]{6,}$")
_TIME_RE = re.compile(r"^\d{2}:\d{2}$")
# Markup in a name or note is never a real patient: it is a scanner probing for
# HTML/script injection (2026-11-12: "<img onerror>" names, "<script>" notes).
# Names refuse any angle bracket; notes/address refuse only tag-like text, so
# "pain < 3 weeks" still books.
_TAG_RE = re.compile(r"<\s*[A-Za-z/!?]")

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


# Where a booking came from, as written into the Plato note.
BOOKED_VIA = {"web": "website", "whatsapp": "WhatsApp assistant"}


def create_booking(plato, draft: dict, *, now: datetime | None = None,
                   email_required: bool = True, dry_run: bool = False,
                   source: str = "web", patient_id: str = "",
                   create_patient: bool = False) -> dict:
    """Validate + create a booking. Raises BookingError on any problem.

    draft keys: service, date (YYYY-MM-DD), time (HH:MM), format ('clinic'|'home'),
    name, phone, email, clinician_id (optional; '' = first available), address
    (required for home).

    email_required=False lets a booking through with no email (WhatsApp: the
    assistant confirms in the chat). An email that IS given is still validated.
    With no email, Plato gets no address and `connect` is False (no portal
    invite to send). dry_run=True runs every check, including the locked fresh
    re-check that picks the clinician, and returns the same result shape with a
    DRYRUN- reference, but never writes to Plato.
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
    _require("<" not in name and ">" not in name,
             "Please enter your name without < or > characters.")
    _require(_PHONE_RE.match(phone), "Please enter a valid phone number.")
    _require(email or not email_required, "Please enter a valid email.")
    _require(not email or _EMAIL_RE.match(email), "Please enter a valid email.")
    # A well-formed but mistyped domain (gmail.con) would sail through the regex
    # and then bounce, so the confirmation never lands. Reject the obvious ones
    # with a corrective hint. (The website form catches these first; this guards
    # a stale/cached form or a direct API call.)
    suggestion = email_typo_suggestion(email) if email else None
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
    _require(not _TAG_RE.search(notes) and not _TAG_RE.search(address),
             "Please remove the < and > characters from your note.")

    # Physiotherapy sub-type the patient chose (website's "What type of
    # physiotherapy?" step). Only meaningful for physiotherapy. `focus_label` is
    # written into the Plato note; `focus_clinicians` (None = no restriction)
    # limits availability + assignment to who offers the sub-type.
    focus_id = (draft.get("physio_focus") or "").strip() if service_id == "physiotherapy" else ""
    focus_label = PHYSIO_FOCUS_LABELS.get(focus_id, "")
    focus_clinicians = PHYSIO_FOCUS_CLINICIANS.get(focus_id)

    # Duration variant (e.g., "30min" or "55min" for paediatric physiotherapy).
    # Only meaningful for services that define variants. Extracted from draft for
    # availability calculations and used when creating the Plato appointment.
    variant = (draft.get("variant") or "").strip() if svc.get("variants") else ""

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
    # Same-day slots are offered on WhatsApp only (the website keeps Plato's
    # min_days), so only a WhatsApp booking may take one. Its re-check is a
    # little shorter than the offer's lead time: the customer may pick the slot
    # a while after it was offered (config.SAME_DAY_BOOK_LEAD_MINUTES).
    same_day_lead = SAME_DAY_BOOK_LEAD_MINUTES if source == "whatsapp" else None
    clinician_requested = False
    if home:
        candidates = [HOME_VISIT_CLINICIAN]
    elif draft.get("clinician_id"):
        _require(draft["clinician_id"] in CLINICIANS, "Unknown clinician.")
        # A direct API call could pick a clinician who doesn't offer the chosen
        # sub-type (the website only offers valid ones); refuse it.
        _require(focus_clinicians is None or draft["clinician_id"] in focus_clinicians,
                 "That clinician doesn't offer this type of physiotherapy.")
        # Check if the clinician is eligible for this service (e.g. removed from
        # Clinical Pilates while still available in other services).
        service_clinicians = SERVICE_CLINICIANS.get(service_id)
        _require(service_clinicians is None or draft["clinician_id"] in service_clinicians,
                 "That clinician is not available for this service.")
        candidates = [draft["clinician_id"]]
        clinician_requested = True
    else:
        # First available: restrict auto-assignment to the sub-type's clinicians
        # (e.g. a scoliosis booking must never land on someone who isn't Cheryl).
        avail = derive_availability(plato, service_id, day,
                                    focus=focus_id or None, variant=variant or None, home=home, now=now,
                                    fresh=True, same_day_lead=same_day_lead)
        candidates = [cid for cid, slots in avail.items() if time_ in slots]
        _require(candidates, "That time is no longer available.", "slot_taken")
        # Walk the clinic's preferred order (Kristy -> Claire -> Cheryl) so a
        # "First available" booking fills higher-priority clinicians first; the
        # loop below takes the first one that survives the locked re-check.
        # Unlisted clinicians sort last, keeping their relative (config) order.
        _rank = {cid: i for i, cid in enumerate(FIRST_AVAILABLE_PRIORITY)}
        candidates.sort(key=lambda cid: _rank.get(cid, len(_rank)))

    last_err: BookingError | None = None
    for cid in candidates:
        with _lock_for(cid):
            avail = derive_availability(plato, service_id, day,
                                       clinician_id=cid, variant=variant or None, home=home, now=now,
                                       fresh=True, same_day_lead=same_day_lead)
            if time_ not in avail.get(cid, []):
                last_err = BookingError("That time is no longer available.", "slot_taken")
                continue
            if dry_run:
                # Everything above ran for real; stop before the only write.
                ids, visit_id = [], ""
                reference = "DRYRUN-" + uuid.uuid4().hex[:6].upper()
            else:
                # WhatsApp bookings are linked to the patient's own record: the
                # one the assistant matched by name AND number, or a new record
                # in the patient's name (the texter may be booking for a spouse
                # or child who shares their number, so a phone match alone
                # would land on the wrong person). Website bookings stay as
                # they are: unlinked until staff register the patient.
                created_patient = False
                if create_patient and not patient_id:
                    patient_id = _create_patient(plato, name, phone, email)
                    created_patient = True
                ids, visit_id = _create_appointments(
                    plato, svc, cid, day, time_, home, name, phone, email, address,
                    notes, clinician_requested, focus_label, variant,
                    booked_via=BOOKED_VIA.get(source, "website"), patient_id=patient_id)
                reference = "GOJI-" + visit_id[-6:].upper()
            return {
                "ok": True,
                "reference": reference,
                "dry_run": dry_run,
                "source": source,
                "appointment_ids": ids,
                # The patient's own appointment (not a home visit's travel
                # legs): what the confirmation email and its invite key on.
                "visit_id": visit_id,
                "duration_min": _duration_min(svc, variant),
                "clinician_id": cid,
                "clinician_name": CLINICIANS[cid]["name"],
                # Matched clinician's inbox, so the admin email can CC them.
                "clinician_email": CLINICIANS[cid].get("email"),
                "clinician_requested": requested_name,
                "service": svc["title"],
                # Physio sub-type label (empty for non-physio), surfaced in the
                # booking emails alongside the Plato note.
                "physio_focus": focus_label,
                "date": day.isoformat(),
                "time": time_,
                "home": home,
                "patient_id": "" if dry_run else patient_id,
                "patient_created": (not dry_run) and created_patient,
            }
    raise last_err or BookingError("That time is no longer available.", "slot_taken")


def _duration_min(svc: dict, variant: str = "") -> int:
    """Session length: the variant's when it has one, else the service's."""
    if variant and svc.get("variants", {}).get(variant):
        return svc["variants"][variant]["duration_min"]
    return svc["duration_min"]


def _create_patient(plato, name: str, phone: str, email: str = "") -> str:
    """A new Plato patient for a WhatsApp booking (the patient may not be the
    person texting; the texter's number is the contact). Returns its id."""
    payload = {"name": name, "handphone": phone, **({"email": email} if email else {})}
    try:
        r = plato.post("patient", payload) or {}
    except Exception as e:
        raise BookingError("Could not register the patient. Please try again or message us.",
                           "plato_error") from e
    pid = r.get("_id") or r.get("id") or ""
    if not pid:
        raise BookingError("Plato did not accept the new patient.", "plato_error")
    return pid


def _post(plato, payload: dict) -> str:
    r = plato.create_appointment(payload) or {}
    _id = r.get("_id")
    if not r.get("success") or not _id:
        raise BookingError("Plato did not accept the appointment.", "plato_error")
    return _id


def _create_appointments(plato, svc, cid, day, time_, home, name, phone, email,
                         address, notes="", clinician_requested=False,
                         focus_label="", variant="",
                         booked_via="website", patient_id: str = "") -> tuple[list[str], str]:
    """Create the appointment(s). Returns (all_ids, visit_id). Rolls back on any
    failure so a partial home visit never lingers."""
    clin = CLINICIANS[cid]
    color, doctor = clin["calendar"], clin["doctor"]
    # Duration: use variant duration if provided and available, else base service duration.
    dur = _duration_min(svc, variant)
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
    # Patient contact on the visit block. No email (a WhatsApp booking) means no
    # email field and connect False: Plato's portal invite needs an address.
    contact = ({"email": email, "handphone": phone, "connect": True} if email
               else {"handphone": phone, "connect": False})
    if patient_id:
        contact["patient_id"] = patient_id
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
                "description": (f"HOME VISIT — {svc['title']}. Booked via {booked_via}.\n"
                                f"Patient: {name} ({phone}).\nAddress: {address}"
                                f"{focus_line}{note_line}"),
                "starttime": _dt(day, time_),
                "endtime": _dt(day, time_, dur),
                "color": color, "doctor": doctor,
                "code_Bottom": HOME_VISIT_TYPE_CODE,
                **contact,
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
                "description": (f"{svc['title']}. Booked via {booked_via}.\n"
                                f"Patient: {name} ({phone})."
                                f"{focus_line}{clin_line}{note_line}"),
                "starttime": _dt(day, time_),
                "endtime": _dt(day, time_, dur),
                "color": color, "doctor": doctor,
                "code_Bottom": svc["type_code"],
                **({"code_Left": svc["space_code"]} if svc.get("space_code") else {}),
                **contact,
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


# --- Reschedule (the WhatsApp assistant moves an existing appointment) --------

# A move needs this much notice. A later change goes to staff, who apply the
# cancellation policy (the assistant hands it over; see /internal/reschedule).
RESCHEDULE_MIN_NOTICE_HOURS = 24
# Plato status text that marks an appointment as not happening. Same rule as
# the BI marts (fct_appointment_reminders): truthy `cancelled`/`void`, or this.
_DEAD_STATUSES = {"cancelled", "canceled", "no_show", "noshow", "no-show"}


def _truthy_flag(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in ("", "0", "false", "no")
    return bool(value)


def _is_live_booking(a: dict) -> bool:
    """A real, still-booked appointment: not leave/unavailable, not cancelled,
    void or a no-show."""
    if a.get("type") == "leave" or _is_leave_title(str(a.get("title") or "")):
        return False
    if "unavailable" in str(a.get("title") or "").lower():
        return False
    if _truthy_flag(a.get("cancelled")) or _truthy_flag(a.get("void")):
        return False
    return str(a.get("status") or "").strip().lower() not in _DEAD_STATUSES


def _last8(value) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())[-8:]


def _parse_plato_dt(value) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value or "").strip())
    except ValueError:
        return None


def _service_for(type_code: str, minutes: int) -> tuple[str, str] | None:
    """(service_id, variant) for an appointment's Plato type + length, or None.
    Physiotherapy and Mummy & Baby share a type, so the length decides."""
    for sid, svc in SERVICES.items():
        if svc["type_code"] != type_code:
            continue
        if svc["duration_min"] == minutes:
            return sid, ""
        for vid, v in (svc.get("variants") or {}).items():
            if v["duration_min"] == minutes:
                return sid, vid
    return None


class _WithoutAppointment:
    """A Plato client that hides one appointment from `appointments()`, so the
    re-check for a move doesn't count the appointment's own current slot as a
    conflict (e.g. 10:00 -> 10:30 the same day overlaps 10:30-11:00)."""

    def __init__(self, plato, appointment_id: str):
        self._plato = plato
        self._id = appointment_id

    def appointments(self, start, end, fresh=False):
        rows = self._plato.appointments(start, end, fresh=fresh)
        return [a for a in rows if a.get("_id") != self._id]

    def __getattr__(self, name):
        return getattr(self._plato, name)


def _find_appointment(plato, day: date, time_: str, patient_id: str,
                      phone: str) -> dict:
    """The one live appointment on `day` starting at `time_` that belongs to the
    patient. With `patient_id`, an appointment linked to a patient must be
    linked to that one; an unlinked appointment (website/WhatsApp bookings
    carry the phone inline, no patient link) matches on the phone's last 8
    digits. Without `patient_id`, the phone decides."""
    phone8 = _last8(phone)
    matches = []
    for a in plato.appointments(day.isoformat(), day.isoformat(), fresh=True):
        start = _parse_plato_dt(a.get("starttime"))
        if not start or start.date() != day or start.strftime("%H:%M") != time_:
            continue
        if not _is_live_booking(a):
            continue
        linked = str(a.get("patient_id") or "").strip()
        if patient_id and linked:
            ok = linked == patient_id
        else:
            ok = len(phone8) == 8 and _last8(a.get("handphone")) == phone8
        if ok:
            matches.append(a)
    if not matches:
        raise BookingError("We couldn't find that appointment.", "not_found")
    if len(matches) > 1:
        raise BookingError("More than one appointment matches; staff will check.",
                           "ambiguous")
    return matches[0]


def reschedule_appointment(plato, req: dict, *, now: datetime | None = None,
                           dry_run: bool = False) -> dict:
    """Move one existing appointment to a new date/time: same clinician, same
    service and length. Raises BookingError (codes: invalid, too_far,
    not_found, ambiguous, late_change, unsupported, slot_taken, plato_error).

    req keys: phone, patient_id (optional, preferred), old_date, old_time,
    new_date, new_time (YYYY-MM-DD / HH:MM, SGT wall clock).

    The new slot is re-checked fresh inside the clinician's lock, like
    create_booking, with the appointment itself hidden so its current slot
    never blocks its own move. dry_run=True does everything but the PUT.
    """
    phone = str(req.get("phone") or "").strip()
    patient_id = str(req.get("patient_id") or "").strip()
    _require(_PHONE_RE.match(phone), "Please give a valid phone number.")
    _require(not patient_id or (patient_id.replace("-", "").isalnum()
                                and len(patient_id) <= 64), "Invalid patient_id.")
    try:
        old_day = date.fromisoformat(str(req.get("old_date") or "").strip())
        new_day = date.fromisoformat(str(req.get("new_date") or "").strip())
    except ValueError:
        raise BookingError("Dates must be YYYY-MM-DD.")
    old_time = str(req.get("old_time") or "").strip()
    new_time = str(req.get("new_time") or "").strip()
    _require(_TIME_RE.match(old_time) and _TIME_RE.match(new_time),
             "Times must be HH:MM.")
    _require((old_day, old_time) != (new_day, new_time),
             "The new time is the same as the current one.")

    now = now or datetime.now(_SGT).replace(tzinfo=None)
    today = now.date()
    _require(new_day >= today, "The new date is in the past.")
    _require((new_day - today).days <= MAX_ADVANCE_DAYS,
             f"Please choose a date within the next {MAX_ADVANCE_DAYS} days.",
             "too_far")

    appt = _find_appointment(plato, old_day, old_time, patient_id, phone)
    appt_id = str(appt.get("_id") or "")
    start = _parse_plato_dt(appt.get("starttime"))
    end = _parse_plato_dt(appt.get("endtime"))
    _require(appt_id and start and end and end > start,
             "That appointment can't be moved automatically.", "unsupported")

    _require(start - now >= timedelta(hours=RESCHEDULE_MIN_NOTICE_HOURS),
             f"Changes within {RESCHEDULE_MIN_NOTICE_HOURS} hours go to our team.",
             "late_change")

    # Home visits are three appointments (travel / visit / travel); moving one
    # alone would strand the travel blocks, so they stay with staff.
    type_code = str(appt.get("code_Bottom") or "")
    _require(type_code != HOME_VISIT_TYPE_CODE,
             "Home visits are moved by our team.", "unsupported")
    cid = clinician_by_calendar(_calendar_color_for_appointment(appt))
    minutes = int((end - start).total_seconds() // 60)
    found = _service_for(type_code, minutes)
    _require(cid and found, "That appointment can't be moved automatically.",
             "unsupported")
    service_id, variant = found
    svc = SERVICES[service_id]

    with _lock_for(cid):
        avail = derive_availability(_WithoutAppointment(plato, appt_id), service_id,
                                    new_day, clinician_id=cid,
                                    variant=variant or None, now=now, fresh=True)
        _require(new_time in avail.get(cid, []),
                 "That time isn't available.", "slot_taken")
        if not dry_run:
            payload = {"starttime": _dt(new_day, new_time),
                       "endtime": _dt(new_day, new_time, minutes)}
            desc = appt.get("description")
            if isinstance(desc, str):
                line = f"Moved via WhatsApp assistant from {old_day.isoformat()} {old_time}."
                payload["description"] = f"{desc}\n{line}" if desc.strip() else line
            try:
                r = plato.update_appointment(
                    appt_id, payload, days=(old_day.isoformat(), new_day.isoformat()))
            except Exception:
                raise BookingError("Could not move the appointment.", "plato_error")
            if isinstance(r, dict) and r.get("success") is False:
                raise BookingError("Plato did not accept the change.", "plato_error")

    return {
        "ok": True,
        "dry_run": dry_run,
        "source": "whatsapp",
        "reference": "GOJI-" + appt_id[-6:].upper(),
        "appointment_id": appt_id,
        "clinician_id": cid,
        "clinician_name": CLINICIANS[cid]["name"],
        "clinician_email": CLINICIANS[cid].get("email"),
        "service": svc["title"],
        "old_date": old_day.isoformat(),
        "old_time": old_time,
        "new_date": new_day.isoformat(),
        "new_time": new_time,
        # The new slot, under the keys the booking callback reads.
        "date": new_day.isoformat(),
        "time": new_time,
    }


# --- Cancel (the WhatsApp assistant cancels an existing appointment) ----------

def cancel_appointment(plato, req: dict, *, now: datetime | None = None,
                       dry_run: bool = False) -> dict:
    """Cancel one existing appointment with at least 24 hours' notice. Raises
    BookingError (codes: invalid, not_found, ambiguous, late_change,
    unsupported, plato_error).

    req keys: phone, patient_id (optional, preferred), date, time (YYYY-MM-DD /
    HH:MM, SGT wall clock).

    Goji's Plato has no cancelled flag (no appointment carries `cancelled`,
    `void` or `status`; checked 24 Nov 2026): staff cancel by deleting the
    appointment, so this deletes it too. The clinic email is the record.
    dry_run=True does everything but the DELETE.
    """
    phone = str(req.get("phone") or "").strip()
    patient_id = str(req.get("patient_id") or "").strip()
    _require(_PHONE_RE.match(phone), "Please give a valid phone number.")
    _require(not patient_id or (patient_id.replace("-", "").isalnum()
                                and len(patient_id) <= 64), "Invalid patient_id.")
    try:
        day = date.fromisoformat(str(req.get("date") or "").strip())
    except ValueError:
        raise BookingError("Dates must be YYYY-MM-DD.")
    time_ = str(req.get("time") or "").strip()
    _require(_TIME_RE.match(time_), "Times must be HH:MM.")

    now = now or datetime.now(_SGT).replace(tzinfo=None)
    appt = _find_appointment(plato, day, time_, patient_id, phone)
    appt_id = str(appt.get("_id") or "")
    start = _parse_plato_dt(appt.get("starttime"))
    end = _parse_plato_dt(appt.get("endtime"))
    _require(appt_id and start and end and end > start,
             "That appointment can't be cancelled automatically.", "unsupported")
    _require(start - now >= timedelta(hours=RESCHEDULE_MIN_NOTICE_HOURS),
             f"Changes within {RESCHEDULE_MIN_NOTICE_HOURS} hours go to our team.",
             "late_change")
    # Home visits are three appointments (travel / visit / travel): deleting
    # the visit alone would strand the travel blocks, so they stay with staff.
    type_code = str(appt.get("code_Bottom") or "")
    _require(type_code != HOME_VISIT_TYPE_CODE,
             "Home visits are cancelled by our team.", "unsupported")
    cid = clinician_by_calendar(_calendar_color_for_appointment(appt))
    _require(cid, "That appointment can't be cancelled automatically.", "unsupported")
    found = _service_for(type_code, int((end - start).total_seconds() // 60))
    service = SERVICES[found[0]]["title"] if found else "Appointment"

    if not dry_run:
        with _lock_for(cid):
            try:
                r = plato.delete_appointment(appt_id, days=(day.isoformat(),))
            except Exception:
                raise BookingError("Could not cancel the appointment.", "plato_error")
            if isinstance(r, dict) and r.get("success") is False:
                raise BookingError("Plato did not accept the cancellation.", "plato_error")

    return {
        "ok": True,
        "dry_run": dry_run,
        "source": "whatsapp",
        "reference": "GOJI-" + appt_id[-6:].upper(),
        "appointment_id": appt_id,
        "clinician_id": cid,
        "clinician_name": CLINICIANS[cid]["name"],
        "clinician_email": CLINICIANS[cid].get("email"),
        "service": service,
        "date": day.isoformat(),
        "time": time_,
    }
