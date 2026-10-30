"""
goji-booking — the public booking backend for the website /book flow.

Runs on Cloud Run as its own service (like goji-links), single instance /
single gunicorn worker so the per-clinician locks in booking.py are
authoritative. Holds the Plato key server-side; the static site calls it via
CORS. Endpoints:
  GET  /api/availability?service=&date=&clinician=&home=  -> free 30-min slots
  GET  /api/availability-summary?service=&month=&...      -> dates with any slot
  POST /api/book                                          -> create the booking
  POST /api/track                                         -> funnel event (fire-and-forget)
  POST /internal/refresh-snapshot                         -> re-page Plato (Cloud Scheduler, 5 min)
  GET  /healthcheck
"""
from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from datetime import date, datetime, timedelta, timezone

from flask import Flask, jsonify, request

from .availability import SGT, derive_availability, derive_available_days
from .booking import BookingError, create_booking
from .config import CLINICIANS, MAX_ADVANCE_DAYS, SERVICES
from .plato import PlatoBusy, PlatoClient, PlatoError, PlatoThrottled
from . import mailer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("goji-booking")

app = Flask(__name__)

CORS_ORIGIN = os.environ.get("CORS_ORIGIN", "https://www.gojiphysio.com")
PROJECT = os.environ.get("GCP_PROJECT", "goji-bi")
FUNNEL_TABLE = f"{PROJECT}.marts.booking_funnel_events"
WEB_EVENT_TABLE = f"{PROJECT}.marts.web_session_events"
# Progress stages plus "stuck" events that make silent drop-off visible:
#   availability_empty — picked a date with no free slots (server-side)
#   validation_error   — bad phone/email on the form (client-side)
#   book_error         — submit failed (server-side; `detail` = the reason code)
# and step-2 behaviour events so the clinician/date/time drop-off is legible:
#   date_picked        — clicked a calendar date (`detail` = the date)
#   availability_error — the times fetch failed in the browser (`detail` = date)
#   clinician_changed  — switched the preferred-clinician option (`detail` = id)
VALID_STAGES = {"page_view", "service_selected", "time_selected", "details",
                "submitted", "confirmed",
                "availability_empty", "availability_error", "validation_error",
                "book_error", "date_picked", "clinician_changed"}
# Attribution fields the browser may attach (first-touch, from the landing
# beacon) so a booking event can be traced to how the visitor arrived.
ATTRIB_KEYS = ("visitor_id", "utm_source", "utm_campaign", "gclid", "go_click_id")

_plato: PlatoClient | None = None
_bq = None
_init_lock = threading.Lock()

# Short-lived availability cache: repeated lookups for the same
# (service, date, clinician, home) — a user clicking around dates/times, or
# several visitors on the same day — reuse one derivation instead of hitting
# Plato each time. Safe because create_booking re-derives under a lock before
# writing, so a slot that fills within the TTL is still caught at submit.
AVAIL_TTL_S = float(os.environ.get("AVAIL_CACHE_TTL", "45"))
_avail_cache: dict[tuple, tuple[float, dict]] = {}
_avail_cache_lock = threading.Lock()
# If Plato fails on a cache miss, an older answer beats an error screen: a day's
# slots up to this old are served (the submit re-checks fresh, so the worst case
# is "that time is no longer available"). Month shading has no such cap — it
# only paints the calendar.
AVAIL_STALE_MAX_S = float(os.environ.get("AVAIL_STALE_MAX", "1800"))

# Month-summary cache (which dates have ANY slot — the calendar shading on the
# website). Cached longer than per-day availability: it only paints the
# calendar, and the visitor's actual date pick (and the submit, under a lock)
# still checks day-level truth fresh.
SUMMARY_TTL_S = float(os.environ.get("AVAIL_SUMMARY_CACHE_TTL", "300"))
_summary_cache: dict[tuple, tuple[float, dict]] = {}

