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
VALID_STAGES = {"page_view", "service_selected", "time_selected", "details",
                "submitted", "confirmed"}

_plato: PlatoClient | None = None
_bq = None
_init_lock = threading.Lock()


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
    try:
        avail = derive_availability(plato(), service, day,
                                    clinician_id=clinician, home=home)
    except Exception as e:  # Plato hiccup — degrade to no slots, don't 500 loudly
        log.warning("availability failed (%s %s): %s", service, day, e)
        return jsonify({"error": "unavailable", "times": []}), 502
    times = sorted({t for slots in avail.values() for t in slots})
    return jsonify({
        "date": day.isoformat(),
        "times": times,
        "by_clinician": avail,
        "clinicians": [{"id": cid, "name": CLINICIANS[cid]["name"]} for cid in avail],
    })


@app.route("/api/book", methods=["POST", "OPTIONS"])
def book():
    if request.method == "OPTIONS":
        return "", 204
    draft = request.get_json(silent=True) or {}
    try:
        result = create_booking(plato(), draft)
    except BookingError as e:
        status = 409 if e.code == "slot_taken" else 400
        return jsonify({"ok": False, "error": str(e), "code": e.code}), status
    except Exception:
        log.exception("booking failed")
        return jsonify({"ok": False,
                        "error": "Something went wrong. Please try again or message us."}), 502
    mailer.send_admin_booking_email(result, draft)     # best-effort
    mailer.send_customer_booking_email(result, draft)  # best-effort
    _track_async("confirmed", draft.get("session_id"), draft.get("service"),
                 request.headers.get("User-Agent"), request.headers.get("Referer"))
    return jsonify({"ok": True, "reference": result["reference"]})


@app.route("/api/track", methods=["POST", "OPTIONS"])
def track():
    if request.method == "OPTIONS":
        return "", 204
    data = request.get_json(silent=True) or {}
    _track_async(data.get("stage"), data.get("session_id"), data.get("service"),
                 request.headers.get("User-Agent"), request.headers.get("Referer"))
    return "", 204


def _track_async(stage, session_id, service, user_agent, referer) -> None:
    """Fire-and-forget funnel event (mirrors the dashboard's _record_link_click)."""
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
    }

    def _insert():
        try:
            errors = bq().insert_rows_json(FUNNEL_TABLE, [row])
            if errors:
                log.warning("funnel insert returned errors: %s", errors)
        except Exception as e:
            log.warning("funnel event not recorded (stage=%s): %s", stage, e)

    threading.Thread(target=_insert, daemon=True).start()
