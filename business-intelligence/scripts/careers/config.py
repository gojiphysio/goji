"""
goji-careers configuration: env vars, form option lists, tracker layout.

Everything that differs between test and production is an environment
variable, so the same image runs against the test folder/tracker until the
production integration is approved (README.md "Test mode").
"""
from __future__ import annotations

import os


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _flag(name: str) -> bool:
    return _env(name).lower() in ("1", "true", "yes", "on")


# ---- Google Workspace ------------------------------------------------------
# Folder that holds the per-year application folders ("Applications").
APPLICATIONS_FOLDER_ID = _env("RECRUITMENT_APPLICATIONS_FOLDER_ID")
# The "Goji Recruitment — Applicant Tracker" spreadsheet and its tab.
TRACKER_SHEET_ID = _env("RECRUITMENT_TRACKER_SHEET_ID")
TRACKER_TAB = _env("RECRUITMENT_TRACKER_TAB", "Applicants")
# How the service authenticates to Google:
#   service_account  (default) Application Default Credentials, i.e. the Cloud
#                    Run runtime service account. Needs a Shared Drive (a
#                    service account has no My Drive storage of its own).
#   oauth            A refresh token for hello@gojiphysio.com in
#                    GOOGLE_OAUTH_CLIENT_JSON (Secret Manager), for when the
#                    recruitment folder has to live in hello@'s My Drive.
GOOGLE_AUTH_MODE = _env("GOOGLE_AUTH_MODE", "service_account")
GOOGLE_OAUTH_CLIENT_JSON = _env("GOOGLE_OAUTH_CLIENT_JSON")

# ---- Website / vacancies ---------------------------------------------------
CORS_ORIGINS = [o.strip() for o in _env(
    "CORS_ORIGIN", "https://www.gojiphysio.com").split(",") if o.strip()]
# The site's machine-readable vacancy list (built from src/lib/vacancies.ts).
VACANCIES_URL = _env("VACANCIES_URL", "https://www.gojiphysio.com/careers/vacancies.json")
VACANCIES_TTL_S = float(_env("VACANCIES_TTL_S", "300"))
CAREERS_PAGE_URL = _env("CAREERS_PAGE_URL", "https://www.gojiphysio.com/careers/")

# ---- Email -----------------------------------------------------------------
SMTP_HOST = _env("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(_env("SMTP_PORT", "587"))
SMTP_USER = _env("SMTP_USER", "hello@gojiphysio.com")
SMTP_PASS = os.environ.get("GMAIL_APP_PASSWORD")  # Secret Manager
ADMIN_TO = _env("CAREERS_ADMIN_EMAIL", "hello@gojiphysio.com")
FROM_NAME = _env("CAREERS_FROM_NAME", "Goji Physiotherapy")
CONTACT_EMAIL = "hello@gojiphysio.com"
# Test mode: applicant acknowledgements go to CAREERS_TEST_EMAIL instead of
# the address on the form. Fails closed: test mode with no test address sends
# no acknowledgement at all, so a test run can never email a real candidate.
TEST_MODE = _flag("CAREERS_TEST_MODE")
TEST_EMAIL = _env("CAREERS_TEST_EMAIL")

# ---- Abuse controls ----------------------------------------------------------
TURNSTILE_SECRET = _env("TURNSTILE_SECRET")
MIN_FILL_MS = int(_env("CAREERS_MIN_FILL_MS", "8000"))
PER_IP_PER_HOUR = int(_env("CAREERS_PER_IP_PER_HOUR", "6"))
PER_EMAIL_PER_DAY = int(_env("CAREERS_PER_EMAIL_PER_DAY", "3"))

# ---- Files -------------------------------------------------------------------
MAX_CV_BYTES = 10 * 1024 * 1024
# Whole request: the CV plus the text fields.
MAX_REQUEST_BYTES = MAX_CV_BYTES + 256 * 1024

# ---- Records -----------------------------------------------------------------
PRIVACY_NOTICE_VERSION = _env("PRIVACY_NOTICE_VERSION", "2026-11-draft")
# Provisional retention review date written at submission (received + N days).
# Reviewers move it when the process concludes (6 months after, or 12 months
# for talent-pool opt-ins) - see RETENTION.md. Nothing is deleted
# automatically.
RETENTION_REVIEW_DAYS = int(_env("RETENTION_REVIEW_DAYS", "180"))
APP_ID_PREFIX = "GOJI-APP"

GENERAL_ID = "general"
GENERAL_TITLE = "General expression of interest"
GENERAL_FOLDER = "General Expressions of Interest"

# Form option lists. Keep in sync with src/lib/vacancies.ts on the website.
AHPC_OPTIONS = ["Fully registered", "Conditionally registered",
                "Registration pending", "Not currently registered"]
TRAINING_OPTIONS = ["Clinical Pilates", "Mat or reformer Pilates", "Dry needling",
                    "Women's health / Pelvic health", "Pre- and post-natal rehabilitation",
                    "Strength and conditioning", "Sports rehabilitation", "Other"]
INTEREST_AREAS = ["Physiotherapy", "Women's health physiotherapy", "Clinical leadership",
                  "Pilates instruction", "Clinic operations",
                  "Administration and patient care", "Something else"]
HEARD_ABOUT_OPTIONS = ["LinkedIn", "JobStreet", "Instagram", "Goji website",
                       "Someone I know at Goji", "Other"]
WORKING_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
EMPLOYMENT = {"full-time": "Full-time", "part-time": "Part-time", "either": "Open to both"}

RECRUITMENT_STATUSES = ["New", "Under Review", "Shortlisted", "Interview Scheduled",
                        "Interviewed", "Offer Extended", "Hired", "Not Progressing",
                        "Talent Pool", "Withdrawn"]
ASSESSED_LEVELS = ["Physiotherapist", "Senior Physiotherapist", "Not yet assessed", "Other"]

# Tracker columns, in order. The service only ever APPENDS a new row; it never
# rewrites an existing one, so everything a reviewer maintains by hand
# (status, reviewer, interview date, notes, assessed level) is never touched.
# Columns marked "manual" are written blank (or with their initial value) once.
TRACKER_COLUMNS = [
    "Application ID",
    "Date and time received (Asia/Singapore)",
    "Application type",
    "Role applied for",
    "Open to alternative seniority level",
    "Assessed seniority level",            # manual
    "Interest area (general)",
    "Clinic location",
    "Full name",
    "Email",
    "Mobile number",
    "Employment preference",
    "Days available per week",
    "Preferred working days",
    "Actual years of clinical experience",
    "AHPC registration status",
    "Clinical experience",
    "Women's health experience or interest",
    "Additional certifications",
    "Earliest available start date",
    "Personal introduction",
    "LinkedIn profile",
    "How they heard about Goji",
    "Application source",
    "CV link",
    "Application folder link",
    "Recruitment status",                  # manual (starts "New")
    "Assigned reviewer",                   # manual
    "Last updated",                        # manual
    "Interview date",                      # manual
    "Internal notes",                      # manual
    "Privacy notice version",
    "Privacy acknowledgement timestamp",
    "Talent pool consent",
    "Retention review date",               # manual after submission
]
