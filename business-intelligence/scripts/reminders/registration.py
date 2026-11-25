"""Has the patient filled in Plato's registration form? If not, the 48-hour
reminder asks again, with a fresh link (clinic decision, 25 Nov 2026).

THE FLAG: the form's last step is the patient signing the "Clinic Consent
Form", which Plato stores on the profile (others.consents, with the time).
Signed = registration done. Every self-registered profile carries it; the
bare profiles the WhatsApp assistant creates don't. The nightly import puts it
in dim_patient.consent_signed_at; this module rechecks Plato live before
asking, so someone who signed today isn't asked.

  - No profile (not on the appointment, none matching the phone or email):
    Plato's pre-registration form, which creates the profile.
  - A profile without a signed consent: that profile's update form. Never the
    pre-registration form, which would duplicate them.
  - A signed consent: nothing.

Plato reads use the job's Plato key, no retries, and at most MAX_READS a run:
the clinic shares 20 requests a minute. Any failure means "don't ask": a
missing reminder line is better than a wrong one.
"""
from __future__ import annotations

import logging
import os

import requests

log = logging.getLogger("reminders.registration")

PLATO_BASE = os.environ.get("PLATO_BASE", "https://clinic.platomedical.com/api")
PLATO_DB = os.environ.get("PLATO_DB", "gojihealth")
PLATO_API_KEY = os.environ.get("PLATO_API_KEY", "")
MAX_READS = 12
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


def form_link(plato: Plato, row: dict) -> str | None:
    """The registration form link if this patient hasn't signed, else None.
    `row` carries appointment_id, profile_id and consent_signed (last night's
    flag). Never raises."""
    if row.get("consent_signed"):
        return None
    try:
        pid = row.get("profile_id") or ""
        if not pid:
            return _url(plato.get(f"appointment/{row['appointment_id']}/prereg"))
        patient = _one(plato.get(f"patient/{pid}"))
        if patient is None or consent_signed(patient):
            return None
        return _url(plato.get(f"patient/{pid}/updatelink"))
    except Exception as e:
        log.warning("registration check for appointment %s skipped: %s",
                    row.get("appointment_id"), type(e).__name__)
        return None


def attach(rows: list[dict], plato: Plato | None) -> None:
    """Set row['form_url'] on each row whose patient still owes the form."""
    for r in rows:
        r["form_url"] = form_link(plato, r) if plato else None
