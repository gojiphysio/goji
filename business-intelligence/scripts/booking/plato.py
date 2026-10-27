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
from collections import deque
from datetime import datetime, timedelta

import requests

log = logging.getLogger("booking.plato")
# Same switch availability.py uses, so one env var turns on the whole
# slot-derivation trace (see DIAGNOSIS.md).
_DIAG = os.environ.get("BOOKING_AVAILABILITY_DEBUG", "").lower() in ("1", "true", "yes")

BASE = "https://clinic.platomedical.com/api"
# A hung Plato read must fail fast: get() retries up to 4x and gunicorn kills the
# worker at 60s, so 30s per attempt could turn one slow call into a dead request.
TIMEOUT_S = 12
# Plato throttles at 20 requests/min per API key. We pace ourselves to just
# under that (see _RateLimiter) rather than discovering the cap via 429s: a 429
# costs 7s of retry backoff and then surfaces as a 502 on the booking form.
PLATO_RATE_PER_MIN = int(float(os.environ.get("PLATO_RATE_PER_MIN", "18")))
# Of that budget, this many requests per minute are held back from bulk work
# (paging a whole month for the calendar shading). A date click or a booking
# write is interactive and must never queue behind a 25-page cosmetic crawl.
PLATO_BULK_RESERVE = int(float(os.environ.get("PLATO_BULK_RESERVE", "5")))
# How long one bulk (month) request may spend paging before it hands back what
# it has and reports "still loading". Progress is kept (see appointments()), so
# the caller retries and resumes instead of one request hanging for a minute.
PLATO_BULK_BUDGET_S = float(os.environ.get("PLATO_BULK_BUDGET", "8"))
# How long a half-paged month is worth resuming. Past this the pages are too old
# to splice onto fresh ones, so we start the month over.
PLATO_PARTIAL_TTL_S = float(os.environ.get("PLATO_PARTIAL_TTL", "180"))
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
# A day inside an already-cached range is answered from that range, with no
# Plato call at all, as long as the range is this fresh. Deliberately much
# shorter than APPTS_RANGE_TTL_S: the day list is what the visitor books from.
# (create_booking always passes fresh=True and never takes this shortcut.)
DAY_FROM_RANGE_MAX_AGE_S = float(os.environ.get("PLATO_DAY_FROM_RANGE_AGE", "90"))
# When a day's fetch fails (usually a 429 cooldown), a cached range up to this
# old still answers it rather than the form saying "couldn't load times". Safe
# because create_booking re-reads fresh under the clinician lock and returns
# slot_taken (409) if the stale view offered a time that has since gone.
DAY_STALE_MAX_AGE_S = float(os.environ.get("PLATO_DAY_STALE_AGE", "1800"))
# The 20 req/min cap is per API key, and the key is shared: the ingestion jobs
# (plato-appointments every 15 min, plato-invoices every 30 min) page Plato on
# the same key, outside this process's limiter. Every 429 episode Sep-Oct 2026
# landed at :02-:04 / :32-:34 past the hour, while those jobs were paging. So
# we also read Plato's own `x-ratelimit-remaining`: once it is down to the
# interactive reserve, bulk work stands down for this long and leaves what is
# left to date clicks and booking writes.
PLATO_SHARED_HOLD_S = float(os.environ.get("PLATO_SHARED_HOLD", "20"))


def _is_leave_title(title: str) -> bool:
    """Check if an appointment title indicates a leave/vacation/holiday block."""
    if not title:
        return False
    title_lower = title.lower()
    return any(keyword in title_lower for keyword in LEAVE_KEYWORDS)


class PlatoError(RuntimeError):
    pass


class PlatoThrottled(PlatoError):
    """No request budget right now (our window is full, or we are cooling down
    after a 429). Not an outage: `retry_after_s` says when asking again is
    worthwhile, so the endpoint can answer "still loading" instead of failing."""

    def __init__(self, msg: str, retry_after_s: float):
        super().__init__(msg)
        self.retry_after_s = retry_after_s


