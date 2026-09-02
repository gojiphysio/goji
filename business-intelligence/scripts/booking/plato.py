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
from datetime import datetime, timedelta

import requests

log = logging.getLogger("booking.plato")
# Same switch availability.py uses, so one env var turns on the whole
# slot-derivation trace (see DIAGNOSIS.md).
_DIAG = os.environ.get("BOOKING_AVAILABILITY_DEBUG", "").lower() in ("1", "true", "yes")

BASE = "https://clinic.platomedical.com/api"
TIMEOUT_S = 30
# Plato throttles at 20 requests/min per API key. We pace ourselves to just
# under that (see _RateLimiter) rather than discovering the cap via 429s: a 429
# costs 7s of retry backoff and then surfaces as a 502 on the booking form.
PLATO_RATE_PER_MIN = float(os.environ.get("PLATO_RATE_PER_MIN", "18"))
PLATO_RATE_BURST = float(os.environ.get("PLATO_RATE_BURST", "12"))
# How long a caller will wait for a token before giving up. Longer than a
# couple of refills is worse than degrading — the visitor is staring at a
# spinner on /book. Note `get()` spends this per retry attempt, so the worst
# case for one call is ~4 x this plus the 7s of 429 backoff; keep it small.
PLATO_RATE_MAX_WAIT_S = float(os.environ.get("PLATO_RATE_MAX_WAIT", "10"))
# When Plato does say 429, every caller in the process stops for this long.
# Without a shared cooldown, N in-flight requests each retry 3x, so being
# throttled multiplies our request rate by four and the budget never recovers —
# a retry storm that outlives whatever caused the first 429. Slightly longer
# than Plato's 60s window would be wasteful; ~20s lets it drain and refill.
PLATO_429_COOLDOWN_S = float(os.environ.get("PLATO_429_COOLDOWN", "20"))
# Leave/vacation/block title keywords (case-insensitive): appointments with these in the title
# block availability like normal appointments (they're just regular appointments on the
# clinician's calendar in Plato, identified by title pattern from real data analysis).
LEAVE_KEYWORDS = ("leave", "holiday", "vacation", "pto", "ooo", "out of office", "block")
# The online-booking config (clinician hours/rules) is effectively static, but
# derive_availability reads it on every slot lookup. Cache it briefly so a burst
# of availability calls (a user clicking around dates/clinicians) hits Plato once.
CONFIG_TTL_S = float(os.environ.get("PLATO_CONFIG_TTL", "300"))
# When a config refresh fails and we fall back to the last good copy, wait this
# long before trying Plato again. Without it the expired TTL means *every*
# request retries the fetch, piling load onto an API that is already struggling
# — the opposite of what you want mid-incident.
CONFIG_RETRY_S = float(os.environ.get("PLATO_CONFIG_RETRY", "30"))
# A day's appointments are the other input to availability. derive_availability
# fetches the whole day (all calendars) on every lookup, so caching it briefly
# lets clinician switches / re-picks on the same day skip the Plato round-trip.
# Short TTL: create_booking re-derives under a lock before writing, so a booking
# made within the window is still caught at submit.
APPTS_TTL_S = float(os.environ.get("PLATO_APPTS_TTL", "20"))
# Multi-day ranges are a different animal: only the month-summary endpoint asks
# for them, they cost one Plato request per 20 appointments (a busy month is
# 10+ pages, half the minute's budget), and they only paint the calendar's
# date shading — the visitor's actual date pick re-reads that day fresh, and
# create_booking re-derives under a lock before writing. So cache them for as
# long as the summary itself is cached (AVAIL_SUMMARY_CACHE_TTL, 5 min).
# Before this split, every summary variant (focus/clinician/home) missed the
# 20s cache and re-paged the same month, which is what pinned us at the cap.
APPTS_RANGE_TTL_S = float(os.environ.get("PLATO_APPTS_RANGE_TTL", "300"))


def _is_leave_title(title: str) -> bool:
    """Check if an appointment title indicates a leave/vacation/holiday block."""
    if not title:
        return False
    title_lower = title.lower()
    return any(keyword in title_lower for keyword in LEAVE_KEYWORDS)


class PlatoError(RuntimeError):
    pass


def _normalise_booking_config(payload):
    """Coerce whatever `onlineapptbooking/list` returned into the config dict,
    or None if it isn't one.

    Plato changed this endpoint's shape on 2026-09-01 with no notice: it used to
    return the booking-config object directly, and now returns a *list* of them
    (one per booking key). That took the /book form down for hours, because
    `_rules_for` does `cfg.get("calendars")` and a list has no `.get`. We accept
    both shapes so their next flip back doesn't repeat it.

    From a list we prefer the entry with `active: true`, falling back to the
    first one carrying `calendars` — Plato allows several booking keys and only
    the active one reflects what customers actually see.
    """
    if isinstance(payload, dict) and "calendars" in payload:
        return payload
    if isinstance(payload, list):
        candidates = [e for e in payload
                      if isinstance(e, dict) and "calendars" in e]
        for entry in candidates:
            if entry.get("active"):
                return entry
        if candidates:
            return candidates[0]
    return None


