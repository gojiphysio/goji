"""
The application submission pipeline: store first, then notify.

    1. find-or-create the application folder (keyed by the browser's
       submission_id, so a double-click or a retry finds the same folder)
    2. upload the CV                       -> folder appProperty `cv`
    3. upload application-summary.json     -> folder appProperty `summary`
    4. append the tracker row              -> folder appProperty `tracker`
       (stored = all four done; only now may the website say "received")
    5. internal notification to hello@     -> folder appProperty `notified`
    6. acknowledgement to the applicant    -> folder appProperty `acked`

Each step records its completion on the folder (Drive appProperties), so a
retry with the same submission_id resumes where the last attempt stopped and
never makes a second folder, row or email. Steps 1-4 failing raises
StorageFailed (the website shows a retryable error); 5-6 failing is logged and
swallowed (the application is already safe), and `reconcile` can resend.

The summary JSON is the record of truth for the tracker row: when step 4 runs
on a retry it rebuilds the row from the stored summary, not from the retry's
form data, so the folder, summary and row always agree.

Logs carry the application reference only, never names, emails or CV content.
"""
from __future__ import annotations

import json
import logging
import threading
from contextlib import contextmanager
from datetime import date, datetime

from . import config, mailer
from .filecheck import CheckedFile
from .google_store import (GoogleStore, StoreError, file_url, folder_url, sheet_url)
from .vacancies import Vacancy

log = logging.getLogger("careers.pipeline")

TRACKER_COLUMNS = [
    "Application ID",
    "Date and time received (Asia/Singapore)",
    "Role applied for",
    "Clinic location",
    "Full name",
    "Email",
    "Mobile number",
    "Employment preference",
    "Days available per week",
    "Preferred working days",
    "Years of experience",
    "AHPC registration status",
    "Clinical experience",
    "Women's health experience",
    "Additional certifications",
    "Earliest available start date",
    "Personal introduction",
    "LinkedIn profile",
    "Application source",
    "CV link",
    "Application folder link",
    "Recruitment status",
    "Assigned reviewer",
    "Last updated",
    "Interview date",
    "Internal notes",
    "Privacy notice version",
    "Privacy acknowledgement timestamp",
    "Talent pool consent",
    "Retention review date",
]
STATUSES = ["New", "Under Review", "Shortlisted", "Interview Scheduled", "Interviewed",
            "Offer Extended", "Hired", "Not Progressing", "Talent Pool", "Withdrawn"]
STATUS_COLUMN = TRACKER_COLUMNS.index("Recruitment status")


class StorageFailed(Exception):
    """The application could not be stored safely; the website must not say
    it was received. Retrying with the same submission_id is safe."""


# One process (Cloud Run --max-instances=1), so in-process locks are
# authoritative: one lock per submission_id (two concurrent clicks of the same
# form wait for each other) and one for the reference counter.
_key_locks: dict[str, threading.Lock] = {}
_key_locks_guard = threading.Lock()
_seq_lock = threading.Lock()


@contextmanager
def _locked(key: str):
    with _key_locks_guard:
        lock = _key_locks.setdefault(key, threading.Lock())
    with lock:
        yield
    with _key_locks_guard:
        if not lock.locked():
            _key_locks.pop(key, None)


def add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    y, m = d.year + y, m + 1
    for day in (d.day, 30, 29, 28):
        try:
            return date(y, m, day)
        except ValueError:
            continue
    raise ValueError(d)


def next_reference(store: GoogleStore, year: int) -> str:
    """GOJI-APP-<year>-<4-digit sequence>. The counter lives on the root
    folder's appProperties (seq_<year>), so it survives restarts."""
    with _seq_lock:
        root = store.get_file(config.DRIVE_ROOT_ID)
        props = root.get("appProperties") or {}
        n = int(props.get(f"seq_{year}", "0")) + 1
        store.set_app_properties(config.DRIVE_ROOT_ID, {f"seq_{year}": str(n)})
    return f"GOJI-APP-{year}-{n:04d}"


