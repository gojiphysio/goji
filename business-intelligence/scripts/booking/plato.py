"""
Thin Plato API client for the booking service.

Bearer-token auth (Secret Manager `plato-api-key`), same base as the ingestion
jobs. Read helpers are safe; write helpers (`create_appointment`,
`delete_appointment`) mutate the live clinic calendar — callers must guard them
(availability re-check + per-clinician lock; see booking.py).
"""
from __future__ import annotations

import os

import requests

BASE = "https://clinic.platomedical.com/api"
TIMEOUT_S = 30


class PlatoError(RuntimeError):
    pass


class PlatoClient:
    def __init__(self, db: str | None = None, token: str | None = None,
                 timeout: int = TIMEOUT_S):
        self.db = db or os.environ.get("PLATO_DB", "gojihealth")
        token = token or os.environ.get("PLATO_API_KEY")
        if not token:
            raise PlatoError("PLATO_API_KEY not set")
        self.timeout = timeout
        self.s = requests.Session()
        self.s.headers.update({
            "accept": "application/json",
            "Authorization": f"Bearer {token}",
        })

    def _url(self, path: str) -> str:
        return f"{BASE}/{self.db}/{path.lstrip('/')}"

    def get(self, path: str, params: dict | None = None):
        r = self.s.get(self._url(path), params=params, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def post(self, path: str, payload: dict):
        r = self.s.post(self._url(path), json=payload, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def delete(self, path: str):
        r = self.s.delete(self._url(path), timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    # --- domain helpers ---
    def appointments(self, start_date: str, end_date: str) -> list[dict]:
        """All appointments with starttime in [start_date, end_date] (YYYY-MM-DD)."""
        data = self.get("appointment", {"start_date": start_date, "end_date": end_date})
        return data if isinstance(data, list) else data.get("data", [])

    def online_booking_config(self) -> dict:
        """The clinic's online-booking calendars + per-clinician rules."""
        return self.get("onlineapptbooking/list")

    def create_appointment(self, payload: dict) -> dict:
        """Create one appointment. Returns {success, _id}. Does NOT check conflicts
        (Plato allows overlaps) — guard at the call site."""
        return self.post("appointment", payload)

    def delete_appointment(self, appointment_id: str) -> dict:
        return self.delete(f"appointment/{appointment_id}")
