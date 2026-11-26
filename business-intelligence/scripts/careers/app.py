"""
goji-careers — the public job-application backend for the website's /careers.

Own Cloud Run service (like goji-booking), single instance so the in-process
locks in pipeline.py are authoritative. Holds the only credentials that can
write the recruitment folder; the browser never sees them.

  POST /api/apply   multipart form (fields + `cv` file) -> {ok, reference}
  GET  /healthcheck liveness only

Deliberately absent: any endpoint that reads, lists or edits applications.
Reviewing happens in Drive/Sheets, behind Google sign-in.

Order of checks on /api/apply, cheapest first: origin -> size cap (Flask) ->
per-IP attempt limit -> bot check (honeypot, fill time, Turnstile) -> field
validation -> role is open -> CV safety checks -> per-email daily limit ->
store (pipeline). Only a fully stored application returns ok:true.

CSRF: there are no cookies or other ambient credentials, so a forged
cross-site POST gains nothing; we still refuse any Origin outside the
allowlist. Responses never echo applicant data.
"""
from __future__ import annotations

import logging
import os
import threading
import time

import requests
from flask import Flask, jsonify, request
from werkzeug.exceptions import RequestEntityTooLarge

from . import config, vacancies
from .filecheck import FileRejected, check_cv
from .google_store import GoogleStore, StoreError
from .pipeline import StorageFailed, submit
from .validation import parse_application

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("goji-careers")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = config.MAX_REQUEST_BYTES

TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"

_store: GoogleStore | None = None
_store_lock = threading.Lock()


def store() -> GoogleStore:
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = GoogleStore()
    return _store


def _err(code: str, message: str, status: int, **extra):
    return jsonify({"ok": False, "code": code, "error": message, **extra}), status


def _origin_ok() -> bool:
    return request.headers.get("Origin", "") in config.ALLOWED_ORIGINS


@app.after_request
def _headers(resp):
    origin = request.headers.get("Origin", "")
    if origin in config.ALLOWED_ORIGINS:
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Vary"] = "Origin"
        resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        resp.headers["Access-Control-Max-Age"] = "86400"
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


@app.errorhandler(RequestEntityTooLarge)
def _too_large(_e):
    return _err("too_large", "Your CV must be 10 MB or smaller.", 413,
                fields={"cv": "Your CV must be 10 MB or smaller."})


@app.route("/healthcheck")
def healthcheck():
    return "ok", 200


# ---- abuse limits (in-memory; --max-instances=1) ----------------------------
_hits: dict[str, list[float]] = {}
_hits_lock = threading.Lock()


def _client_ip() -> str:
    """Cloud Run appends the real client address as the LAST X-Forwarded-For
    entry; anything before it is caller-supplied (same rule as goji-booking)."""
    xff = request.headers.get("X-Forwarded-For", "")
    return (xff.split(",")[-1].strip() if xff else "") or (request.remote_addr or "?")


def _count(key: str, window_s: float) -> int:
    now = time.monotonic()
    with _hits_lock:
        ts = [t for t in _hits.get(key, []) if now - t < window_s]
        if ts:
            _hits[key] = ts
        else:
            _hits.pop(key, None)
        return len(ts)


def _hit(key: str) -> None:
    with _hits_lock:
        _hits.setdefault(key, []).append(time.monotonic())


def _turnstile_ok(token: str, ip: str) -> bool:
    """Same policy as goji-booking: if Cloudflare can't be reached, let it
    through (an outage there must not close the form; the limits still apply)."""
    try:
        r = requests.post(TURNSTILE_VERIFY_URL, timeout=5, data={
            "secret": config_turnstile_secret(), "response": token, "remoteip": ip})
        body = r.json()
    except Exception as e:
        log.warning("turnstile verify unreachable, allowing: %s", type(e).__name__)
        return True
    return bool(body.get("success"))


def config_turnstile_secret() -> str:
    """Read per call so tests (and a secret rotation) need no restart."""
    return os.environ.get("TURNSTILE_SECRET", "").strip()


def _bot_reason(form, ip: str) -> str | None:
    if str(form.get("company_url") or "").strip():
        return "honeypot"
    elapsed = str(form.get("elapsed_ms") or "").strip()
    if elapsed.isdigit() and int(elapsed) < config.MIN_FILL_MS:
        return "too_fast"
    if config_turnstile_secret():
        token = str(form.get("turnstile_token") or "").strip()
        if not token:
            return "captcha_missing"
        if not _turnstile_ok(token[:2048], ip):
            return "captcha_failed"
    return None


BOT_MSG = ("We couldn't verify this submission. Please try again, or email your "
           "CV to hello@gojiphysio.com.")
STORE_MSG = ("We couldn't save your application just now. Nothing has been lost on "
             "your side: please try again in a minute. If it keeps happening, email "
             "your CV to hello@gojiphysio.com.")


@app.route("/api/apply", methods=["POST", "OPTIONS"])
def apply():
    if request.method == "OPTIONS":
        return ("", 204) if _origin_ok() else ("", 403)
    if not _origin_ok():
        return _err("forbidden", "Forbidden.", 403)

    ip = _client_ip()
    if _count(f"ip:{ip}", 3600) >= config.ATTEMPTS_PER_IP_HOUR:
        return _err("rate_limited", "Too many attempts. Please try again later, or "
                    "email your CV to hello@gojiphysio.com.", 429)
    _hit(f"ip:{ip}")

    form = request.form
    bot = _bot_reason(form, ip)
    if bot:
        log.warning("application refused by bot check (%s)", bot)
        return _err("bot_check", BOT_MSG, 400)

    job_id = str(form.get("job_id") or "").strip()[:80]
    vacancy, why = vacancies.lookup(job_id)
    if vacancy is None:
        if why == "closed":
            return _err("closed", "Applications for this role have closed. You're "
                        "welcome to send us an expression of interest instead.", 410)
        if why == "unavailable":
            return _err("unavailable", STORE_MSG, 503)
        return _err("unknown_role", "This role isn't open for applications.", 400)

    data, errors = parse_application(form, vacancy)
    cv_file = request.files.get("cv")
    cv = None
    if not cv_file or not cv_file.filename:
        errors["cv"] = "Please attach your CV (PDF, DOC or DOCX, up to 10 MB)."
    elif not errors:
        try:
            cv = check_cv(cv_file.filename, cv_file.mimetype or "",
                          cv_file.read(config.MAX_CV_BYTES + 1))
        except FileRejected as e:
            log.info("CV rejected: %s", e.code)
            errors["cv"] = e.message
    if errors:
        return _err("invalid", "Please check the highlighted fields.", 400, fields=errors)

    email_key = f"email:{data['email']}"
    if _count(email_key, 86400) >= config.APPLICATIONS_PER_EMAIL_DAY:
        return _err("rate_limited", "We've already received several applications from "
                    "you today. Please email hello@gojiphysio.com if you need to add "
                    "anything.", 429)

    try:
        ref = submit(store(), data, cv, vacancy)
    except (StorageFailed, StoreError):
        return _err("storage", STORE_MSG, 503, retry=True)
    _hit(email_key)
    return jsonify({"ok": True, "reference": ref})
