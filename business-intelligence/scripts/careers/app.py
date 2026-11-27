"""
goji-careers: the website's job-application backend (Cloud Run,
careers-api.gojiphysio.com).

  POST /api/applications   store one application or expression of interest
  GET  /healthcheck        liveness

One submission:
  1. only from our site (origin + custom header), then bot checks: hidden
     honeypot field, minimum fill time, Cloudflare Turnstile
  2. the role is still open (the website's vacancies.json)
  3. validate the fields, the CV and (Pilates instructor) any certificates
  4. upload the files to the applications folder, append a row to the tracker
  5. email hello@, then send the applicant's confirmation

There is deliberately no endpoint that lists or reads applications: reviewers
use Drive and Sheets with their own Goji accounts. Logs carry the reference and
error codes only, never names, contact details or file contents.
"""
from __future__ import annotations

import logging
import re
import threading
from datetime import datetime, timedelta, timezone

import requests
from flask import Flask, jsonify, request

from . import config, mailer, vacancies
from .validation import (CERT_TYPES, CONTENT_TYPES, FileRejected, check_certificate, check_cv,
                         validate_form)
from .workspace import Workspace, WorkspaceError, file_url, folder_url

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("goji-careers")
SGT = timezone(timedelta(hours=8))

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = config.MAX_CV_BYTES + config.MAX_CERT_BYTES + 256 * 1024

_ws: Workspace | None = None
_ref_lock = threading.Lock()  # with --max-instances=1, reference numbers never collide

RETRY_MSG = ("We couldn't save your application just now. Please try again in a minute, "
             "or email your CV to hello@gojiphysio.com.")
BOT_MSG = ("We couldn't verify this submission. Please try again, or email your CV to "
           "hello@gojiphysio.com.")


def workspace() -> Workspace:
    global _ws
    if _ws is None:
        _ws = Workspace()
    return _ws


def _err(status: int, code: str, msg: str, fields: dict | None = None):
    body = {"ok": False, "code": code, "error": msg}
    if fields:
        body["fields"] = fields
    return jsonify(body), status


@app.after_request
def _headers(resp):
    if request.headers.get("Origin", "") in config.CORS_ORIGINS:
        resp.headers["Access-Control-Allow-Origin"] = request.headers["Origin"]
        resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Goji-Careers"
        resp.headers["Access-Control-Max-Age"] = "86400"
    resp.headers["Vary"] = "Origin"
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.errorhandler(413)
def _too_big(_e):
    msg = "Your files are too large. Please keep your CV, and your certificates together, to 10MB each."
    return _err(413, "file_too_large", msg, {"cv": msg})


@app.route("/healthcheck")
def healthcheck():
    return "ok", 200


# ---- bot checks --------------------------------------------------------------------

def _turnstile_ok(token: str) -> bool:
    xff = request.headers.get("X-Forwarded-For", "")
    ip = xff.split(",")[-1].strip() if xff else (request.remote_addr or "")
    try:
        r = requests.post("https://challenges.cloudflare.com/turnstile/v0/siteverify", timeout=5,
                          data={"secret": config.TURNSTILE_SECRET, "response": token,
                                "remoteip": ip})
        return bool(r.json().get("success"))
    except Exception as e:
        # A Cloudflare outage must not close recruitment.
        log.warning("turnstile unreachable, allowing: %s", type(e).__name__)
        return True


def _bot_reason(form) -> str | None:
    if (form.get("company_url") or "").strip():
        return "honeypot"
    try:
        elapsed = int(form.get("elapsed_ms") or "0")
    except ValueError:
        elapsed = 0
    if elapsed < config.MIN_FILL_MS:
        return "too_fast"
    if config.TURNSTILE_SECRET:
        token = (form.get("turnstile_token") or "").strip()
        if not token:
            return "captcha_missing"
        if not _turnstile_ok(token[:2048]):
            return "captcha_failed"
    return None


# ---- storing -------------------------------------------------------------------------

def next_reference(ws: Workspace, year: int) -> str:
    """GOJI-APP-<year>-NNNN, one past the highest this year in the tracker."""
    prefix = f"{config.APP_ID_PREFIX}-{year}-"
    nums = [int(m.group(1)) for ref in ws.tracker_ids()
            if (m := re.fullmatch(rf"{re.escape(prefix)}(\d{{4,}})", ref.strip()))]
    return f"{prefix}{max(nums, default=0) + 1:04d}"