class PlatoBusy(PlatoError):
    """A bulk fetch ran out of its time budget before finishing. Not a failure:
    the pages fetched so far are kept and the next call resumes from them."""


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
    """Sliding-window limiter that keeps us under Plato's 20 req/min cap.

    Plato throttles per API key, so the budget is clinic-wide — every
    availability lookup, month summary and booking write draws on the same
    window. The service runs `--max-instances=1` (deploy-booking.yml), which is
    what makes a single in-process limiter authoritative, the same reason the
    per-clinician booking locks live in-process. Raise max-instances and this
    needs a shared store, exactly like those locks.

    A sliding window, not a token bucket: a bucket with a burst of B refilling at
    R/min lets B + R requests through in the first minute, which is *over* the
    cap whenever B + R > 20. That is how a cold month view (25 pages) used to
    draw a 429 on itself, trip the cooldown, and take every date click down with
    it. Here no 60s window ever holds more than `limit` requests.

    `bulk` callers (paging a month for calendar shading) may only use
    `limit - reserve` of the window, so the last `reserve` slots are always free
    for interactive calls — a date click or a booking write.
    """

    WINDOW_S = 60.0

    def __init__(self, limit_per_min: float, bulk_reserve: float = 0):
        self._limit = int(limit_per_min) if limit_per_min and limit_per_min > 0 else 0
        self._reserve = max(0, min(int(bulk_reserve), self._limit - 1))
        self._stamps: deque[float] = deque()
        self._penalty_until = 0.0
        self._bulk_hold_until = 0.0
        self._lock = threading.Lock()

    def acquire(self, max_wait_s: float, bulk: bool = False) -> None:
        """Take one slot in the window, sleeping until one is free. Raises
        PlatoError if the wait would exceed `max_wait_s` — the caller degrades
        to "no slots" rather than holding the request open.

        During a cooldown (see `penalise`) the wait is by definition longer than
        a slot refill, so callers give up immediately instead of queueing. That
        is the point: while Plato is throttling us, the cheapest thing we can do
        is stop calling it at all and let its window reset.
        """
        if not self._limit:
            return
        cap = self._limit - (self._reserve if bulk else 0)
        deadline = time.monotonic() + max_wait_s
        while True:
            with self._lock:
                now = time.monotonic()
                if now < self._penalty_until:
                    wait = self._penalty_until - now
                    reason = "cooling down after a 429"
                elif bulk and now < self._bulk_hold_until:
                    wait = self._bulk_hold_until - now
                    reason = "budget in use by another caller on this key"
                else:
                    while self._stamps and now - self._stamps[0] >= self.WINDOW_S:
                        self._stamps.popleft()
                    if len(self._stamps) < cap:
                        self._stamps.append(now)
                        return
                    # Free once enough of the oldest requests age out of the window.
                    wait = self._stamps[len(self._stamps) - cap] + self.WINDOW_S - now
                    reason = f"budget exhausted at {self._limit} req/min"
            if now + wait > deadline:
                raise PlatoThrottled(
                    f"Plato rate limit — {reason}; would need {wait:.0f}s, "
                    f"waited {max_wait_s:.0f}s", retry_after_s=wait)
            time.sleep(min(wait, max(0.0, deadline - now)))

    def observe(self, remaining) -> None:
        """Plato's `x-ratelimit-remaining` after a call. Our window only counts
        our own requests; this is the key-wide truth. At or below the reserve,
        hold bulk callers off so the budget that is left goes to interactive
        calls, instead of a month crawl drawing the 429 that stops everyone."""
        try:
            left = int(remaining)
        except (TypeError, ValueError):
            return
        if not self._limit or left > self._reserve:
            return
        with self._lock:
            self._bulk_hold_until = max(self._bulk_hold_until,
                                        time.monotonic() + PLATO_SHARED_HOLD_S)

    def penalise(self, cooldown_s: float) -> None:
        """Plato returned 429: hold every caller off for `cooldown_s`, not just
        the one that got throttled.

        This is the circuit breaker. Retrying into a 429 is what keeps the
        budget pinned — each failing request costs four Plato calls, so a burst
        of visitors during a throttle keeps us throttled indefinitely.
        """
        with self._lock:
            self._penalty_until = max(self._penalty_until,
                                      time.monotonic() + cooldown_s)