# The availability snapshot (see SNAPSHOT_MAX_AGE_S in plato.py). The refresh
# endpoint is unauthenticated on purpose — no secret to mint or rotate — so it
# throttles itself instead: however often it is hit, Plato is paged at most
# once per SNAPSHOT_MIN_INTERVAL_S, the same as the scheduler alone.
SNAPSHOT_MIN_INTERVAL_S = float(os.environ.get("SNAPSHOT_MIN_INTERVAL", "240"))
# The deep healthcheck fails once the snapshot is this old (the scheduler or
# the refresh is broken; the form has fallen back to live Plato reads)...
SNAPSHOT_ALERT_AGE_S = float(os.environ.get("SNAPSHOT_ALERT_AGE", "1200"))
# ...but not in the first minutes after a cold start, before the first tick.
SNAPSHOT_GRACE_S = float(os.environ.get("SNAPSHOT_GRACE", "600"))
_snapshot_lock = threading.Lock()
_snapshot_last_try = float("-inf")
_STARTED = time.monotonic()


def plato() -> PlatoClient:
    global _plato
    if _plato is None:
        with _init_lock:
            if _plato is None:
                _plato = PlatoClient()
    return _plato


def bq():
    global _bq
    if _bq is None:
        with _init_lock:
            if _bq is None:
                from google.cloud import bigquery
                _bq = bigquery.Client(project=PROJECT)
    return _bq


@app.after_request
def _cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = CORS_ORIGIN
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Max-Age"] = "86400"
    return resp


@app.route("/healthcheck")
def healthcheck():
    """Liveness only: is the container up. Deliberately does NOT touch Plato.

    This stayed a cheerful 200 through the whole 2026-09-01 outage while /book
    was unusable, which is why the uptime check watches /healthcheck/deep."""
    return "ok", 200


# Readiness cache: the deep check costs a Plato read, and Plato's budget is 20
# req/min for the entire clinic. One derivation per DEEP_TTL_S is plenty for a
# 5-minute uptime check, and it stops a bot hammering the URL from eating the
# booking form's budget.
DEEP_TTL_S = float(os.environ.get("DEEP_HEALTH_CACHE_TTL", "60"))
# How far ahead the check looks for a bookable date. Wide enough that a
# genuinely full stretch (holiday week) can't trip the alert on its own, but
# still a single Plato appointments fetch.
DEEP_HORIZON_DAYS = int(os.environ.get("DEEP_HEALTH_HORIZON_DAYS", "14"))
DEEP_SERVICE = os.environ.get("DEEP_HEALTH_SERVICE", "physiotherapy")
_deep_cache: tuple[float, dict, int] | None = None
_deep_lock = threading.Lock()


