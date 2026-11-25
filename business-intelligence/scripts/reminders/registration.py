"""Has the patient filled in Plato's registration form? If not, the 48-hour
reminder asks again, with a fresh link (clinic decision, 25 Nov 2026).

Two cases:
  - NO PROFILE: the appointment isn't linked to a Plato patient. Plato's
    pre-registration form creates the profile and links the appointment; in
    every case since Sep 2026 the submitted form left the appointment linked
    (last edited by "Self Registration"). So unlinked = not registered,
    unless a profile already matches the phone or email (a returning patient
    who booked on the website; the reminder query checks that), because the
    form would make a duplicate profile.
  - A PROFILE WITH NO DATE OF BIRTH: every profile made or completed through
    the form has one (checked on the self-registered profiles, 25 Nov 2026);
    the bare profiles the WhatsApp assistant creates (name and number) don't.
    These get the profile's update form. The rule looks at what the profile
    holds, not at who edited it last, so staff completing it at the desk also
    counts. The query's first pass uses last night's data (age_band is derived
    from the date of birth); the live read here catches anyone who filled it
    in since.

Plato reads use the job's Plato key on the non-urgent path, no retries, and at
most MAX_READS a run: the clinic shares 20 requests a minute. Any failure
means "don't ask": a missing reminder line is better than a wrong one.
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


def has_dob(patient: dict) -> bool:
    dob = str(patient.get("dob") or "").strip()
    return bool(dob) and not dob.startswith("0000")


def form_link(plato: Plato, row: dict) -> str | None:
    """The registration form link if this appointment's patient still owes it,
    else None. `row` carries appointment_id, patient_id and needs_form_check
    (the query's cheap first pass). Never raises."""
    if not row.get("needs_form_check"):
        return None
    try:
        pid = row.get("patient_id") or ""
        if not pid:
            return _url(plato.get(f"appointment/{row['appointment_id']}/prereg"))
        patient = _one(plato.get(f"patient/{pid}"))
        if patient is None or has_dob(patient):
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
