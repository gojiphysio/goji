"""
goji-booking — the public booking backend for the website /book flow.

Runs on Cloud Run as its own service (like goji-links), single instance /
single gunicorn worker so the per-clinician locks in booking.py are
authoritative. Holds the Plato key server-side; the static site calls it via
CORS. Endpoints:
  GET  /api/availability?service=&date=&clinician=&home=  -> free 30-min slots
  POST /api/book                                          -> create the booking
  POST /api/track                                         -> funnel event (fire-and-forget)
  GET  /healthcheck
"""
from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from datetime import date, datetime, timezone

from flask import Flask, jsonify, request

from .availability import derive_availability
from .booking import BookingError, create_booking
from .config import CLINICIANS, SERVICES
from .plato import PlatoClient
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
VALID_STAGES = {"page_view", "service_selected", "time_selected", "details",
                "submitted", "confirmed",
                "availability_empty", "validation_error", "book_error"}
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


def plato() -> PlatoClient:
    global _plato
    if _plato is None:
        with _init_lock:
            if _plato is None:
                _plato = PlatoClient()
                _warm_broad(_plato)  # prime the recurrence sweep off the hot path
    return _plato


def _warm_broad(client: PlatoClient) -> None:
    """Kick off the background recurrence/long-block sweep so it's warm before the
    first availability request (which otherwise sees an empty overlay). Best-effort."""
    from datetime import date as _date, timedelta
    from .config import MAX_ADVANCE_DAYS, RECUR_LOOKBACK_DAYS
    try:
        today = _date.today()
        client.warm_broad(
            (today - timedelta(days=RECUR_LOOKBACK_DAYS)).isoformat(),
            (today + timedelta(days=MAX_ADVANCE_DAYS)).isoformat(),
        )
    except Exception:
        pass  # the first request will trigger the refresh anyway


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
    return "ok", 200


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

    cache_key = (service, day.isoformat(), clinician or "", focus or "", home)
    nowm = time.monotonic()
    with _avail_cache_lock:
        hit = _avail_cache.get(cache_key)
        if hit and nowm - hit[0] < AVAIL_TTL_S:
            return jsonify(hit[1])

    try:
        avail = derive_availability(plato(), service, day,
                                    clinician_id=clinician, focus=focus, home=home)
    except Exception as e:  # Plato hiccup — degrade to no slots, don't 500 loudly
        log.warning("availability failed (%s %s): %s", service, day, e)
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
    page_view capturing arrival attribution. Fire-and-forget; always 204."""
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


def _record_web_event_async(data, user_agent, referer) -> None:
    """Fire-and-forget landing-beacon event → marts.web_session_events. This is
    the top of the funnel: how the visitor arrived (utm_*, gclid, referer,
    landing_path) plus the go-link click_id passthrough (cid) for the exact
    origin→booking join. Best-effort; never blocks the page."""
    event_type = (data.get("event_type") or "page_view")
    row = {
        "event_id": str(uuid.uuid4()),
        "event_type": str(event_type)[:32],
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "user_agent": ((user_agent or "")[:512] or None),
        "referer": ((referer or data.get("referrer") or "")[:512] or None),
    }
    # Copy known string fields when present (keeps the row tidy; unknown keys
    # from a future beacon version are simply ignored).
    for k in ("visitor_id", "session_id", "utm_source", "utm_medium",
              "utm_campaign", "utm_content", "utm_term", "gclid", "fbclid",
              "landing_path", "go_click_id"):
        v = data.get(k)
        if v:
            row[k] = str(v)[:512]

    def _insert():
        try:
            errors = bq().insert_rows_json(WEB_EVENT_TABLE, [row])
            if errors:
                log.warning("web event insert returned errors: %s", errors)
        except Exception as e:
            log.warning("web event not recorded (%s): %s", event_type, e)

    threading.Thread(target=_insert, daemon=True).start()