@app.route("/healthcheck/deep")
def healthcheck_deep():
    """Readiness: can a visitor actually get times on /book right now?

    Exercises the real failure surface end to end — Plato auth, the appointments
    fetch, the online-booking config (including the shape guard that the
    2026-09-01 cache-poisoning bug slipped past), and slot derivation — then
    asserts at least one bookable date exists in the next DEEP_HORIZON_DAYS.

    200 `{"ok": true, ...}`   — the booking form works.
    503 `{"ok": false, ...}`  — it does not; `reason` says which failure it is:
        `derivation_failed`   — Plato or our derivation threw (the 502 the
                                visitor sees as "We couldn't load times just now")
        `no_bookable_dates`   — it ran clean but returned an empty calendar
        `snapshot_stale`      — the 5-minute snapshot refresh has stopped, so
                                every click is back on live Plato reads

    Uses one range fetch, which the Plato client caches, and the whole answer is
    cached for DEEP_TTL_S. Public by design: the uptime check is unauthenticated
    and the payload is a date list, no patient data.
    """
    global _deep_cache
    nowm = time.monotonic()
    with _deep_lock:
        if _deep_cache and nowm - _deep_cache[0] < DEEP_TTL_S:
            return jsonify(_deep_cache[1]), _deep_cache[2]

    today = datetime.now(SGT).date()
    start = today + timedelta(days=1)  # lead time: Plato's min_days, no same-day
    end = min(today + timedelta(days=DEEP_HORIZON_DAYS),
              today + timedelta(days=MAX_ADVANCE_DAYS))
    started = time.monotonic()
    try:
        days = derive_available_days(plato(), DEEP_SERVICE, start, end)
    except PlatoBusy as e:
        # Plato's request budget is spent, not broken: the range is part-paged.
        # Paging an outage's worth of alerts out of a busy minute helps nobody;
        # real breakage (auth, shape, derivation) still raises something else.
        log.info("deep healthcheck: Plato busy (%s)", e)
        payload = {"ok": True, "busy": True, "service": DEEP_SERVICE,
                   "window": [start.isoformat(), end.isoformat()], "detail": str(e)}
        status = 200
    except Exception as e:
        log.error("deep healthcheck failed (%s %s..%s): %s",
                  DEEP_SERVICE, start, end, e, exc_info=True)
        payload = {"ok": False, "reason": "derivation_failed", "error": str(e),
                   "service": DEEP_SERVICE,
                   "window": [start.isoformat(), end.isoformat()]}
        status = 503
    else:
        ok = bool(days)
        if not ok:
            log.error("deep healthcheck: no bookable dates for %s in %s..%s",
                      DEEP_SERVICE, start, end)
        payload = {"ok": ok, "service": DEEP_SERVICE,
                   "window": [start.isoformat(), end.isoformat()],
                   "bookable_dates": len(days),
                   "first_available": days[0] if days else None,
                   "took_ms": int((time.monotonic() - started) * 1000)}
        if not ok:
            payload["reason"] = "no_bookable_dates"
        status = 200 if ok else 503

    age = plato().snapshot_age_s()
    payload["snapshot_age_s"] = None if age is None else int(age)
    if (status == 200 and time.monotonic() - _STARTED > SNAPSHOT_GRACE_S
            and (age is None or age > SNAPSHOT_ALERT_AGE_S)):
        log.error("deep healthcheck: availability snapshot is %s",
                  "missing" if age is None else f"{age:.0f}s old")
        payload.update(ok=False, reason="snapshot_stale")
        status = 503

    with _deep_lock:
        _deep_cache = (nowm, payload, status)
    return jsonify(payload), status


@app.route("/internal/refresh-snapshot", methods=["POST"])
def refresh_snapshot():
    """Re-page the bookable window into the availability snapshot.

    Called by Cloud Scheduler (`booking-snapshot-refresh`, every 5 min, off the
    ingest jobs' minutes). Also keeps the single instance warm, so the snapshot
    is almost never cold. 200 with stats when refreshed or skipped; 503 when
    Plato couldn't serve the window in time (the previous snapshot keeps serving
    until it ages out)."""
    global _snapshot_last_try
    if not _snapshot_lock.acquire(blocking=False):
        return jsonify({"ok": True, "skipped": "refresh in progress"})
    try:
        nowm = time.monotonic()
        if nowm - _snapshot_last_try < SNAPSHOT_MIN_INTERVAL_S:
            return jsonify({"ok": True, "skipped": "refreshed recently",
                            "age_s": plato().snapshot_age_s()})
        _snapshot_last_try = nowm
        today = datetime.now(SGT).date()
        start, end = today, today + timedelta(days=MAX_ADVANCE_DAYS)
        try:
            stats = plato().refresh_snapshot(start.isoformat(), end.isoformat())
        except PlatoError as e:  # PlatoBusy / PlatoThrottled / transport
            log.warning("snapshot refresh failed: %s", e)
            return jsonify({"ok": False, "error": str(e),
                            "age_s": plato().snapshot_age_s()}), 503
        # Answers derived from the old snapshot would outlive it otherwise.
        with _avail_cache_lock:
            _avail_cache.clear()
            _summary_cache.clear()
        log.info("snapshot refreshed: %s", stats)
        return jsonify({"ok": True, **stats})
    finally:
        _snapshot_lock.release()


