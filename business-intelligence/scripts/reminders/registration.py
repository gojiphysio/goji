"""Does this patient still owe Plato's registration form? If so, the 48-hour
reminder asks again, by email and on WhatsApp (clinic decisions, 25 and
26 Nov 2026).

Only NEW patients are asked: no Plato profile on the appointment and none
matching the phone or email (the reminder query works that out). They get
Plato's pre-registration form, which needs no login and creates the profile;
submitting it links the appointment, so the next reminder won't ask. A
patient with a profile is never asked: the clinic fixes gaps in an existing
profile in person.

THE LINK: goji-booking's stable form link,
https://booking.gojiphysio.com/form/<appointment id>.<signature>, which opens
Plato's pre-registration form, or a "you're all set" page once the
appointment has a profile. The same link goes in the email and in the
WhatsApp template's URL button, signed with the internal token
(INTERNAL_TOKEN, mounted from wa-agent-internal-token). form_token is a copy
of booking/formlink.py; a test keeps them equal.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os

import requests

log = logging.getLogger("reminders.registration")

PLATO_BASE = os.environ.get("PLATO_BASE", "https://clinic.platomedical.com/api")
PLATO_DB = os.environ.get("PLATO_DB", "gojihealth")
PLATO_API_KEY = os.environ.get("PLATO_API_KEY", "")
MAX_READS = 12
FORM_LINK_BASE = os.environ.get("FORM_LINK_BASE", "https://booking.gojiphysio.com/form/")
FORM_SECRET = os.environ.get("INTERNAL_TOKEN", "")


def form_token(appointment_id: str, secret: str = FORM_SECRET) -> str:
    """Copy of booking/formlink.token (separate deploys; a test checks)."""
    if not (secret and appointment_id):
        return ""
    key = hmac.new(secret.encode(), b"form-link", hashlib.sha256).digest()
    sig = hmac.new(key, appointment_id.encode(), hashlib.sha256).hexdigest()[:20]
    return f"{appointment_id}.{sig}"
TIMEOUT_S = 10


def _one(payload):
    """Plato answers some single-record GETs with a one-item list."""
    if isinstance(payload, list):
        return payload[0] if len(payload) == 1 and isinstance(payload[0], dict) else None
    return payload if isinstance(payload, dict) else None


class Plato:
    def __init__(self, key: str = PLATO_API_KEY, session=None):
        self.key, self.http, self.reads = key, session or requests, 0

    def get(self, path: str):
        if self.reads >= MAX_READS:
            raise RuntimeError("read cap reached")
        self.reads += 1
        r = self.http.get(f"{PLATO_BASE}/{PLATO_DB}/{path.lstrip('/')}", timeout=TIMEOUT_S,
                          headers={"Authorization": f"Bearer {self.key}"})
        r.raise_for_status()
        return r.json()


def _url(payload) -> str | None:
    url = (_one(payload) or {}).get("url")
    return url if isinstance(url, str) and url.startswith("https://") else None


CONSENT_TITLE = "Clinic Consent Form"  # same as ingestion/plato_patients


def consent_signed(patient: dict) -> bool:
    """The profile carries a signed Clinic Consent Form."""
    others = patient.get("others")
    consents = others.get("consents") if isinstance(others, dict) else None
    return any(isinstance(c, dict) and c.get("title") == CONSENT_TITLE
               and isinstance(c.get("created_on"), (int, float)) and c["created_on"] > 0
               for c in consents or [])


def owes_form(plato: Plato | None, row: dict) -> bool:
    """A NEW patient owes the form: no Plato profile on the appointment and
    none matching the phone or email (row['profile_id'] empty). A patient with
    a profile is never asked (clinic decision, 26 Nov 2026: gaps in an
    existing profile are fixed in person). No Plato read."""
    return not row.get("profile_id")


def form_link(plato: Plato | None, row: dict, secret: str | None = None) -> str | None:
    """The form link if this patient still owes the form, else None."""
    token = form_token(row["appointment_id"], FORM_SECRET if secret is None else secret)
    if not token or not owes_form(plato, row):
        return None
    return FORM_LINK_BASE + token


def attach(rows: list[dict], plato: Plato | None) -> None:
    """Set row['form_url'] (the email's link) and row['form_token'] (the
    WhatsApp button's) on each row whose patient still owes the form."""
    for r in rows:
        r["form_url"] = form_link(plato, r)
        r["form_token"] = r["form_url"][len(FORM_LINK_BASE):] if r["form_url"] else ""
