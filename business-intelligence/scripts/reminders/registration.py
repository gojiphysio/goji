"""Has the patient filled in Plato's registration form? If not, the 48-hour
reminder asks again, by email and on WhatsApp (clinic decision, 25 Nov 2026).

THE FLAG: the form's last step is the patient signing the "Clinic Consent
Form", which Plato stores on the profile (others.consents, with the time).
Signed = registration done. The nightly import puts it in
dim_patient.consent_signed_at; this module rechecks a profile live in Plato
before asking, so someone who signed today isn't asked. No profile at all
(none on the appointment, none matching the phone or email) = owed.

THE LINK: goji-booking's stable form link,
https://booking.gojiphysio.com/form/<appointment id>.<signature>, which works
out the right Plato form when tapped (pre-registration without a profile, the
profile's update form with one). The same link goes in the email and in the
WhatsApp template's URL button, signed with the internal token
(INTERNAL_TOKEN, mounted from wa-agent-internal-token). form_token is a copy
of booking/formlink.py; a test keeps them equal.

Plato reads use the job's Plato key, no retries, and at most MAX_READS a run:
the clinic shares 20 requests a minute. Any failure means "don't ask": a
missing reminder line is better than a wrong one.
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
    """Whether this patient still owes the registration form. `row` carries
    profile_id and consent_signed (last night's flag). Never raises; any
    doubt = not owed."""
    if row.get("consent_signed"):
        return False
    pid = row.get("profile_id") or ""
    if not pid:
        return True
    if plato is None:
        return False
    try:
        patient = _one(plato.get(f"patient/{pid}"))
    except Exception as e:
        log.warning("registration check for appointment %s skipped: %s",
                    row.get("appointment_id"), type(e).__name__)
        return False
    return patient is not None and not consent_signed(patient)


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
