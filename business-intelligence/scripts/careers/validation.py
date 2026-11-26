"""
Server-side validation of the application form.

`parse_application(form, vacancy)` returns `(application, errors)`. `errors`
maps a form field name to a message the website shows beside that field; an
empty dict means the application is valid. Every value is coerced, trimmed,
length-capped and checked against the option lists in config.py. Nothing an
applicant answers ever rejects them on its own (e.g. 2 days/week on a 3-day
role is recorded and flagged for review, not refused): the checks are only
about the data being well-formed and complete.
"""
from __future__ import annotations

import re
import uuid

from . import config
from .vacancies import Vacancy

EMAIL_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}"
                      r"[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$")
LINKEDIN_RE = re.compile(r"^https://([a-z]{2,3}\.)?linkedin\.com/[A-Za-z0-9_\-/%.]+/?$")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f  ]")

INTRO_MIN, INTRO_MAX = 30, 3000


def _text(form, name: str, max_len: int, multiline: bool = False) -> str:
    v = str(form.get(name) or "")
    v = _CONTROL.sub("", v)
    if not multiline:
        v = re.sub(r"[\r\n\t]+", " ", v)
    else:
        v = v.replace("\r\n", "\n").replace("\r", "\n")
        v = re.sub(r"\n{3,}", "\n\n", v)
    return v.strip()[:max_len]


def _choice(form, name: str, options: dict) -> str | None:
    v = str(form.get(name) or "").strip()
    return v if v in options else None


def _multi(form, name: str, options: dict) -> list[str]:
    raw = form.getlist(name) if hasattr(form, "getlist") else (form.get(name) or [])
    if isinstance(raw, str):
        raw = [raw]
    seen: list[str] = []
    for v in raw:
        v = str(v).strip()
        if v in options and v not in seen:
            seen.append(v)
    return seen


def _bool(form, name: str) -> bool:
    return str(form.get(name) or "").strip().lower() in ("1", "true", "yes", "on")


def normalise_phone(raw: str) -> str | None:
    """'+65 9123 4567' -> '+65 9123 4567' (kept as typed, minus junk) when it
    has a leading + country code and 8-15 digits; None otherwise."""
    raw = (raw or "").strip()
    if raw.startswith("00"):
        raw = "+" + raw[2:]
    if not raw.startswith("+") or re.search(r"[^\d ()+.-]", raw):
        return None
    digits = re.sub(r"\D", "", raw)
    if not 8 <= len(digits) <= 15 or digits.startswith("0"):
        return None
    cleaned = "+" + re.sub(r"[^\d ()-]", "", raw[1:]).strip()
    return re.sub(r"\s+", " ", cleaned)[:24]


def is_physio_application(vacancy: Vacancy, role_category: str | None) -> bool:
    if vacancy.is_general:
        return role_category == "physiotherapy"
    return vacancy.form == "physio"