class _RateLimiter:
    """Token bucket that paces our own calls under Plato's 20 req/min cap.

    Plato throttles per API key, so the budget is clinic-wide — every
    availability lookup, month summary and booking write draws on the same
    bucket. The service runs `--max-instances=1` (deploy-booking.yml), which is
    what makes a single in-process bucket authoritative, the same reason the
    per-clinician booking locks live in-process. Raise max-instances and this
    needs a shared store, exactly like those locks.

    Starts full, so a burst (paging a month of appointments) goes straight
    through and only the tail waits. Waiting ~3s for a token beats a 429, which
    costs 7s of backoff and still ends as a 502 on the form.
    """

    def __init__(self, rate_per_min: float, burst: float):
        self._interval = 60.0 / rate_per_min if rate_per_min > 0 else 0.0
        self._burst = max(1.0, burst)
        self._tokens = self._burst
        self._updated = time.monotonic()
        self._penalty_until = 0.0
        self._lock = threading.Lock()

    def acquire(self, max_wait_s: float) -> None:
        """Consume one token, sleeping until one is free. Raises PlatoError if
        the wait would exceed `max_wait_s` — the caller degrades to "no slots"
        rather than holding the request open.

        During a cooldown (see `penalise`) the wait is by definition longer than
        a token refill, so callers give up immediately instead of queueing. That
        is the point: while Plato is throttling us, the cheapest thing we can do
        is stop calling it at all and let its window reset.
        """
        if not self._interval:
            return
        deadline = time.monotonic() + max_wait_s
        while True:
            with self._lock:
                now = time.monotonic()
                if now < self._penalty_until:
                    wait = self._penalty_until - now
                    reason = "cooling down after a 429"
                else:
                    # Defensive clamp. Nothing sets _updated into the future
                    # today, but if anything ever does, a negative elapsed would
                    # silently *remove* tokens and never recover.
                    elapsed = max(0.0, now - self._updated)
                    self._tokens = min(self._burst,
                                       self._tokens + elapsed / self._interval)
                    self._updated = now
                    if self._tokens >= 1.0:
                        self._tokens -= 1.0
                        return
                    wait = (1.0 - self._tokens) * self._interval
                    reason = f"budget exhausted at {60.0 / self._interval:.0f} req/min"
            if now + wait > deadline:
                raise PlatoError(
                    f"Plato rate limit — {reason}; would need {wait:.0f}s, "
                    f"waited {max_wait_s:.0f}s")
            time.sleep(min(wait, max(0.0, deadline - now)))

    def penalise(self, cooldown_s: float) -> None:
        """Plato returned 429: drain the bucket and hold every caller off for
        `cooldown_s`, not just the one that got throttled.

        This is the circuit breaker. Retrying into a 429 is what keeps the
        budget pinned — each failing request costs four Plato calls, so a burst
        of visitors during a throttle keeps us throttled indefinitely.
        """
        with self._lock:
            now = time.monotonic()
            self._tokens = 0.0
            self._updated = now
            self._penalty_until = max(self._penalty_until, now + cooldown_s)