def build_summary(ref: str, app: dict, cv: CheckedFile, cv_name: str,
                  received: datetime) -> dict:
    months = config.TALENT_POOL_RETENTION_MONTHS if app["talent_pool"] \
        else config.RETENTION_MONTHS
    return {
        "reference": ref,
        "received_at": received.isoformat(timespec="seconds"),
        "application_type": app["application_type"],
        "job_id": app["job_id"],
        "role": app["role"],
        "role_category": app.get("role_category"),
        "location": app["location"],
        "applicant": {
            "full_name": app["full_name"],
            "email": app["email"],
            "phone": app["phone"],
            "linkedin": app["linkedin"],
        },
        "answers": {
            "employment_pref": app["employment_pref"],
            "days_per_week": app["days_per_week"],
            "below_min_days": app["below_min_days"],
            "available_days": app["available_days"],
            "years_experience": app["years_experience"],
            "start_availability": app["start_availability"],
            "ahpc_status": app["ahpc_status"],
            "clinical_areas": app["clinical_areas"],
            "clinical_areas_other": app["clinical_areas_other"],
            "womens_health": app["womens_health"],
            "certifications": app["certifications"],
            "certifications_other": app["certifications_other"],
            "how_heard": app["how_heard"],
            "intro": app["intro"],
        },
        "attribution": app.get("attribution") or {},
        "cv": {
            "stored_as": cv_name,
            "original_name": cv.safe_name,
            "type": cv.ext,
            "size_bytes": cv.size,
            "sha256": cv.sha256,
            "checks": "passed structural safety checks (signature, active content)",
        },
        "privacy": {
            "notice_version": config.PRIVACY_NOTICE_VERSION,
            "acknowledged_at": received.isoformat(timespec="seconds"),
            "talent_pool_consent": app["talent_pool"],
            "retention_review_date": add_months(received.date(), months).isoformat(),
        },
        "submission_id": app["submission_id"],
    }


def _labels(keys, options: dict, other: str = "") -> str:
    out = [options.get(k, k) for k in keys or [] if k != "other"]
    if "other" in (keys or []):
        out.append(f"Other: {other}" if other else "Other")
    return ", ".join(out)


def tracker_row(s: dict, cv_id: str, folder_id: str) -> list[str]:
    a, ans, p = s["applicant"], s["answers"], s["privacy"]
    days = ""
    if ans.get("days_per_week") is not None:
        days = str(ans["days_per_week"])
        if ans.get("below_min_days"):
            days += " (below the stated minimum)"
    attr = s.get("attribution") or {}
    source = config.HEARD.get(ans.get("how_heard") or "", "")
    if attr:
        utm = " / ".join(v for v in (attr.get("utm_source"), attr.get("utm_medium"),
                                     attr.get("utm_campaign")) if v)
        source = f"{source} (utm: {utm})".strip() if utm else source
    received = s["received_at"].replace("T", " ")[:16]
    return [
        s["reference"],
        received,
        s["role"],
        s["location"],
        a["full_name"],
        a["email"],
        a["phone"],
        config.EMPLOYMENT.get(ans.get("employment_pref") or "", ""),
        days,
        _labels(ans.get("available_days"), config.DAYS),
        config.YEARS.get(ans.get("years_experience") or "", ""),
        config.AHPC.get(ans.get("ahpc_status") or "", ""),
        _labels(ans.get("clinical_areas"), config.CLINICAL_AREAS,
                ans.get("clinical_areas_other", "")),
        ans.get("womens_health", ""),
        _labels(ans.get("certifications"), config.CERTIFICATIONS,
                ans.get("certifications_other", "")),
        ans.get("start_availability", ""),
        ans.get("intro", ""),
        a.get("linkedin", ""),
        source,
        file_url(cv_id),
        folder_url(folder_id),
        "New",
        "",
        received,
        "",
        "",
        p["notice_version"],
        p["acknowledged_at"].replace("T", " ")[:19],
        "Yes" if p["talent_pool_consent"] else "No",
        p["retention_review_date"],
    ]


def ensure_tracker_row(store: GoogleStore, folder: dict, summary: dict | None = None) -> None:
    """Append the tracker row for an application folder unless it's already
    there (matched on Application ID). Used by submit() and reconcile."""
    props = folder.get("appProperties") or {}
    ref = props["reference"]
    if ref not in store.column_values(config.TRACKER_ID, config.TRACKER_TAB, "A"):
        if summary is None:
            summary = json.loads(store.download(props["summary"]))
        store.append_row(config.TRACKER_ID, config.TRACKER_TAB,
                         tracker_row(summary, props["cv"], folder["id"]))
    store.set_app_properties(folder["id"], {"tracker": "1"})
    props["tracker"] = "1"