@app.route("/api/availability")
def availability():
    service = request.args.get("service", "")
    if service not in SERVICES:
        return jsonify({"error": "unknown service"}), 400
    try:
        day = date.fromisoformat(request.args.get("date", ""))
    except ValueError:
        return jsonify({"error": "bad date"}), 400
    home = request.args.get("home", "") in ("1", "true", "yes")
    clinician = request.args.get("clinician") or None
    focus = request.args.get("focus") or None
    variant = request.args.get("variant") or None

    cache_key = (service, day.isoformat(), clinician or "", focus or "", variant or "", home)
    nowm = time.monotonic()
    with _avail_cache_lock:
        hit = _avail_cache.get(cache_key)
        if hit and nowm - hit[0] < AVAIL_TTL_S:
            return jsonify(hit[1])

    try:
        avail = derive_availability(plato(), service, day,
                                    clinician_id=clinician, focus=focus, variant=variant, home=home)
    except Exception as e:  # Plato hiccup — serve the last answer if we have one
        with _avail_cache_lock:
            stale = _avail_cache.get(cache_key)
        if stale and nowm - stale[0] < AVAIL_STALE_MAX_S:
            log.warning("availability failed (%s %s): %s — serving a %.0fs-old answer",
                        service, day, e, nowm - stale[0])
            return jsonify(stale[1])
        if isinstance(e, PlatoThrottled):
            # Out of Plato budget for a few seconds (the key is shared with the
            # ingestion jobs). Not an outage: tell the browser when to ask again
            # so it waits it out instead of showing "couldn't load times".
            retry = max(2, min(int(e.retry_after_s) + 1, 20))
            log.info("availability throttled (%s %s): %s", service, day, e)
            return jsonify({"error": "loading", "times": [], "retry_after": retry}), 503
        log.warning("availability failed (%s %s): %s", service, day, e, exc_info=True)
        return jsonify({"error": "unavailable", "times": []}), 502
    times = sorted({t for slots in avail.values() for t in slots})
    # A date with zero free slots is a silent drop-off point: the visitor picked
    # a day and hit a dead end. Log it (server-side, so it's authoritative) with
    # the service+date as detail. session_id comes from the query so it ties into
    # that visitor's funnel; skipped if the browser didn't send one.
    if not times:
        _track_async("availability_empty", request.args.get("session_id"),
                     service, request.headers.get("User-Agent"),
                     request.headers.get("Referer"),
                     detail=f"{service}:{day.isoformat()}")
    payload = {
        "date": day.isoformat(),
        "times": times,
        "by_clinician": avail,
        "clinicians": [{"id": cid, "name": CLINICIANS[cid]["name"]} for cid in avail],
    }
    with _avail_cache_lock:
        _avail_cache[cache_key] = (nowm, payload)
    return jsonify(payload)