def _join(items, other: str = "", other_label: str = "Others") -> str:
    """A multi-select as one cell: "Mat, Reformer, Others: Wunda chair"."""
    out = [x for x in items or [] if x != other_label]
    if other_label in (items or []):
        out.append(f"{other_label}: {other}" if other else other_label)
    return ", ".join(out)


def tracker_row(ref: str, received: datetime, role: dict, d: dict, cv_id: str,
                cert_ids: list[str] | None = None) -> list:
    general = role["id"] == config.GENERAL_ID
    ts = received.strftime("%Y-%m-%d %H:%M")
    source = "Website" + (f" ({d['source_page']})" if d.get("source_page") else "")
    if d.get("utm"):
        source += "; " + " ".join(f"{k}={v}" for k, v in d["utm"].items())
    training = [t for t in d.get("training") or [] if t != "Other"]
    if d.get("training_other"):
        training.append(f"Other: {d['training_other']}")
    elif "Other" in (d.get("training") or []):
        training.append("Other")
    interest = ""
    if general:
        interest = d.get("interest_area", "") + (
            f": {d['interest_detail']}" if d.get("interest_detail") else "")
    row = {
        "Application ID": ref,
        "Date and time received (Asia/Singapore)": ts,
        "Application type": "Expression of interest" if general else "Job application",
        "Role applied for": role["title"],
        "Assessed seniority level": "",
        "Interest area (general)": interest,
        "Clinic location": "" if general else "Lentor Modern",
        "Full name": d.get("full_name", ""),
        "Email": d.get("email", ""),
        "Mobile number": d.get("phone", ""),
        "Employment preference": d.get("employment", ""),
        "Days available per week": d.get("days_per_week", ""),
        "Preferred working days": ", ".join(d.get("preferred_days") or []),
        "Actual years of clinical experience": d.get("years_experience", ""),
        "AHPC registration status": d.get("ahpc_status", ""),
        "Clinical experience": d.get("clinical_experience", ""),
        "Women's health experience or interest": d.get("womens_health", ""),
        "Additional certifications": ", ".join(training),
        "Earliest available start date": d.get("start_availability", ""),
        "Personal introduction": d.get("intro", ""),
        "LinkedIn profile": d.get("linkedin", ""),
        "How they heard about Goji": d.get("heard_about", ""),
        "Application source": source,
        "CV link": file_url(cv_id),
        "Application folder link": folder_url(),
        "Recruitment status": "New",
        "Assigned reviewer": "",
        "Last updated": ts,
        "Interview date": "",
        "Internal notes": "",
        "Privacy notice version": config.PRIVACY_NOTICE_VERSION,
        "Privacy acknowledgement timestamp": ts,
        "Talent pool consent": "Yes" if d.get("talent_pool") else "No",
        "Retention review date": (received + timedelta(days=config.RETENTION_REVIEW_DAYS)
                                  ).strftime("%Y-%m-%d"),
        "Singapore work eligibility": d.get("work_eligibility", ""),
        "Pilates certification and training provider": d.get("certification", ""),
        "Apparatus qualifications": _join(d.get("apparatus"), d.get("apparatus_other", "")),
        "Years of teaching experience": d.get("teaching_years", ""),
        "Relevant teaching experience": _join(d.get("teaching_experience"),
                                              d.get("teaching_other", "")),
        "Preferred time windows": ", ".join(d.get("time_windows") or []),
        "Approximate weekly availability": d.get("weekly_availability", ""),
        "Current teaching commitments": d.get("current_commitments", ""),
        "Pilates certificate links": "\n".join(file_url(i) for i in cert_ids or []),
        "Portfolio / social media profile": d.get("portfolio", ""),
    }
    assert list(row) == config.TRACKER_COLUMNS, "tracker_row out of sync with TRACKER_COLUMNS"
    return list(row.values())


def _file_name(ref: str, full_name: str, what: str, ext: str) -> str:
    safe = re.sub(r"[^\w .'-]+", "", full_name, flags=re.UNICODE).strip()[:80] or "Applicant"
    return f"{ref} - {safe} - {what}.{ext}"


def _cv_name(ref: str, full_name: str, ext: str) -> str:
    return _file_name(ref, full_name, "CV", ext)


# ---- the endpoint ------------------------------------------------------------------

