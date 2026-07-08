"""
Thin Plato API client for the booking service.

Bearer-token auth (Secret Manager `plato-api-key`), same base as the ingestion
jobs. Read helpers are safe; write helpers (`create_appointment`,
`delete_appointment`) mutate the live clinic calendar — callers must guard them
(availability re-check + per-clinician lock; see booking.py).
"""
from __future__ import annotations

import os
import time

import requests

BASE = "https://clinic.platomedical.com/api"
TIMEOUT_S = 30
PER_PAGE_SLEEP_S = 1.0  # pace multi-page reads under Plato's 20 req/min limit
# The online-booking config (clinician hours/rules) is effectively static, but
# derive_availability reads it on every slot lookup. Cache it briefly so a burst
# of availability calls (a user clicking around dates/clinicians) hits Plato once.
CONFIG_TTL_S = float(os.environ.get("PLATO_CONFIG_TTL", "300"))
# A day's appointments are the other input to availability. derive_availability
# fetches the whole day (all calendars) on every lookup, so caching it briefly
# lets clinician switches / re-picks on the same day skip the Plato round-trip.
# Short TTL: create_booking re-derives under a lock before writing, so a booking
# made within the window is still caught at submit.
APPTS_TTL_S = float(os.environ.get("PLATO_APPTS_TTL", "20"))


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
        self._cfg_cache: dict | None = None
        self._cfg_ts = 0.0
        self._appts_cache: dict[tuple[str, str], tuple[float, list[dict]]] = {}

    def _url(self, path: str) -> str:
        return f"{BASE}/{self.db}/{path.lstrip('/')}"

    def get(self, path: str, params: dict | None = None, _retries: int = 4):
        """GET with exponential backoff on 429/5xx (Plato caps at 20 req/min)."""
        delay = 2.0
        for attempt in range(_retries + 1):
            r = self.s.get(self._url(path), params=params, timeout=self.timeout)
            if r.status_code in (429, 500, 502, 503) and attempt < _retries:
                time.sleep(delay)
                delay = min(delay * 2, 60)
                continue
            r.raise_for_status()
            return r.json()

    def get_all(self, path: str, params: dict | None = None) -> list[dict]:
        """Page through a list endpoint (20/page) via `current_page`, returning
        every row. Plato paginates all list endpoints, so a single busy day can
        span multiple pages — never trust page 1 alone."""
        out: list[dict] = []
        params = dict(params or {})
        page = 1
        while True:
            params["current_page"] = page
            batch = self.get(path, params)
            rows = batch if isinstance(batch, list) else batch.get("data", [])
            if not rows:
                break
            out.extend(rows)
            if len(rows) < 20:  # last (partial) page
                break
            page += 1
            time.sleep(PER_PAGE_SLEEP_S)
        return out

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
        """Every appointment with starttime in [start_date, end_date] (YYYY-MM-DD),
        across all pages. Cached per range for APPTS_TTL_S (the availability hot
        path re-reads the same day repeatedly)."""
        key = (start_date, end_date)
        now = time.monotonic()
        hit = self._appts_cache.get(key)
        if hit and now - hit[0] < APPTS_TTL_S:
            return hit[1]
        rows = self.get_all("appointment",
                            {"start_date": start_date, "end_date": end_date})
        self._appts_cache[key] = (now, rows)
        return rows

    def online_booking_config(self) -> dict:
        """The clinic's online-booking calendars + per-clinician rules.

        Cached for CONFIG_TTL_S — it barely changes, and re-fetching it on every
        availability lookup is a needless Plato round-trip on the hot path.
        """
        now = time.monotonic()
        if self._cfg_cache is not None and now - self._cfg_ts < CONFIG_TTL_S:
            return self._cfg_cache
        self._cfg_cache = self.get("onlineapptbooking/list")
        self._cfg_ts = now
        return self._cfg_cache

    def create_appointment(self, payload: dict) -> dict:
        """Create one appointment. Returns {success, _id}. Does NOT check conflicts
        (Plato allows overlaps) — guard at the call site."""
        r = self.post("appointment", payload)
        self._appts_cache.clear()  # a write changes availability — never re-read stale
        return r

    def delete_appointment(self, appointment_id: str) -> dict:
        r = self.delete(f"appointment/{appointment_id}")
        self._appts_cache.clear()
        return r