@app.route("/api/availability-summary")
def availability_summary():
    """Which dates in a calendar month have at least one bookable slot.

    Feeds the website's calendar shading and its first-free-date auto-pick, so
    a visitor never clicks through empty dates hunting for availability. One
    derivation covers the month (a single Plato appointments fetch)."""
    service = request.args.get("service", "")
    if service not in SERVICES:
        return jsonify({"error": "unknown service"}), 400
    month_s = request.args.get("month", "")
    try:
        month_start = datetime.strptime(month_s, "%Y-%m").date()
    except ValueError:
        return jsonify({"error": "bad month"}), 400
    home = request.args.get("home", "") in ("1", "true", "yes")
    clinician = request.args.get("clinician") or None
    focus = request.args.get("focus") or None
    variant = request.args.get("variant") or None

    # Clamp to [today, today + MAX_ADVANCE_DAYS] (SGT — the clinic's clock, not
    # the server's UTC). Rule-level min/max_days still apply per day inside the
    # derivation; this just bounds the work to the bookable window.
    today = datetime.now(SGT).date()
    next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
    start = max(month_start, today)
    end = min(next_month - timedelta(days=1), today + timedelta(days=MAX_ADVANCE_DAYS))
    if start > end:
        return jsonify({"month": month_s, "available": []})

    cache_key = (service, month_s, clinician or "", focus or "", variant or "", home)
    nowm = time.monotonic()
    with _avail_cache_lock:
        hit = _summary_cache.get(cache_key)
        if hit and nowm - hit[0] < SUMMARY_TTL_S:
            return jsonify(hit[1])

    try:
        days = derive_available_days(plato(), service, start, end,
                                     clinician_id=clinician, focus=focus, variant=variant, home=home)
    except PlatoBusy as e:
        # Not a failure: the month is only part-paged because Plato's request
        # budget is 20/min and a month is ~25 pages. Progress is kept, so the
        # browser retrying in a few seconds resumes it. Serve the last shading
        # we had if there is one.
        with _avail_cache_lock:
            stale = _summary_cache.get(cache_key)
        if stale:
            return jsonify(stale[1])
        log.info("availability summary still loading (%s %s): %s", service, month_s, e)
        return jsonify({"error": "loading", "available": []}), 503
    except Exception as e:  # Plato hiccup — the calendar degrades to unshaded
        with _avail_cache_lock:
            stale = _summary_cache.get(cache_key)
        if stale:
            log.warning("availability summary failed (%s %s): %s — serving a %.0fs-old answer",
                        service, month_s, e, nowm - stale[0])
            return jsonify(stale[1])
        log.warning("availability summary failed (%s %s): %s", service, month_s, e,
                    exc_info=True)
        return jsonify({"error": "unavailable", "available": []}), 502
    payload = {"month": month_s, "available": days}
    with _avail_cache_lock:
        _summary_cache[cache_key] = (nowm, payload)
    return jsonify(payload)


@app.route("/api/book", methods=["POST", "OPTIONS"])
def book():
    if request.method == "OPTIONS":
        return "", 204
    draft = request.get_json(silent=True) or {}
    ua, ref = request.headers.get("User-Agent"), request.headers.get("Referer")
    attribution = draft.get("attribution") or {}
    try:
        result = create_booking(plato(), draft)
    except BookingError as e:
        status = 409 if e.code == "slot_taken" else 400
        # A failed submit is where a ready-to-book visitor gets stuck. Record it
        # with the reason code so "book_error" drop-off is visible and typed.
        _track_async("book_error", draft.get("session_id"), draft.get("service"),
                     ua, ref, detail=(e.code or "error"), attribution=attribution)
        return jsonify({"ok": False, "error": str(e), "code": e.code}), status
    except Exception:
        log.exception("booking failed")
        _track_async("book_error", draft.get("session_id"), draft.get("service"),
                     ua, ref, detail="plato_error", attribution=attribution)
        return jsonify({"ok": False,
                        "error": "Something went wrong. Please try again or message us."}), 502
    mailer.send_admin_booking_email(result, draft)     # best-effort
    mailer.send_customer_booking_email(result, draft)  # best-effort
    _track_async("confirmed", draft.get("session_id"), draft.get("service"),
                 ua, ref, attribution=attribution)
    return jsonify({"ok": True, "reference": result["reference"]})


@app.route("/api/track", methods=["POST", "OPTIONS"])
def track():
    if request.method == "OPTIONS":
        return "", 204
    data = request.get_json(silent=True) or {}
    _track_async(data.get("stage"), data.get("session_id"), data.get("service"),
                 request.headers.get("User-Agent"), request.headers.get("Referer"),
                 detail=data.get("detail"), attribution=data.get("attribution"))
    return "", 204


@app.route("/api/web-event", methods=["POST", "OPTIONS"])
def web_event():
    """Landing beacon from the site (BaseLayout): one row per session_start /
    page_view capturing arrival attribution, plus a page_engagement row on exit
    carrying dwell_ms / scroll_pct. Fire-and-forget; always 204."""
    if request.method == "OPTIONS":
        return "", 204
    data = request.get_json(silent=True) or {}
    _record_web_event_async(data, request.headers.get("User-Agent"),
                            request.headers.get("Referer"))
    return "", 204


