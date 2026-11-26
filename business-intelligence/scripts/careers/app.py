"""
goji-careers — the website's recruitment backend (Cloud Run,
careers-api.gojiphysio.com). Write-only by design:

  POST /api/applications   store one application or expression of interest
  GET  /healthcheck        liveness

There is deliberately NO endpoint that lists, reads or edits applications.
Reviewers work in Google Drive / Sheets with their own Goji accounts; this
service only ever appends. Kept apart from goji-booking so recruitment data
never shares a process, identity or log stream with patient bookings.

Submission sequence (recruitment brief §8):
  1. origin + custom-header check (CSRF), rate limit, bot checks
  2. role still open? (the website's vacancies.json)
  3. validate fields and the CV server-side
  4. store.persist(): reference -> private Drive folder -> CV -> summary ->
     tracker row (idempotent on the browser's key; resumable)
  5. internal notification, then the applicant's acknowledgement (each sent
     once, best-effort; a failure never loses or repeats the application)
  6. {"ok": true, "reference": ...} only after step 4 has fully succeeded

Logs carry reference numbers and error codes only: never names, contact
details, answers or file contents.
"""
from __future__ import annotations

import logging
import threading
import time

import requests
from flask import Flask, jsonify, request

from . import config, mailer, store, vacancies
from .validation import FileRejected, CONTENT_TYPES, check_cv, sanitise_filename, validate_form
from .workspace import Workspace, WorkspaceError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("goji-careers")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = config.MAX_REQUEST_BYTES

_ws: Workspace | None = None
_ws_lock = threading.Lock()


def workspace() -> Workspace:
    global _ws
    if _ws is None:
        with _ws_lock:
            if _ws is None:
                _ws = Workspace()
    return _ws


RETRY_MSG = ("We couldn't save your application just now. Please try again in a minute, "
             "or email your CV to hello@gojiphysio.com.")
BOT_MSG = ("We couldn't verify this submission. Please try again, or email your CV to "
           "hello@gojiphysio.com.")


def _err(status: int, code: str, msg: str, fields: dict | None = None):
    body = {"ok": False, "code": code, "error": msg}
    if fields:
        body["fields"] = fields
    return jsonify(body), status


# ---- CORS / headers ------------------------------------------------------------

@app.after_request
def _headers(resp):
    origin = request.headers.get("Origin", "")
    if origin in config.CORS_ORIGINS:
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Goji-Careers"
        resp.headers["Access-Control-Max-Age"] = "86400"
    resp.headers["Vary"] = "Origin"
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


@app.errorhandler(413)
def _too_big(_e):
    return _err(413, "file_too_large", "Please upload a CV of 10MB or less.",
                {"cv": "Please upload a CV of 10MB or less."})


@app.route("/healthcheck")
def healthcheck():
    return "ok", 200


# ---- abuse controls ----------------------------------------------------------------

_hits: dict[str, list[tuple[float, str]]] = {}
_hits_lock = threading.Lock()
_human_keys: dict[str, float] = {}  # idem keys that already passed Turnstile


def _client_ip() -> str:
    """Cloud Run appends the real client address as the LAST X-Forwarded-For
    entry; anything before it is caller-controlled."""
    xff = request.headers.get("X-Forwarded-For", "")
    return (xff.split(",")[-1].strip() if xff else "") or (request.remote_addr or "?")


def _over_limit(key: str, window_s: float, limit: int, idem: str) -> bool:
    """True when `key` already has `limit` distinct submissions in the window
    and this one (idem) is a new submission. Retries of the same submission
    (same idempotency key) never count against the candidate."""
    now = time.monotonic()
    with _hits_lock:
        rows = [(t, k) for t, k in _hits.get(key, []) if now - t < window_s]
        _hits[key] = rows
        keys = {k for _, k in rows}
        return idem not in keys and len(keys) >= limit


def _record(key: str, idem: str) -> None:
    with _hits_lock:
        rows = _hits.setdefault(key, [])
        if idem not in {k for _, k in rows}:
            rows.append((time.monotonic(), idem))


def _turnstile_ok(token: str, ip: str) -> bool:
    try:
        r = requests.post("https://challenges.cloudflare.com/turnstile/v0/siteverify", timeout=5,
                          data={"secret": config.TURNSTILE_SECRET, "response": token,
                                "remoteip": ip})
        return bool(r.json().get("success"))
    except Exception as e:
        # An outage at Cloudflare must not close recruitment; the limits still apply.
        log.warning("turnstile unreachable, allowing: %s", type(e).__name__)
        return True


