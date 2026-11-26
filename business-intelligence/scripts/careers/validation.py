"""
Server-side validation for applications and CVs. Everything from the browser
is untrusted: the form's own checks are a convenience, these are the rules.
Pure functions (no Flask, no Google), so they are easy to test.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from . import config

EMAIL_RE = re.compile(r"^[^\s@<>(),;:\"\\\[\]]+@[^\s@<>(),;:\"\\\[\]]+\.[A-Za-z]{2,63}$")
PHONE_CHARS = re.compile(r"^\+?[\d\s().\-]+$")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f​-‏‪-‮⁦-⁩]")

CONTENT_TYPES = {
    "pdf": "application/pdf",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class FileRejected(ValueError):
    """The CV failed a safety or format check. `str(e)` is safe to show."""


@dataclass
class Result:
    data: dict = field(default_factory=dict)
    errors: dict = field(default_factory=dict)

    def fail(self, name: str, msg: str) -> None:
        self.errors.setdefault(name, msg)


# ---- text helpers ------------------------------------------------------------

def clean_line(value, max_len: int) -> str:
    """One-line text: NFC, no control/bidi characters, no newlines, trimmed."""
    s = unicodedata.normalize("NFC", str(value or ""))
    s = _CONTROL.sub("", s).replace("\r", " ").replace("\n", " ").replace("\t", " ")
    return re.sub(r" {2,}", " ", s).strip()[:max_len]


def clean_text(value, max_len: int) -> str:
    """Multi-line text: keeps newlines, drops other control characters."""
    s = unicodedata.normalize("NFC", str(value or "")).replace("\r\n", "\n").replace("\r", "\n")
    s = _CONTROL.sub("", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()[:max_len]


def normalise_phone(raw: str) -> str:
    """Singapore numbers may skip +65: eight digits (or 65 + eight) become
    "+65 9123 4567". Anything else with 8 to 15 digits is kept as typed, so
    overseas applicants can enter their own format. Returns "" if invalid."""
    if not PHONE_CHARS.match(raw):
        return ""
    digits = re.sub(r"\D", "", raw)
    if not raw.startswith("+"):
        if len(digits) == 10 and digits.startswith("65"):
            digits = digits[2:]
        if len(digits) == 8:
            return f"+65 {digits[:4]} {digits[4:]}"
    return raw if 8 <= len(digits) <= 15 else ""


def file_ext(name: str) -> str:
    base = re.split(r"[\\/]", str(name or ""))[-1]
    return base.rsplit(".", 1)[-1].lower() if "." in base else ""


# ---- file check ------------------------------------------------------------------
# Extension, size and the file's real signature must agree on PDF, DOC or DOCX.
# Deeper content scanning is left to Google Drive, which virus-scans uploads,
# and CVs are only opened by signed-in reviewers in Drive's viewer.
_MAGIC = {"pdf": b"%PDF-", "docx": b"PK\x03\x04",
          "doc": b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"}


def check_cv(filename: str, data: bytes) -> str:
    """Validate an uploaded CV. Returns the extension, or raises FileRejected
    with a message that is safe to show the candidate."""
    ext = file_ext(filename)
    if ext not in _MAGIC:
        raise FileRejected("Upload your CV as a PDF, DOC or DOCX file.")
    if not data:
        raise FileRejected("This file is empty. Please choose another.")
    if len(data) > config.MAX_CV_BYTES:
        raise FileRejected("Please upload a CV of 10MB or less.")
    # PDFs may carry a few junk bytes before the header; Office files may not.
    ok = _MAGIC["pdf"] in data[:1024] if ext == "pdf" else data.startswith(_MAGIC[ext])
    if not ok:
        raise FileRejected("This file doesn't look like a valid "
                           f"{ext.upper()}. Please export it again or upload a PDF.")
    return ext


# ---- form ----------------------------------------------------------------------------

def _one_of(value: str, options: list[str]) -> str:
    return value if value in options else ""


def validate_form(form, vacancy: dict | None, general: bool) -> Result:
    """Validate the text fields. `form` is a MultiDict-like (get/getlist).
    `vacancy` is the open vacancy (None for a general expression of interest).
    Returns normalised data plus per-field errors (messages safe to show)."""
    r = Result()
    g = lambda k, n=200: clean_line(form.get(k), n)  # noqa: E731
    d = r.data

    d["full_name"] = g("full_name", 120)
    if len(d["full_name"]) < 2:
        r.fail("full_name", "Enter your full name.")

    email = clean_line(form.get("email"), 254)
    if not EMAIL_RE.match(email):
        r.fail("email", "Enter a valid email address, like name@example.com.")
    d["email"] = email

    phone = normalise_phone(g("phone", 25))
    if not phone:
        r.fail("phone", "Enter a valid mobile number, for example 9123 4567.")
    d["phone"] = phone or ""

    emp = g("employment", 20)
    if emp not in config.EMPLOYMENT:
        r.fail("employment", "Choose full-time, part-time or open to both.")
    d["employment"] = config.EMPLOYMENT.get(emp, "")

    days = g("days_per_week", 2)
    if emp in ("part-time", "either"):
        if days not in [str(n) for n in range(1, 7)]:
            r.fail("days_per_week", "Choose how many days per week you're available.")
        d["days_per_week"] = days if days.isdigit() else ""
    else:
        d["days_per_week"] = ""
    d["preferred_days"] = [x for x in config.WORKING_DAYS if x in form.getlist("preferred_days")]

    years_raw = g("years_experience", 10)
    try:
        years = float(years_raw)
        if not 0 <= years <= 50 or years != years:
            raise ValueError
        d["years_experience"] = int(years) if years.is_integer() else round(years, 1)
    except ValueError:
        r.fail("years_experience", "Enter your years of experience as a number between 0 and 50.")
        d["years_experience"] = ""

    d["start_availability"] = g("start_availability", 120)
    if not d["start_availability"]:
        r.fail("start_availability", "Tell us your earliest start date or notice period.")

    d["intro"] = clean_text(form.get("intro"), 2000)
    if not d["intro"]:
        r.fail("intro", "Write a brief introduction.")
    elif len(clean_text(form.get("intro"), 5000)) > 2000:
        r.fail("intro", "Keep the introduction to 2,000 characters or fewer.")

    d["training"] = [x for x in config.TRAINING_OPTIONS if x in form.getlist("training")]
    d["training_other"] = g("training_other", 200) if "Other" in d["training"] else ""

    linkedin = g("linkedin", 300)
    if linkedin and not re.match(r"^https?://[^\s<>\"']+$", linkedin, re.I):
        r.fail("linkedin", "Enter a full web address starting with https://.")
    d["linkedin"] = linkedin if "linkedin" not in r.errors else ""

    d["heard_about"] = _one_of(g("heard_about", 40), config.HEARD_ABOUT_OPTIONS)

    if (form.get("privacy_ack") or "") != "yes":
        r.fail("privacy_ack", "Please confirm you have read the recruitment privacy notice.")
    d["talent_pool"] = (form.get("talent_pool") or "") == "yes"

    physio = bool(vacancy) and vacancy.get("form") == "physio"
    if physio:
        d["ahpc_status"] = _one_of(g("ahpc_status", 40), config.AHPC_OPTIONS)
        if not d["ahpc_status"]:
            r.fail("ahpc_status", "Choose your AHPC registration status.")
        d["clinical_experience"] = clean_text(form.get("clinical_experience"), 600)
        if not d["clinical_experience"]:
            r.fail("clinical_experience", "Tell us your main areas of clinical experience.")
        d["womens_health"] = clean_text(form.get("womens_health"), 600)
    else:
        d["ahpc_status"] = d["clinical_experience"] = d["womens_health"] = ""

    if general:
        d["interest_area"] = _one_of(g("interest_area", 60), config.INTEREST_AREAS)
        if not d["interest_area"]:
            r.fail("interest_area", "Choose the kind of role you're interested in.")
        d["interest_detail"] = g("interest_detail", 200)
    else:
        d["interest_area"] = d["interest_detail"] = ""

    # Non-identifying campaign attribution, for the tracker's source column.
    d["utm"] = {k: g(k, 100) for k in ("utm_source", "utm_medium", "utm_campaign", "utm_content")
                if g(k, 100)}
    d["source_page"] = g("source_page", 120)
    return r