def _track_async(stage, session_id, service, user_agent, referer,
                 detail=None, attribution=None) -> None:
    """Fire-and-forget funnel event (mirrors the dashboard's _record_link_click).

    `detail` carries context for stuck events (a book_error code, or the date
    with no availability). `attribution` is the first-touch blob from the landing
    beacon (visitor_id / utm_* / gclid / go_click_id) so a confirmed booking can
    be traced back to how the visitor arrived; only known keys are copied."""
    if not stage or stage not in VALID_STAGES or not session_id:
        return
    row = {
        "event_id": str(uuid.uuid4()),
        "session_id": str(session_id)[:64],
        "stage": stage,
        "service": (service or None),
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "user_agent": ((user_agent or "")[:512] or None),
        "referer": ((referer or "")[:512] or None),
        "detail": ((str(detail)[:256]) if detail else None),
    }
    if attribution:
        for k in ATTRIB_KEYS:
            v = attribution.get(k)
            if v:
                row[k] = str(v)[:256]

    def _insert():
        try:
            errors = bq().insert_rows_json(FUNNEL_TABLE, [row])
            if errors:
                log.warning("funnel insert returned errors: %s", errors)
        except Exception as e:
            log.warning("funnel event not recorded (stage=%s): %s", stage, e)

    threading.Thread(target=_insert, daemon=True).start()


def web_event_row(data, user_agent, referer) -> dict:
    """Build the marts.web_session_events row for a beacon payload.

    Pure (bar the uuid/clock) so the coercion rules are unit-testable: the
    endpoint is public and unauthenticated, so every value here is untrusted.

    `referer` must be the visitor's `document.referrer` (the body's `referrer`),
    never the HTTP Referer header: the beacon is a cross-origin fetch from our
    own page, so the header is always gojiphysio.com and every arrival looked
    like a self-referral (Jul–Oct 2026). An empty body value is a real Direct.
    The header is only a fallback for a payload with no `referrer` key at all.
    """
    body_ref = data.get("referrer")
    ref = body_ref if body_ref is not None else referer
    row = {
        "event_id": str(uuid.uuid4()),
        "event_type": str(data.get("event_type") or "page_view")[:32],
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "user_agent": ((user_agent or "")[:512] or None),
        "referer": ((str(ref or ""))[:512] or None),
    }
    # Copy known string fields when present (keeps the row tidy; unknown keys
    # from a future beacon version are simply ignored).
    for k in ("visitor_id", "session_id", "utm_source", "utm_medium",
              "utm_campaign", "utm_content", "utm_term", "gclid", "fbclid",
              "landing_path", "go_click_id"):
        v = data.get(k)
        if v:
            row[k] = str(v)[:512]
    # Engagement metrics (page_engagement rows). Coerced and clamped: a
    # malformed or hostile payload must not poison the column. Checked against
    # None rather than falsiness — scroll_pct = 0 (landed, never scrolled) is
    # exactly the signal we're here to measure.
    for k, hi in (("dwell_ms", 86_400_000), ("scroll_pct", 100)):
        v = data.get(k)
        if v is None:
            continue
        try:
            row[k] = max(0, min(int(v), hi))
        except (TypeError, ValueError):
            pass  # ignore junk; the rest of the row is still worth writing
    return row


def _record_web_event_async(data, user_agent, referer) -> None:
    """Fire-and-forget landing-beacon event → marts.web_session_events. This is
    the top of the funnel: how the visitor arrived (utm_*, gclid, referer,
    landing_path) plus the go-link click_id passthrough (cid) for the exact
    origin→booking join. A page_engagement event additionally carries dwell_ms /
    scroll_pct, which separate a bounce from a read. Best-effort; never blocks
    the page."""
    row = web_event_row(data, user_agent, referer)
    event_type = row["event_type"]

    def _insert():
        try:
            errors = bq().insert_rows_json(WEB_EVENT_TABLE, [row])
            if errors:
                log.warning("web event insert returned errors: %s", errors)
        except Exception as e:
            log.warning("web event not recorded (%s): %s", event_type, e)

    threading.Thread(target=_insert, daemon=True).start()