def _notify(store: GoogleStore, folder: dict, summary: dict | None) -> None:
    """Steps 5-6: best-effort emails, each sent at most once."""
    props = folder.get("appProperties") or {}
    if props.get("notified") == "1" and props.get("acked") == "1":
        return
    if summary is None:
        summary = json.loads(store.download(props["summary"]))
    links = {"folder": folder_url(folder["id"]), "tracker": sheet_url(config.TRACKER_ID)}
    for flag, send in (("notified", mailer.send_internal_notification),
                       ("acked", mailer.send_applicant_acknowledgement)):
        if props.get(flag) == "1":
            continue
        if send(summary, links):
            try:
                store.set_app_properties(folder["id"], {flag: "1"})
                props[flag] = "1"
            except StoreError as e:
                log.warning("%s: could not record %s flag: %s", props.get("reference"), flag, e)


def submit(store: GoogleStore, app: dict, cv: CheckedFile, vacancy: Vacancy,
           now: datetime | None = None) -> str:
    """Store an application end to end; return its reference. Raises
    StorageFailed if it could not be stored (safe to retry)."""
    now = (now or datetime.now(config.SGT)).astimezone(config.SGT)
    sid = app["submission_id"]
    summary: dict | None = None
    with _locked(sid):
        try:
            folder = store.find_folder_by_property("submission_id", sid)
            if folder is None:
                ref = next_reference(store, now.year)
                year_id = store.ensure_folder(config.DRIVE_APPLICATIONS_ID, str(now.year))
                role_id = store.ensure_folder(year_id, vacancy.drive_folder)
                folder = store.create_folder(ref, role_id, {
                    "submission_id": sid, "reference": ref, "job_id": vacancy.id,
                    "received_at": now.isoformat(timespec="seconds")})
                log.info("%s: folder created", ref)
            props = folder.setdefault("appProperties", {})
            ref = props["reference"]
            received = datetime.fromisoformat(props.get("received_at") or now.isoformat())

            if not props.get("cv"):
                cv_name = f"{ref}-CV.{cv.ext}"
                f = store.upload(folder["id"], cv_name, cv.mime, cv.data,
                                 {"kind": "cv", "sha256": cv.sha256[:64]})
                store.set_app_properties(folder["id"], {"cv": f["id"], "cv_name": cv_name,
                                                        "cv_sha": cv.sha256[:40]})
                props.update(cv=f["id"], cv_name=cv_name)
                log.info("%s: CV stored", ref)
            if not props.get("summary"):
                summary = build_summary(ref, app, cv, props["cv_name"], received)
                f = store.upload(folder["id"], f"{ref}-application-summary.json",
                                 "application/json",
                                 json.dumps(summary, indent=2, ensure_ascii=False).encode(),
                                 {"kind": "summary"})
                store.set_app_properties(folder["id"], {"summary": f["id"]})
                props["summary"] = f["id"]
            if props.get("tracker") != "1":
                ensure_tracker_row(store, folder, summary)
                log.info("%s: tracker row added", ref)
        except StoreError as e:
            log.error("application not stored (submission %s…): %s", sid[:8], e)
            raise StorageFailed(str(e)) from e
        except (KeyError, ValueError) as e:
            log.error("application folder in a bad state (submission %s…): %r", sid[:8], e)
            raise StorageFailed("inconsistent application folder") from e

        # Stored. Emails are best-effort from here on.
        try:
            _notify(store, folder, summary)
        except Exception as e:
            log.warning("%s: notification step failed: %s", ref, e)
    return ref


def reconcile(store: GoogleStore, dry_run: bool = False) -> list[str]:
    """Finish any application whose earlier attempt stopped part-way: add a
    missing tracker row, resend a missing email. Returns a line per action."""
    actions: list[str] = []
    # drive.file scope: this only ever sees folders the service created.
    folders = store.find_files(
        "mimeType='application/vnd.google-apps.folder' and trashed=false "
        "and name contains 'GOJI-APP-'", fields="id,name,appProperties")
    for folder in folders:
        props = folder.get("appProperties") or {}
        ref = props.get("reference")
        if not ref:
            continue
        if not props.get("cv") or not props.get("summary"):
            actions.append(f"{ref}: incomplete (no CV/summary) - check the folder by hand")
            continue
        if props.get("tracker") != "1":
            actions.append(f"{ref}: add tracker row")
            if not dry_run:
                ensure_tracker_row(store, folder)
        if props.get("notified") != "1" or props.get("acked") != "1":
            actions.append(f"{ref}: send missing email(s)")
            if not dry_run:
                _notify(store, folder, None)
    return actions
