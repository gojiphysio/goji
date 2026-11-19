"""
Book an appointment for a customer, from the chat (direct booking, 19 Nov 2026).

The model never books. It fills `booking` in its proposal and asks the
customer to confirm; only when the customer confirms in a LATER message does
app.py call `book()` here, which goes through goji-booking's private
`/internal/book` route (the same create_booking as the website: availability,
locks, clinician rules, the Plato write).

Dry run is the default (`WA_AGENT_BOOKING_DRY_RUN`, on unless set to 0):
goji-booking validates and checks the slot but writes nothing, so testing never
touches the live calendar. `WA_AGENT_BOOKING_SIMULATE=1` (local only) checks
the slot against the public availability API instead, for testing before the
booking service has the private route.
"""
from __future__ import annotations

import logging
import re
import secrets
from datetime import date

import requests

from . import config, tools

log = logging.getLogger("wa_agent.booking")

CLINICIAN_IDS = {"cheryl": "cheryl-long", "claire": "claire-ng", "kristy": "kristy-ng",
                 "camille": "camille-tan"}
FIELDS = ("service", "date", "time", "clinician", "physio_focus", "variant", "format",
          "full_name", "email", "address", "notes")
_TIME = re.compile(r"^\d{2}:\d{2}$")


class BookingFailed(Exception):
    def __init__(self, message: str, code: str = "error"):
        super().__init__(message)
        self.code = code


def complete(b: dict | None) -> bool:
    """Has the model collected enough to book?"""
    if not b:
        return False
    try:
        date.fromisoformat(b.get("date", ""))
    except ValueError:
        return False
    return bool(b.get("service") and _TIME.match(b.get("time", "")) and
                (b.get("full_name") or "").strip() and
                (b.get("format") != "home" or (b.get("address") or "").strip()))


def _clinician_id(name: str) -> str:
    return CLINICIAN_IDS.get((name or "").strip().split(" ")[0].lower(), "")


def book(b: dict, *, wa_id: str, http=requests) -> dict:
    """{ok, reference, clinician_name, service, date, time, dry_run} or BookingFailed."""
    if config.BOOKING_SIMULATE and config.STATE_BACKEND == "memory":
        return _simulate(b, http)
    if not config.INTERNAL_TOKEN:
        raise BookingFailed("booking isn't set up", "not_configured")
    body = {"service": b["service"], "date": b["date"], "time": b["time"],
            "format": b.get("format") or "clinic", "name": b["full_name"].strip(),
            "phone": "+" + re.sub(r"\D", "", wa_id), "email": (b.get("email") or "").strip(),
            "clinician_id": _clinician_id(b.get("clinician", "")),
            "physio_focus": b.get("physio_focus", ""), "variant": b.get("variant", ""),
            "address": b.get("address", ""), "notes": b.get("notes", ""),
            "source": "whatsapp", "dry_run": config.BOOKING_DRY_RUN}
    try:
        r = http.post(f"{config.BOOKING_API_BASE}/internal/book", json=body, timeout=30,
                      headers={"X-Internal-Token": config.INTERNAL_TOKEN})
        data = r.json()
    except Exception as e:
        log.warning("booking call failed: %s", e)
        raise BookingFailed("the booking system didn't answer", "unreachable")
    if not data.get("ok"):
        raise BookingFailed(data.get("error") or "booking refused", data.get("code") or "error")
    return data


def _simulate(b: dict, http) -> dict:
    """Local testing: confirm the slot is open, write nothing."""
    try:
        avail = tools.get_times({"service": b["service"], "date": b["date"],
                                 "focus": b.get("physio_focus") or None}, http=http)
    except Exception as e:
        raise BookingFailed(f"couldn't check the time: {e}", "unreachable")
    by = avail.get("by_clinician") or {}
    wanted = (b.get("clinician") or "").split(" ")[0].lower()
    who = [n for n, slots in by.items() if b["time"] in slots
           and (not wanted or n.lower().startswith(wanted))]
    if not who:
        raise BookingFailed("That time is no longer available.", "slot_taken")
    return {"ok": True, "dry_run": True, "reference": "DRYRUN-" + secrets.token_hex(3).upper(),
            "clinician_name": who[0], "service": b["service"], "date": b["date"],
            "time": b["time"]}


def confirmation_text(res: dict, *, first_name: str = "") -> str:
    """What the customer sees once it's booked. Composed in code from the
    booking system's answer, so it can't claim a booking that didn't happen."""
    d = date.fromisoformat(res["date"])
    h, m = map(int, res["time"].split(":"))
    when = f"{d:%a} {d.day} {d:%b}, {(h % 12) or 12}:{m:02d}{'am' if h < 12 else 'pm'}"
    who = (res.get("clinician_name") or "").split(" ")[0]
    text = (f"You're booked{', ' + first_name if first_name else ''}! {when}"
            f"{' with ' + who if who else ''} (ref {res['reference']}).\n\n"
            "We'll send a reminder before your appointment. See you then 😊")
    if res.get("dry_run"):
        text += "\n\n🧪 TEST: dry run, nothing was booked in the calendar."
    return text
