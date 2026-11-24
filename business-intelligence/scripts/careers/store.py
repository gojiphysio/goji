"""
Persisting one application: Drive folder -> CV -> summary -> tracker row.

Idempotent and resumable, with Drive itself as the ledger (no database):
  - The application folder carries the browser's idempotency key as a private
    appProperty. A repeat submission with the same key (a double click, or a
    retry after a lost response) finds that folder and returns the SAME
    reference instead of creating a second application.
  - Each step checks whether it already happened (the CV / summary files are
    tagged with appProperties; the tracker is searched for the reference; the
    folder records `goji_tracker=1` once the row is in) and only does what is
    missing. So if the CV uploaded but the tracker write failed, the candidate's
    retry finishes the job in the existing folder.
  - The caller only reports success after persist() returns, i.e. after the
    folder, CV, summary and tracker row all exist.

Reference numbers (GOJI-APP-<year>-NNNN) are allocated under a process lock;
the service runs as a single instance, so the lock is authoritative. The next
number is one past the highest seen in BOTH the tracker and the Drive folder
names, so a half-finished application can never have its number reused.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
from datetime import datetime, timedelta, timezone

from . import config
from .workspace import Workspace, file_url, folder_url

SGT = timezone(timedelta(hours=8))
_lock = threading.Lock()

IDEM_RE = re.compile(r"^[A-Za-z0-9-]{16,64}$")


def _ref_number(ref: str, year: int) -> int:
    m = re.fullmatch(rf"{config.APP_ID_PREFIX}-{year}-(\d{{4,}})", ref.strip())
    return int(m.group(1)) if m else 0


def next_reference(ws: Workspace, year: int) -> str:
    prefix = f"{config.APP_ID_PREFIX}-{year}-"
    seen = ws.tracker_ids() + ws.folder_names_containing(prefix)
    n = max([_ref_number(x, year) for x in seen] + [0]) + 1
    return f"{prefix}{n:04d}"


def application_summary(ref: str, received: datetime, role: dict, app: dict,
                        cv_meta: dict) -> dict:
    """The structured record stored beside the CV (application.json)."""
    return {
        "application_id": ref,
        "received_at": received.isoformat(),
        "type": "General expression of interest" if role["id"] == config.GENERAL_ID
                else "Job application",
        "role": {"id": role["id"], "title": role["title"]},
        "open_to_alternative_level": app.get("also_consider") or None,
        "candidate": {k: app.get(k) for k in ("full_name", "email", "phone", "linkedin")},
        "availability": {
            "employment": app.get("employment"),
            "days_per_week": app.get("days_per_week") or None,
            "preferred_days": app.get("preferred_days"),
            "earliest_start": app.get("start_availability"),
        },
        "experience": {
            "years_clinical": app.get("years_experience"),
            "ahpc_status": app.get("ahpc_status") or None,
            "clinical_experience": app.get("clinical_experience") or None,
            "womens_health": app.get("womens_health") or None,
            "training": app.get("training"),
            "training_other": app.get("training_other") or None,
        },
        "interest": ({"area": app.get("interest_area"), "detail": app.get("interest_detail")}
                     if role["id"] == config.GENERAL_ID else None),
        "introduction": app.get("intro"),
        "heard_about": app.get("heard_about") or None,
        "source": {"page": app.get("source_page"), **(app.get("utm") or {})},
        "privacy": {
            "notice_version": config.PRIVACY_NOTICE_VERSION,
            "acknowledged_at": received.isoformat(),
            "talent_pool_consent": bool(app.get("talent_pool")),
        },
        "cv": cv_meta,
    }


def tracker_row(ref: str, received: datetime, role: dict, app: dict,
                cv_link: str, folder_link: str) -> list:
    general = role["id"] == config.GENERAL_ID
    ts = received.strftime("%Y-%m-%d %H:%M")
    src = " ".join(f"{k}={v}" for k, v in (app.get("utm") or {}).items())
    source = "Website" + (f" ({app.get('source_page')})" if app.get("source_page") else "")
    if src:
        source += f"; {src}"
    training = list(app.get("training") or [])
    if app.get("training_other"):
        training = [t for t in training if t != "Other"] + [f"Other: {app['training_other']}"]
    row = {
        "Application ID": ref,
        "Date and time received (Asia/Singapore)": ts,
        "Application type": "Expression of interest" if general else "Job application",
        "Role applied for": role["title"],
        "Open to alternative seniority level": app.get("also_consider") or "",
        "Assessed seniority level": "",
        "Interest area (general)": (
            app.get("interest_area", "") + (f": {app['interest_detail']}" if app.get("interest_detail") else "")
        ) if general else "",
        "Clinic location": "" if general else "Lentor Modern",
        "Full name": app.get("full_name", ""),
        "Email": app.get("email", ""),
        "Mobile number": app.get("phone", ""),
        "Employment preference": app.get("employment", ""),
        "Days available per week": app.get("days_per_week", ""),
        "Preferred working days": ", ".join(app.get("preferred_days") or []),
        "Actual years of clinical experience": app.get("years_experience", ""),
        "AHPC registration status": app.get("ahpc_status", ""),
        "Clinical experience": app.get("clinical_experience", ""),
        "Women's health experience or interest": app.get("womens_health", ""),
        "Additional certifications": ", ".join(training),
        "Earliest available start date": app.get("start_availability", ""),
        "Personal introduction": app.get("intro", ""),
        "LinkedIn profile": app.get("linkedin", ""),
        "How they heard about Goji": app.get("heard_about", ""),
        "Application source": source,
        "CV link": cv_link,
        "Application folder link": folder_link,
        "Recruitment status": "New",
        "Assigned reviewer": "",
        "Last updated": ts,
        "Interview date": "",
        "Internal notes": "",
        "Privacy notice version": config.PRIVACY_NOTICE_VERSION,
        "Privacy acknowledgement timestamp": ts,
        "Talent pool consent": "Yes" if app.get("talent_pool") else "No",
        "Retention review date": (received + timedelta(days=config.RETENTION_REVIEW_DAYS)).strftime("%Y-%m-%d"),
    }
    assert list(row) == config.TRACKER_COLUMNS, "tracker_row out of sync with TRACKER_COLUMNS"
    return [row[c] for c in config.TRACKER_COLUMNS]


def persist(ws: Workspace, idem_key: str, role: dict, app: dict, cv: dict,
            now: datetime | None = None) -> dict:
    """Store (or finish storing) one application. Returns
    {"reference", "folder_id", "cv_id", "props", "created"}.

    `role` = {"id", "title", "drive_folder"}; `cv` = {"ext", "data",
    "content_type", "original_name"}. Raises WorkspaceError on failure; a
    retry with the same idem_key resumes where it stopped."""
    if not IDEM_RE.match(idem_key or ""):
        raise ValueError("bad idempotency key")
    received = (now or datetime.now(SGT)).astimezone(SGT)
    with _lock:
        created = False
        folder = ws.find_by_property("goji_idem", idem_key)
        if folder:
            props = dict(folder.get("appProperties") or {})
            ref = props.get("goji_ref") or folder["name"]
            if props.get("goji_received"):
                received = datetime.fromisoformat(props["goji_received"])
        else:
            ref = next_reference(ws, received.year)
            year = ws.ensure_folder(config.APPLICATIONS_FOLDER_ID, str(received.year))
            role_dir = ws.ensure_folder(year["id"], role["drive_folder"])
            props = {"goji_idem": idem_key, "goji_ref": ref, "goji_role": role["id"],
                     "goji_received": received.isoformat()}
            folder = ws.create_folder(ref, role_dir["id"], props)
            created = True
        fid = folder["id"]

        existing = {(c.get("appProperties") or {}).get("goji_kind"): c
                    for c in ([] if created else ws.children(fid))}

        cv_file = existing.get("cv")
        if not cv_file:
            cv_file = ws.upload(f"{ref}-CV.{cv['ext']}", fid, cv["content_type"], cv["data"],
                                {"goji_kind": "cv", "goji_ref": ref})
        if not existing.get("summary"):
            cv_meta = {"stored_as": f"{ref}-CV.{cv['ext']}",
                       "original_filename": cv["original_name"],
                       "bytes": len(cv["data"]),
                       "sha256": hashlib.sha256(cv["data"]).hexdigest()}
            summary = application_summary(ref, received, role, app, cv_meta)
            ws.upload(f"{ref}-application.json", fid, "application/json",
                      json.dumps(summary, indent=2, ensure_ascii=False).encode("utf-8"),
                      {"goji_kind": "summary", "goji_ref": ref})

        if props.get("goji_tracker") != "1":
            if ref not in ws.tracker_ids():
                ws.append_row(tracker_row(ref, received, role, app,
                                          file_url(cv_file["id"]), folder_url(fid)))
            props["goji_tracker"] = "1"
            ws.set_properties(fid, {"goji_tracker": "1"})

        return {"reference": ref, "folder_id": fid, "cv_id": cv_file["id"],
                "props": props, "created": created}


def mark(ws: Workspace, folder_id: str, key: str) -> None:
    """Record that a one-time side effect (an email) has happened."""
    try:
        ws.set_properties(folder_id, {key: "1"})
    except Exception:
        pass  # worst case a retry re-sends that one email