@app.route("/api/applications", methods=["POST", "OPTIONS"])
def applications():
    origin_ok = request.headers.get("Origin", "") in config.CORS_ORIGINS
    if request.method == "OPTIONS":
        return ("", 204) if origin_ok else ("", 403)
    # The custom header forces a CORS preflight, which other sites fail.
    if not origin_ok or request.headers.get("X-Goji-Careers") != "1":
        return _err(403, "forbidden", "This form can only be submitted from gojiphysio.com.")

    form = request.form
    bot = _bot_reason(form)
    if bot:
        log.warning("careers submission refused by bot check (%s)", bot)
        return _err(400, "bot_check", BOT_MSG)

    # ---- role ----
    role_id = (form.get("role") or "").strip()
    vacancy = None
    if role_id == config.GENERAL_ID:
        role = {"id": config.GENERAL_ID, "title": config.GENERAL_TITLE}
    else:
        status, vacancy = vacancies.lookup(role_id)
        if status == "unavailable":
            return _err(503, "vacancies_unavailable", RETRY_MSG)
        if status == "unknown":
            msg = "Please choose one of the open roles."
            return _err(400, "unknown_role", msg, {"role": msg})
        if status == "closed":
            return _err(409, "role_closed",
                        "Applications for this role have now closed. You're welcome to send us "
                        "an expression of interest instead.")
        role = {"id": vacancy["id"], "title": vacancy["title"], "form": vacancy.get("form", "")}

    # ---- fields + CV ----
    result = validate_form(form, vacancy, role["id"] == config.GENERAL_ID)
    errors = dict(result.errors)
    upload = request.files.get("cv")
    cv = ext = None
    if not upload or not upload.filename:
        errors["cv"] = "Choose your CV to upload."
    else:
        cv = upload.read(config.MAX_CV_BYTES + 1)
        try:
            ext = check_cv(upload.filename, cv)
        except FileRejected as e:
            errors["cv"] = str(e)
    # Pilates certificates: optional, up to MAX_CERTS, MAX_CERT_BYTES together.
    certs: list[tuple[bytes, str]] = []
    if vacancy and vacancy.get("form") == "pilates":
        uploads = [u for u in request.files.getlist("certificates") if u and u.filename]
        total = 0
        if len(uploads) > config.MAX_CERTS:
            errors["certificates"] = f"Choose up to {config.MAX_CERTS} certificate files."
        for u in uploads[:config.MAX_CERTS]:
            data = u.read(config.MAX_CERT_BYTES + 1)
            total += len(data)
            try:
                certs.append((data, check_certificate(u.filename, data)))
            except FileRejected as e:
                errors.setdefault("certificates", str(e))
        if total > config.MAX_CERT_BYTES:
            errors.setdefault("certificates", "Please keep certificates to 10MB in total.")
    if errors:
        log.info("careers validation failed: %s", ",".join(sorted(errors)))
        return _err(400, "invalid", "Please check the highlighted fields.", errors)

    # ---- store: CV, then the tracker row ----
    d = result.data
    received = datetime.now(SGT)
    try:
        ws = workspace()
        with _ref_lock:
            ref = next_reference(ws, received.year)
            cv_id = ws.upload(_cv_name(ref, d["full_name"], ext), CONTENT_TYPES[ext], cv)
            multi = len(certs) > 1
            cert_ids = [ws.upload(_file_name(ref, d["full_name"],
                                             f"Certificate {n}" if multi else "Certificate", cext),
                                  CERT_TYPES[cext], data)
                        for n, (data, cext) in enumerate(certs, 1)]
            ws.append_row(tracker_row(ref, received, role, d, cv_id, cert_ids))
    except WorkspaceError as e:
        log.error("careers storage failed (%s): %s", role["id"], e)
        return _err(503, "storage_failed", RETRY_MSG)
    except Exception:
        log.exception("careers storage crashed (%s)", role["id"])
        return _err(503, "storage_failed", RETRY_MSG)
    log.info("careers application stored: %s (%s)", ref, role["id"])

    # ---- emails (best effort; the application is already safe) ----
    mailer.send("internal", mailer.internal_message(ref, role, d, cv_id, cert_ids), ref)
    mailer.send("confirmation", mailer.confirmation_message(role, d), ref)

    return jsonify({"ok": True, "reference": ref})