# One bucket for the whole process — see _RateLimiter on why that is enough.
_limiter = _RateLimiter(PLATO_RATE_PER_MIN, PLATO_RATE_BURST)


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

    def get(self, path: str, params: dict | None = None, _retries: int = 3):
        """GET with exponential backoff on 429/5xx (Plato caps at 20 req/min).

        Backoff is capped low (<=8s/step) because this sits on the interactive
        availability path — a long 60s backoff made the booking form hang for
        minutes when a burst of date changes tripped the rate limit. The frontend
        debounces + the per-day appointment cache keep the request rate down."""
        delay = 1.0
        for attempt in range(_retries + 1):
            _limiter.acquire(PLATO_RATE_MAX_WAIT_S)
            r = self.s.get(self._url(path), params=params, timeout=self.timeout)
            if r.status_code == 429:
                # Tell the whole process to stand down, then let the retry (if
                # any) fail fast against the cooldown rather than calling Plato.
                _limiter.penalise(PLATO_429_COOLDOWN_S)
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
        return out

    def post(self, path: str, payload: dict):
        _limiter.acquire(PLATO_RATE_MAX_WAIT_S)
        r = self.s.post(self._url(path), json=payload, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def delete(self, path: str):
        _limiter.acquire(PLATO_RATE_MAX_WAIT_S)
        r = self.s.delete(self._url(path), timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    # --- domain helpers ---
    def appointments(self, start_date: str, end_date: str) -> list[dict]:
        """Every appointment with starttime in [start_date, end_date] (YYYY-MM-DD),
        across all pages. Cached per range for APPTS_TTL_S (the availability hot
        path re-reads the same day repeatedly). Includes regular appointments and
        leave/unavailable entries."""
        key = (start_date, end_date)
        # A single day feeds the slot list a visitor is about to book against,
        # so it stays short-lived; a multi-day range only feeds calendar
        # shading and is the expensive one to re-page. See APPTS_RANGE_TTL_S.
        ttl = APPTS_TTL_S if start_date == end_date else APPTS_RANGE_TTL_S
        now = time.monotonic()
        hit = self._appts_cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
        rows = self.get_all("appointment",
                            {"start_date": start_date, "end_date": end_date})

        # Mark leave/vacation appointments by title pattern, and ensure all appointments
        # have proper ISO datetime strings (not just dates). Holiday blocks are regular
        # appointments on the clinician's own calendar, identified by title (from real
        # Plato data analysis; see commit f56b63e). This approach doesn't rely on a
        # non-existent clinician_leave endpoint.
        for appointment in rows:
            title = appointment.get("title", "")
            if _is_leave_title(title):
                appointment["type"] = "leave"
                # Behind the debug flag: this fires for every leave entry on
                # every fetch, and left on it buries the WARNING lines you
                # actually need when the form is down.
                if _DIAG:
                    log.info("leave block: %s | start=%s | end=%s | color=%s | doctor=%s",
                             title, appointment.get("starttime"), appointment.get("endtime"),
                             appointment.get("color"), appointment.get("doctor"))

            # Convert date-only fields to ISO datetimes if needed
            starttime = appointment.get("starttime")
            if starttime and not ("T" in starttime or " " in starttime):
                # Date-only string (e.g., "2026-08-15"), convert to datetime at start of day
                appointment["starttime"] = f"{starttime}T00:00:00"

            endtime = appointment.get("endtime")
            if endtime and not ("T" in endtime or " " in endtime):
                # Date-only string (e.g., "2026-08-15"), convert to next day at start of day
                try:
                    end_dt = datetime.fromisoformat(endtime)
                    end_dt = end_dt + timedelta(days=1)
                    appointment["endtime"] = end_dt.isoformat()
                except (ValueError, TypeError):
                    appointment["endtime"] = f"{endtime}T23:59:59"

        self._appts_cache[key] = (now, rows)
        return rows

    def _serve_stale_config(self, now: float) -> dict:
        """Hand back the last good config and hold off re-fetching for
        CONFIG_RETRY_S. Deliberately does not refresh the copy's real age — it
        just moves the next retry out, so an expired TTL doesn't turn every
        request into another failing Plato call."""
        self._cfg_ts = now - CONFIG_TTL_S + CONFIG_RETRY_S
        assert self._cfg_cache is not None
        return self._cfg_cache

    def online_booking_config(self) -> dict:
        """The clinic's online-booking calendars + per-clinician rules.

        Cached for CONFIG_TTL_S — it barely changes, and re-fetching it on every
        availability lookup is a needless Plato round-trip on the hot path.

        Two guards, both learned from the 2026-09-01 outage:

        1. **The response is normalised, then shape-checked.** Plato silently
           changed this endpoint from returning the config object to returning a
           list of them (see `_normalise_booking_config`), which took /book down
           on 2026-09-01. Only something with `calendars` is ever cached — a
           shape we don't recognise is an error, never a poisoned cache entry.
        2. **A stale-but-good config beats no config.** The rules change maybe
           a few times a year, so when a refresh fails we keep serving the last
           good copy instead of failing the booking form. Only a cold cache
           (no good copy ever seen) propagates the error.
        """
        now = time.monotonic()
        if self._cfg_cache is not None and now - self._cfg_ts < CONFIG_TTL_S:
            return self._cfg_cache

        try:
            fresh = self.get("onlineapptbooking/list")
        except Exception as e:
            if self._cfg_cache is not None:
                log.warning("Plato config refresh failed (%s) — serving the "
                            "last good copy, %.0fs old", e, now - self._cfg_ts)
                return self._serve_stale_config(now)
            raise

        cfg = _normalise_booking_config(fresh)
        if cfg is None:
            got = type(fresh).__name__
            if self._cfg_cache is not None:
                log.warning("Plato returned a malformed booking config (%s, not a "
                            "dict with 'calendars') — serving the last good copy, "
                            "%.0fs old", got, now - self._cfg_ts)
                return self._serve_stale_config(now)
            raise PlatoError(
                f"Plato returned a malformed booking config ({got}, expected a dict "
                "with 'calendars' or a list of them); refusing to cache it")

        self._cfg_cache = cfg
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
