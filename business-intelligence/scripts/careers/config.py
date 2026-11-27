"""
goji-careers configuration: env vars, form option lists, tracker layout.

Everything that differs between test and production is an environment variable,
set from the env block of .github/workflows/deploy-careers.yml, so the same
code runs against the TEST folder/tracker until go-live.
"""
from __future__ import annotations

import os


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


# ---- where applications go ---------------------------------------------------
APPLICATIONS_FOLDER_ID = _env("RECRUITMENT_APPLICATIONS_FOLDER_ID")  # CVs (one flat folder)
TRACKER_SHEET_ID = _env("RECRUITMENT_TRACKER_SHEET_ID")              # the "database"
TRACKER_TAB = _env("RECRUITMENT_TRACKER_TAB", "Applicants")

# ---- web -----------------------------------------------------------------------
CORS_ORIGINS = [o.strip() for o in _env(
    "CORS_ORIGIN", "https://www.gojiphysio.com").split(",") if o.strip()]
VACANCIES_URL = _env("VACANCIES_URL", "https://www.gojiphysio.com/careers/vacancies.json")

# ---- email (Gmail SMTP as hello@, the same app password booking uses) ---------
SMTP_USER = _env("SMTP_USER", "hello@gojiphysio.com")
SMTP_PASS = os.environ.get("GMAIL_APP_PASSWORD")  # Secret Manager
ADMIN_TO = _env("CAREERS_ADMIN_EMAIL", "hello@gojiphysio.com")
CONTACT_EMAIL = "hello@gojiphysio.com"
# Test mode sends the applicant's confirmation to TEST_EMAIL instead. With no
# TEST_EMAIL it sends no confirmation at all (fails closed).
TEST_MODE = _env("CAREERS_TEST_MODE").lower() in ("1", "true", "yes", "on")
TEST_EMAIL = _env("CAREERS_TEST_EMAIL")

# ---- bot checks ------------------------------------------------------------------
TURNSTILE_SECRET = _env("TURNSTILE_SECRET")  # empty = Turnstile not enforced
MIN_FILL_MS = int(_env("CAREERS_MIN_FILL_MS", "8000"))

MAX_CV_BYTES = 10 * 1024 * 1024
MAX_CERT_BYTES = 10 * 1024 * 1024   # all Pilates certificates together
MAX_CERTS = 3
PRIVACY_NOTICE_VERSION = _env("PRIVACY_NOTICE_VERSION", "2026-11-draft")
RETENTION_REVIEW_DAYS = 180
APP_ID_PREFIX = "GOJI-APP"

GENERAL_ID = "general"
GENERAL_TITLE = "General expression of interest"

# ---- form option lists (must match marketing/website/src/lib/vacancies.ts) ----
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

# Freelance Pilates instructor (form "pilates"). Must match the lists of the
# same purpose in marketing/website/src/lib/vacancies.ts.
WORK_ELIGIBILITY_OPTIONS = ["Singapore Citizen or Permanent Resident",
                            "I hold a pass that allows me to work in Singapore",
                            "I would need a pass to work in Singapore"]
APPARATUS_OPTIONS = ["Mat", "Reformer", "Cadillac / Trapeze Table", "Chair", "Barrels", "Others"]
TEACHING_YEARS_OPTIONS = ["Less than 1 year", "1 to 2 years", "3 to 5 years", "6 to 10 years",
                          "More than 10 years"]
TEACHING_EXPERIENCE_OPTIONS = ["Private 1:1", "Duet 2:1", "Group Pilates", "Prenatal",
                               "Postnatal", "Others"]
ALL_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
TIME_WINDOWS = ["Morning", "Afternoon", "Evening"]

# ---- tracker layout ----------------------------------------------------------------
# The live sheet's header row, in order. "manual" columns are written blank
# (or with a starting value) and then belong to the reviewers. Add new columns
# at the END, here and in the sheet, in the same change. Removing one means
# deleting it from the live sheets as the deploy lands (rows are positional).
TRACKER_COLUMNS = [
    "Application ID",
    "Date and time received (Asia/Singapore)",
    "Application type",
    "Role applied for",
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
    "Retention review date",               # provisional; the reviewer updates it
    # Freelance Pilates instructor answers (added 2026-11-26). Blank for other
    # roles. Pilates rows also reuse "Preferred working days", "Additional
    # certifications", "Earliest available start date" and "Personal
    # introduction", and record "Freelance" as the employment preference.
    "Singapore work eligibility",
    "Pilates certification and training provider",
    "Apparatus qualifications",
    "Years of teaching experience",
    "Relevant teaching experience",
    "Preferred time windows",
    "Approximate weekly availability",
    "Current teaching commitments",
    "Pilates certificate links",
    "Portfolio / social media profile",
]