def parse_application(form, vacancy: Vacancy) -> tuple[dict, dict]:
    errors: dict[str, str] = {}
    app: dict = {}

    sid = str(form.get("submission_id") or "").strip()
    try:
        app["submission_id"] = str(uuid.UUID(sid, version=4))
        if app["submission_id"] != sid.lower():
            raise ValueError
    except ValueError:
        errors["submission_id"] = "Please reload the page and try again."

    app["full_name"] = _text(form, "full_name", 100)
    if len(app["full_name"]) < 2:
        errors["full_name"] = "Please enter your full name."

    email = _text(form, "email", 254).lower()
    if not EMAIL_RE.match(email) or ".." in email:
        errors["email"] = "Please enter a valid email address, like name@example.com."
    app["email"] = email

    phone = normalise_phone(_text(form, "phone", 40))
    if not phone:
        errors["phone"] = "Please enter your mobile number with its country code, like +65 9123 4567."
    app["phone"] = phone or ""

    # Role. A vacancy fixes it; an expression of interest names a role type.
    if vacancy.is_general:
        cat = _choice(form, "role_category", config.ROLE_CATEGORIES)
        if not cat:
            errors["role_category"] = "Please choose the type of role you're interested in."
        app["role_category"] = cat
        app["role_interest"] = _text(form, "role_interest", 120)
        label = config.ROLE_CATEGORIES.get(cat or "", "")
        app["role"] = f"{label} (expression of interest)" if label else "Expression of interest"
        if app["role_interest"]:
            app["role"] = f"{label}: {app['role_interest']} (expression of interest)"
    else:
        app["role_category"] = None
        app["role_interest"] = ""
        app["role"] = vacancy.title
    app["job_id"] = vacancy.id
    app["application_type"] = "expression_of_interest" if vacancy.is_general else "vacancy"
    app["location"] = vacancy.location

    pref = _choice(form, "employment_pref", config.EMPLOYMENT)
    if not pref:
        errors["employment_pref"] = "Please choose full-time, part-time or open to both."
    app["employment_pref"] = pref

    app["days_per_week"] = None
    app["available_days"] = _multi(form, "available_days", config.DAYS)
    if pref in ("part_time", "either"):
        raw = str(form.get("days_per_week") or "").strip()
        if raw.isdigit() and 1 <= int(raw) <= 6:
            app["days_per_week"] = int(raw)
        else:
            errors["days_per_week"] = "Please tell us how many days a week you're available (1 to 6)."
    # Recorded for the reviewer, never used to reject.
    app["below_min_days"] = bool(
        vacancy.min_days and app["days_per_week"] is not None
        and app["days_per_week"] < vacancy.min_days)

    yrs = _choice(form, "years_experience", config.YEARS)
    if not yrs:
        errors["years_experience"] = "Please choose your years of relevant experience."
    app["years_experience"] = yrs

    app["start_availability"] = _text(form, "start_availability", 120)
    if len(app["start_availability"]) < 2:
        errors["start_availability"] = "Please tell us your earliest start date or notice period."

    app["intro"] = _text(form, "intro", INTRO_MAX, multiline=True)
    if len(app["intro"]) < INTRO_MIN:
        errors["intro"] = f"Please write at least {INTRO_MIN} characters about yourself."

    physio = is_physio_application(vacancy, app.get("role_category"))
    app["is_physio"] = physio
    app["ahpc_status"] = _choice(form, "ahpc_status", config.AHPC)
    app["clinical_areas"] = _multi(form, "clinical_areas", config.CLINICAL_AREAS)
    app["clinical_areas_other"] = _text(form, "clinical_areas_other", 200)
    if physio:
        if not app["ahpc_status"]:
            errors["ahpc_status"] = "Please choose your AHPC registration status."
        if not app["clinical_areas"]:
            errors["clinical_areas"] = "Please choose at least one area of clinical experience."
    else:
        app["ahpc_status"] = None
        app["clinical_areas"] = []
        app["clinical_areas_other"] = ""

    # Optional.
    app["womens_health"] = _text(form, "womens_health", 1000, multiline=True)
    app["certifications"] = _multi(form, "certifications", config.CERTIFICATIONS)
    app["certifications_other"] = _text(form, "certifications_other", 200)
    linkedin = _text(form, "linkedin", 200)
    if linkedin and not LINKEDIN_RE.match(linkedin):
        errors["linkedin"] = "Please paste the full link to your LinkedIn profile, starting https://"
    app["linkedin"] = linkedin
    app["how_heard"] = _choice(form, "how_heard", config.HEARD)

    if not _bool(form, "privacy_ack"):
        errors["privacy_ack"] = "Please confirm you've read the recruitment privacy notice."
    app["privacy_ack"] = True
    app["talent_pool"] = _bool(form, "talent_pool")

    # Campaign attribution (non-identifying; from the landing URL's utm_*).
    app["attribution"] = {
        k: _text(form, k, 100) for k in ("utm_source", "utm_medium", "utm_campaign", "utm_content")
        if _text(form, k, 100)
    }
    return app, errors
