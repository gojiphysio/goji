"""
Careers-service config: environment settings plus the form's option lists.

The option lists mirror the website's `marketing/website/src/lib/careers.ts`
(`CAREERS_OPTIONS`); keep the two in sync. The backend is the authority: a
value that isn't listed here is rejected, whatever the browser sent.

Nothing here is secret. Secrets (the Google OAuth refresh token, the Gmail app
password, the Turnstile secret) come from Secret Manager as env vars and are
read where they are used.
"""
from __future__ import annotations

import os
from datetime import timedelta, timezone

SGT = timezone(timedelta(hours=8), "Asia/Singapore")


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


# ---- Where applications are stored (Google Drive / Sheets) -----------------
# IDs printed by `python -m careers.admin setup`. Use the TEST pair until the
# production integration is approved (see README "Go-live").
DRIVE_ROOT_ID = _env("CAREERS_DRIVE_ROOT_ID")          # "Goji Recruitment"
DRIVE_APPLICATIONS_ID = _env("CAREERS_DRIVE_APPLICATIONS_ID")  # ".../Applications"
TRACKER_ID = _env("CAREERS_TRACKER_ID")                # the Applicant Tracker sheet
TRACKER_TAB = _env("CAREERS_TRACKER_TAB", "Applicants")

# Google OAuth client + hello@'s refresh token (scope: drive.file only).
GOOGLE_CLIENT_ID = _env("CAREERS_GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = _env("CAREERS_GOOGLE_CLIENT_SECRET")
GOOGLE_REFRESH_TOKEN = _env("CAREERS_GOOGLE_REFRESH_TOKEN")

# ---- Web ------------------------------------------------------------------
CORS_ORIGIN = _env("CORS_ORIGIN", "https://www.gojiphysio.com")
# Extra allowed origins, comma-separated (a Cloudflare preview for testing).
EXTRA_ORIGINS = [o.strip() for o in _env("CAREERS_EXTRA_ORIGINS").split(",") if o.strip()]
ALLOWED_ORIGINS = {CORS_ORIGIN, *EXTRA_ORIGINS}
VACANCIES_URL = _env("CAREERS_VACANCIES_URL",
                     "https://www.gojiphysio.com/careers/vacancies.json")
VACANCIES_TTL_S = float(_env("CAREERS_VACANCIES_TTL", "300"))

# ---- Abuse limits ---------------------------------------------------------
# In-memory, which is enough with --max-instances=1 (same as goji-booking).
ATTEMPTS_PER_IP_HOUR = int(_env("CAREERS_ATTEMPTS_PER_IP_HOUR", "20"))
APPLICATIONS_PER_EMAIL_DAY = int(_env("CAREERS_APPLICATIONS_PER_EMAIL_DAY", "3"))
MIN_FILL_MS = int(_env("CAREERS_MIN_FILL_MS", "5000"))

# ---- Email ----------------------------------------------------------------
SMTP_HOST = _env("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(_env("SMTP_PORT", "587"))
SMTP_USER = _env("SMTP_USER", "hello@gojiphysio.com")
ADMIN_EMAIL = _env("CAREERS_ADMIN_EMAIL", "hello@gojiphysio.com")
FROM_NAME = _env("CAREERS_FROM_NAME", "Goji Physiotherapy")
# Test mode: applicant acknowledgements go to CAREERS_TEST_RECIPIENT instead of
# the applicant. Fails closed: test mode with no recipient sends no
# acknowledgement at all, so a test can never email a real candidate.
TEST_MODE = _env("CAREERS_TEST_MODE").lower() in ("1", "true", "yes")
TEST_RECIPIENT = _env("CAREERS_TEST_RECIPIENT")

# ---- Privacy / retention ---------------------------------------------------
# Bump PRIVACY_NOTICE_VERSION whenever the notice beside the form changes, in
# the same PR as the website's PRIVACY_NOTICE_VERSION in careers.ts.
PRIVACY_NOTICE_VERSION = "2026-11-v1"
# Proposed operational periods (not statutory); the tracker's "Retention review
# date" is set from these. Nothing is deleted automatically.
RETENTION_MONTHS = int(_env("CAREERS_RETENTION_MONTHS", "6"))
TALENT_POOL_RETENTION_MONTHS = int(_env("CAREERS_TALENT_POOL_RETENTION_MONTHS", "12"))

# ---- CV upload --------------------------------------------------------------
MAX_CV_BYTES = 10 * 1024 * 1024
# Whole request cap (CV + form fields). Flask returns 413 above it.
MAX_REQUEST_BYTES = MAX_CV_BYTES + 512 * 1024

# ---- Form options (mirror careers.ts CAREERS_OPTIONS) ------------------------
GENERAL_JOB_ID = "general"
GENERAL_DRIVE_FOLDER = "General Expressions of Interest"

EMPLOYMENT = {"full_time": "Full-time", "part_time": "Part-time", "either": "Open to both"}
YEARS = {
    "0-2": "Less than 3 years",
    "3-5": "3-5 years",
    "6-10": "6-10 years",
    "10+": "More than 10 years",
}
AHPC = {
    "full": "Fully registered",
    "conditional": "Conditionally registered",
    "pending": "Registration pending",
    "none": "Not currently registered",
}
CLINICAL_AREAS = {
    "msk": "Musculoskeletal / orthopaedic",
    "sports": "Sports injuries",
    "womens_health": "Women's health / pelvic health",
    "antenatal_postnatal": "Pregnancy and postnatal",
    "paediatrics": "Paediatrics",
    "neuro": "Neurological",
    "cardioresp": "Cardiorespiratory",
    "older_adults": "Older adults / falls",
    "vestibular": "Vestibular",
    "post_surgical": "Post-surgical rehabilitation",
    "other": "Other",
}
CERTIFICATIONS = {
    "clinical_pilates": "Clinical Pilates",
    "mat_reformer_pilates": "Mat or reformer Pilates",
    "dry_needling": "Dry needling",
    "womens_pelvic": "Women's health / Pelvic health",
    "pre_post_natal": "Pre- and post-natal rehabilitation",
    "strength_conditioning": "Strength and conditioning",
    "sports_rehab": "Sports rehabilitation",
    "other": "Other",
}
DAYS = {"mon": "Mon", "tue": "Tue", "wed": "Wed", "thu": "Thu", "fri": "Fri", "sat": "Sat"}
HEARD = {
    "linkedin": "LinkedIn",
    "jobstreet": "JobStreet",
    "instagram": "Instagram",
    "website": "Goji website",
    "referral": "Friend or colleague",
    "other": "Other",
}
ROLE_CATEGORIES = {
    "physiotherapy": "Physiotherapy",
    "pilates": "Pilates instruction",
    "operations": "Clinic operations",
    "patient_care": "Administration and patient care",
    "other": "Other",
}