# One limiter for the whole process — see _RateLimiter on why that is enough.
_limiter = _RateLimiter(PLATO_RATE_PER_MIN, PLATO_BULK_RESERVE)


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
        # Half-paged bulk fetches: key -> (started_at, next_page, rows so far).
        self._partial: dict[tuple[str, str], tuple[float, int, list[dict]]] = {}
        self._key_locks: dict[tuple[str, str], threading.Lock] = {}
        self._key_locks_guard = threading.Lock()

    def _url(self, path: str) -> str:
        return f"{BASE}/{self.db}/{path.lstrip('/')}"

    def get(self, path: str, params: dict | None = None, _retries: int = 3,
            bulk: bool = False, max_wait_s: float | None = None):
        """GET with exponential backoff on 429/5xx (Plato caps at 20 req/min).

        Backoff is capped low (<=8s/step) because this sits on the interactive
        availability path — a long 60s backoff made the booking form hang for
        minutes when a burst of date changes tripped the rate limit. The frontend
        debounces + the per-day appointment cache keep the request rate down.

        `bulk` marks background-ish work that may only use the non-reserved part
        of the rate budget (see _RateLimiter); `max_wait_s` overrides how long it
        may queue for a slot."""
        delay = 1.0
        wait_s = PLATO_RATE_MAX_WAIT_S if max_wait_s is None else max_wait_s
        for attempt in range(_retries + 1):
            _limiter.acquire(wait_s, bulk=bulk)
            r = self.s.get(self._url(path), params=params, timeout=self.timeout)
            _limiter.observe(r.headers.get("x-ratelimit-remaining"))
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
    def appointments(self, start_date: str, end_date: str,
                     fresh: bool = False) -> list[dict]:
        """Every appointment with starttime in [start_date, end_date] (YYYY-MM-DD),
        across all pages. Includes regular appointments and leave/unavailable
        entries.

        Cached per range (APPTS_TTL_S for a day, APPTS_RANGE_TTL_S for a range).
        Three things keep the hot path off Plato's 20 req/min budget:

        * **A day is answered from a cached range** when one covers it and is
          under DAY_FROM_RANGE_MAX_AGE_S old — the calendar shading has usually
          just paged the month, so the date click costs zero requests.
        * **A multi-day range is paged in bulk mode**: it can't starve date
          clicks (reserved budget), and it stops after PLATO_BULK_BUDGET_S with
          the pages so far kept, raising PlatoBusy; the next call resumes.
        * **A failed refresh serves the last copy** rather than an error.

        `fresh=True` is for the booking re-check under the clinician lock: it
        skips the range shortcut and never serves stale. Writing a booking off a
        90-second-old read would defeat the lock.
        """
        key = (start_date, end_date)
        single = start_date == end_date
        ttl = APPTS_TTL_S if single else APPTS_RANGE_TTL_S
        hit = self._appts_cache.get(key)
        if hit and time.monotonic() - hit[0] < ttl:
            return hit[1]
        if single and not fresh:
            covered = self._day_from_range(start_date)
            if covered is not None:
                return covered

        with self._key_lock(key):
            # Another thread may have finished this very fetch while we queued.
            hit = self._appts_cache.get(key)
            if hit and time.monotonic() - hit[0] < ttl:
                return hit[1]
            try:
                rows = self._fetch_appointments(key, bulk=not single)
            except Exception as e:
                if hit and not fresh:
                    log.warning("Plato appointments refresh failed (%s) — serving the "
                                "last copy, %.0fs old", e, time.monotonic() - hit[0])
                    return hit[1]
                if single and not fresh:
                    covered = self._day_from_range(start_date, DAY_STALE_MAX_AGE_S)
                    if covered is not None:
                        log.warning("Plato day fetch failed (%s) — answering %s from "
                                    "an older cached range", e, start_date)
                        return covered
                raise
            self._appts_cache[key] = (time.monotonic(), rows)
            return rows

    def _key_lock(self, key: tuple[str, str]) -> threading.Lock:
        """One lock per range, so concurrent identical fetches (two visitors, or
        the summary and the deep healthcheck) share one crawl, not run two."""
        with self._key_locks_guard:
            return self._key_locks.setdefault(key, threading.Lock())

    def _day_from_range(self, day: str,
                        max_age_s: float = DAY_FROM_RANGE_MAX_AGE_S) -> list[dict] | None:
        """The rows `appointments(day, day)` would return, taken from a cached
        range under `max_age_s` old that covers `day` — or None if there isn't
        one. Same rule Plato applies to a day query: starttime falls on that day."""
        now = time.monotonic()
        for (s, e), (ts, rows) in list(self._appts_cache.items()):
            if s != e and s <= day <= e and now - ts < max_age_s:
                return [r for r in rows if str(r.get("starttime", ""))[:10] == day]
        return None

    def _fetch_appointments(self, key: tuple[str, str], bulk: bool) -> list[dict]:
        start_date, end_date = key
        params = {"start_date": start_date, "end_date": end_date}
        if not bulk:
            rows = self.get_all("appointment", params)
        else:
            rows = self._page_in_bulk(key, params)
        self._tidy_appointments(rows)
        return rows

    def _page_in_bulk(self, key: tuple[str, str], params: dict) -> list[dict]:
        """Page a long range using only the bulk share of the rate budget, for at
        most PLATO_BULK_BUDGET_S. Progress survives a PlatoBusy: the next call
        picks up at the next page, so a month Plato can only serve in ~2 minutes
        still completes, as a few short requests instead of one that hangs."""
        started = time.monotonic()
        began, page, rows = self._partial.get(key, (started, 1, []))
        if started - began > PLATO_PARTIAL_TTL_S:
            began, page, rows = started, 1, []
        while True:
            spent = time.monotonic() - started
            if spent >= PLATO_BULK_BUDGET_S and page > 1:
                raise PlatoBusy(f"month still loading ({len(rows)} rows, page {page})")
            try:
                batch = self.get("appointment", {**params, "current_page": page},
                                 bulk=True,
                                 max_wait_s=max(0.0, PLATO_BULK_BUDGET_S - spent))
            except PlatoError as e:  # out of budget, or cooling down after a 429
                raise PlatoBusy(str(e)) from e
            got = batch if isinstance(batch, list) else batch.get("data", [])
            if not got:
                break
            rows.extend(got)
            page += 1
            self._partial[key] = (began, page, rows)  # keep progress across a timeout
            if len(got) < 20:  # last (partial) page
                break
        self._partial.pop(key, None)
        return rows

    @staticmethod
    def _tidy_appointments(rows: list[dict]) -> None:
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
        self._partial.clear()
        return r

    def delete_appointment(self, appointment_id: str) -> dict:
        r = self.delete(f"appointment/{appointment_id}")
        self._appts_cache.clear()
        self._partial.clear()
        return r