def _bot_reason(form, idem: str, ip: str) -> str | None:
    if (form.get("company_url") or "").strip():
        return "honeypot"
    try:
        elapsed = int(form.get("elapsed_ms") or "0")
    except ValueError:
        elapsed = 0
    if elapsed < config.MIN_FILL_MS:
        return "too_fast"
    if config.TURNSTILE_SECRET and idem not in _human_keys:
        token = (form.get("turnstile_token") or "").strip()
        if not token:
            return "captcha_missing"
        if not _turnstile_ok(token[:2048], ip):
            return "captcha_failed"
        _human_keys[idem] = time.monotonic()
    return None


# ---- the endpoint ------------------------------------------------------------------------

@app.route("/api/applications", methods=["POST", "OPTIONS"])
def applications():
    if request.method == "OPTIONS":
        if request.headers.get("Origin", "") not in config.CORS_ORIGINS:
            return "", 403
        return "", 204

    # CSRF: only our site, and only via the form's script (the custom header
    # forces a CORS preflight that other origins fail).
    if request.headers.get("Origin", "") not in config.CORS_ORIGINS or \
            request.headers.get("X-Goji-Careers") != "1":
        return _err(403, "forbidden", "This form can only be submitted from gojiphysio.com.")

    form = request.form
    idem = (form.get("idempotency_key") or "").strip()
    if not store.IDEM_RE.match(idem):
        return _err(400, "bad_request", RETRY_MSG)

    ip = _client_ip()
    if _over_limit(f"ip:{ip}", 3600, config.PER_IP_PER_HOUR, idem):
        log.warning("careers rate-limited (ip window)")
        return _err(429, "rate_limited",
                    "We've received several applications from this connection. Please try again "
                    "later, or email your CV to hello@gojiphysio.com.")
    _record(f"ip:{ip}", idem)

    bot = _bot_reason(form, idem, ip)
    if bot:
        log.warning("careers submission refused by bot check (%s)", bot)
        return _err(400, "bot_check", BOT_MSG)

    # ---- role ----
    role_id = (form.get("role") or "").strip()
    general = role_id == config.GENERAL_ID
    vacancy = None
    if general:
        role = {"id": config.GENERAL_ID, "title": config.GENERAL_TITLE,
                "drive_folder": config.GENERAL_FOLDER}
    else:
        status, vacancy = vacancies.lookup(role_id)
        if status == "unavailable":
            log.error("vacancies.json unavailable; refusing job application")
            return _err(503, "vacancies_unavailable", RETRY_MSG)
        if status == "unknown":
            return _err(400, "unknown_role", "Please choose one of the open roles.",
                        {"role": "Please choose one of the open roles."})
        if status == "closed":
            return _err(409, "role_closed",
                        "Applications for this role have now closed. You're welcome to send us an "
                        "expression of interest instead.")
        role = {"id": vacancy["id"], "title": vacancy["title"],
                "drive_folder": vacancy.get("drive_folder") or vacancy["title"]}

    # ---- fields + file ----
    result = validate_form(form, vacancy, general)
    errors = dict(result.errors)
    upload = request.files.get("cv")
    cv = None
    if not upload or not upload.filename:
        errors["cv"] = "Choose your CV to upload."
    else:
        data = upload.read(config.MAX_CV_BYTES + 1)
        try:
            ext = check_cv(upload.filename, upload.mimetype or "", data)
            cv = {"ext": ext, "data": data, "content_type": CONTENT_TYPES[ext],
                  "original_name": sanitise_filename(upload.filename)}
        except FileRejected as e:
            errors["cv"] = str(e)
    if errors:
        log.info("careers validation failed: %s", ",".join(sorted(errors)))
        return _err(400, "invalid", "Please check the highlighted fields.", errors)

    email_key = f"email:{result.data['email'].lower()}"
    if _over_limit(email_key, 86400, config.PER_EMAIL_PER_DAY, idem):
        return _err(429, "rate_limited",
                    "We've already received several applications from this email address today. "
                    "If you need to update one, please email hello@gojiphysio.com.")

    # ---- store ----
    try:
        stored = store.persist(workspace(), idem, role, result.data, cv)
    except WorkspaceError as e:
        log.error("careers storage failed (%s): %s", role["id"], e)
        return _err(503, "storage_failed", RETRY_MSG)
    except Exception:
        log.exception("careers storage crashed (%s)", role["id"])
        return _err(503, "storage_failed", RETRY_MSG)
    _record(email_key, idem)
    ref, props = stored["reference"], stored["props"]
    log.info("careers application stored: %s (%s, %s)", ref, role["id"],
             "new" if stored["created"] else "resumed")

    # ---- emails (once each, never blocking the success response) ----
    ws = workspace()
    if props.get("goji_notified") != "1" and \
            mailer.send_internal(ref, role, result.data, stored["folder_id"]):
        store.mark(ws, stored["folder_id"], "goji_notified")
    if props.get("goji_acked") != "1" and mailer.send_ack(ref, role, result.data):
        store.mark(ws, stored["folder_id"], "goji_acked")

    return jsonify({"ok": True, "reference": ref})
