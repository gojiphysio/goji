"""
Thin Plato API client for the booking service.

Bearer-token auth (Secret Manager `plato-api-key`), same base as the ingestion
jobs. Read helpers are safe; write helpers (`create_appointment`,
`delete_appointment`) mutate the live clinic calendar — callers must guard them
(availability re-check + per-clinician lock; see booking.py).
"""
from __future__ import annotations

import logging
import os
import threading
import time

import requests

log = logging.getLogger("booking.plato")

BASE = "https://clinic.platomedical.com/api"
TIMEOUT_S = 30
PER_PAGE_SLEEP_S = 1.0  # pace multi-page reads under Plato's 20 req/min limit
# The broad recurrence/long-block sweep is many pages and must NOT starve the
# interactive per-day fetches of Plato's 20 req/min budget (doing so on the
# request path is what took the booking form down once). It therefore runs in the
# BACKGROUND only, paced far slower than the per-day path (one page every
# BROAD_PAGE_SLEEP_S) so it stays well under the limit and leaves headroom, and
# its result is cached for BROAD_TTL_S.
BROAD_TTL_S = float(os.environ.get("PLATO_BROAD_TTL", "1800"))
BROAD_PAGE_SLEEP_S = float(os.environ.get("PLATO_BROAD_PAGE_SLEEP", "5"))
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
        # Broad sweep: (monotonic_ts, rows, (start,end)). Maintained by a single
        # background refresher; the request path only ever READS it.
        self._broad_cache: tuple[float, list[dict], tuple[str, str]] | None = None
        self._broad_lock = threading.Lock()
        self._broad_refreshing = False

    def _url(self, path: str) -> str:
        return f"{BASE}/{self.db}/{path.lstrip('/')}"

    def get(self, path: str, params: dict | None = None, _retries: int = 3):
        """GET with exponential backoff on 429/5xx (Plato caps at 20 req/min).

        Backoff is capped low (<=8s/step) because this sits on the interactive
        availability path — a long 60s backoff made the booking form hang for
        minutes when a burst of date changes tripped the rate limit. The frontend
        debounces + the per-day appointment cache keep the request rate down."""
        delay = 1.0
        for attempt in range(_retries + 1):
            try:
                r = self.s.get(self._url(path), params=params, timeout=self.timeout)
            except (requests.ConnectionError, requests.Timeout):
                # Plato resets long-lived connections mid-sweep; treat like a 5xx.
                if attempt >= _retries:
                    raise
                time.sleep(delay)
                delay = min(delay * 2, 8)
                continue
            if r.status_code in (429, 500, 502, 503) and attempt < _retries:
                time.sleep(delay)
                delay = min(delay * 2, 8)
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

    def appointments_broad(self, start_date: str, end_date: str) -> list[dict]:
        """Recurring masters + multi-day blocks over a wide window, for the
        availability overlay. NON-BLOCKING and best-effort: it returns whatever is
        cached (an EMPTY list on a cold instance) and never fetches on the caller's
        thread — a stale or cold read just kicks off a background refresh. So the
        interactive path never pays for this many-page sweep, and a Plato hiccup
        here can never break availability (the caller falls back to the per-day
        fetch). Recurrences/long blocks change slowly, so brief staleness is fine."""
        key = (start_date, end_date)
        now = time.monotonic()
        c = self._broad_cache
        if c and c[2] == key and now - c[0] < BROAD_TTL_S:
            return c[1]
        self._refresh_broad_async(key)          # cold or stale -> refresh behind us
        return c[1] if c and c[2] == key else []  # serve stale, or empty when cold

    def warm_broad(self, start_date: str, end_date: str) -> None:
        """Prime the broad cache in the background at startup, so it's ready before
        the first availability request (which would otherwise see it empty)."""
        self._refresh_broad_async((start_date, end_date))

    def _refresh_broad_async(self, key: tuple[str, str]) -> None:
        with self._broad_lock:
            if self._broad_refreshing:
                return  # one refresh in flight is enough (no thundering herd)
            self._broad_refreshing = True

        def _run():
            try:
                rows = self._get_all_slow("appointment",
                                          {"start_date": key[0], "end_date": key[1]})
                self._broad_cache = (time.monotonic(), rows, key)
                log.info("broad sweep refreshed: %d rows for %s..%s",
                         len(rows), key[0], key[1])
            except Exception as e:
                # Keep serving the last good rows; retry on the next stale read.
                log.warning("broad sweep refresh failed (%s..%s): %s", key[0], key[1], e)
            finally:
                self._broad_refreshing = False

        threading.Thread(target=_run, daemon=True).start()

    def _get_all_slow(self, path: str, params: dict | None = None) -> list[dict]:
        """Like get_all but paced by BROAD_PAGE_SLEEP_S between pages, so the
        background sweep stays comfortably under Plato's 20 req/min and leaves
        budget for the interactive per-day fetches."""
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
            if len(rows) < 20:
                break
            page += 1
            time.sleep(BROAD_PAGE_SLEEP_S)
        return out

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
