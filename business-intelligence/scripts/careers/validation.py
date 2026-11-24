"""
Server-side validation for applications and CV files.

Everything from the browser is untrusted: the form's own checks are a
convenience, these are the rules. Pure functions (no Flask, no Google) so they
are unit-testable on their own.

File safety (recruitment brief §6): the extension, the declared MIME type and
the file's real signature must all agree on PDF, DOC or DOCX, and the file
must not carry active content (PDF JavaScript/launch actions/embedded files,
Office macros, ActiveX, OLE embeddings, remote templates). Anything else is
rejected, never "cleaned". Google Drive additionally virus-scans every upload,
and CVs are only ever opened by signed-in reviewers in Drive's viewer.
"""
from __future__ import annotations

import io
import re
import unicodedata
import zipfile
import zlib
from dataclasses import dataclass, field

from . import config

EMAIL_RE = re.compile(r"^[^\s@<>(),;:\"\\\[\]]+@[^\s@<>(),;:\"\\\[\]]+\.[A-Za-z]{2,63}$")
PHONE_RE = re.compile(r"^\+[\d\s()\-]{7,24}$")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f​-‏‪-‮⁦-⁩]")

ALLOWED = {
    "pdf": {"application/pdf", "application/x-pdf", "application/octet-stream"},
    "doc": {"application/msword", "application/octet-stream"},
    "docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document",
             "application/zip", "application/octet-stream"},
}
CONTENT_TYPES = {
    "pdf": "application/pdf",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


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


def sanitise_filename(name: str) -> str:
    """A display-safe version of the uploaded filename (kept only for the
    summary; the stored file is always named <application id>-CV.<ext>)."""
    base = re.split(r"[\\/]", str(name or ""))[-1]
    base = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode()
    base = re.sub(r"[^A-Za-z0-9._ -]+", "_", base).strip(" ._")
    base = re.sub(r"_+", "_", re.sub(r" {2,}", " ", base))
    return (base or "cv")[:100]


def file_ext(name: str) -> str:
    base = re.split(r"[\\/]", str(name or ""))[-1]
    return base.rsplit(".", 1)[-1].lower() if "." in base else ""


# ---- file checks -----------------------------------------------------------------

_PDF_BAD_NAMES = {b"javascript", b"js", b"launch", b"embeddedfile", b"embeddedfiles",
                  b"richmedia", b"submitform", b"importdata", b"gotoe"}
_PDF_NAME = re.compile(rb"/([A-Za-z0-9#]{2,40})")
_PDF_STREAM = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.S)


def _pdf_names(blob: bytes):
    for m in _PDF_NAME.finditer(blob):
        raw = m.group(1)
        # Undo #xx hex escapes, the classic way to hide /JavaScript as /J#61vaScript.
        try:
            name = re.sub(rb"#([0-9A-Fa-f]{2})", lambda h: bytes([int(h.group(1), 16)]), raw)
        except ValueError:
            name = raw
        yield name.lower()


def _check_pdf(data: bytes) -> None:
    if b"%PDF-" not in data[:1024]:
        raise FileRejected("This doesn't look like a valid PDF file.")
    if b"%%EOF" not in data[-2048:]:
        raise FileRejected("This PDF appears to be incomplete. Please export it again.")
    chunks = [data]
    # Dictionaries can hide inside compressed object streams; inflate them
    # (bounded, so a decompression bomb can't exhaust memory).
    budget = 60 * 1024 * 1024
    for m in _PDF_STREAM.finditer(data):
        if budget <= 0:
            break
        try:
            d = zlib.decompressobj()
            out = d.decompress(m.group(1), min(budget, 20 * 1024 * 1024))
            budget -= len(out)
            if b"/" in out:
                chunks.append(out)
        except zlib.error:
            continue
    for chunk in chunks:
        for name in _pdf_names(chunk):
            if name in _PDF_BAD_NAMES:
                raise FileRejected("This PDF contains interactive or embedded content we can't accept. "
                                   "Please save it as a plain PDF (Print to PDF works) and try again.")


_DOCX_BAD_PARTS = ("vbaproject.bin", "/activex/", "vbadata.xml", "/embeddings/")
_EXTERNAL_REL = re.compile(rb"<Relationship\b[^>]*TargetMode=\"External\"[^>]*>", re.I)
_REL_TYPE = re.compile(rb"Type=\"([^\"]+)\"", re.I)


def _check_docx(data: bytes) -> None:
    if not data.startswith(b"PK\x03\x04"):
        raise FileRejected("This doesn't look like a valid DOCX file.")
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        infos = zf.infolist()
    except zipfile.BadZipFile:
        raise FileRejected("This DOCX file appears to be damaged. Please export it again.")
    if len(infos) > 2000 or sum(i.file_size for i in infos) > 150 * 1024 * 1024:
        raise FileRejected("This DOCX file is unusually large inside. Please save it as a PDF instead.")
    names = [i.filename.lower() for i in infos]
    if "[content_types].xml" not in names or "word/document.xml" not in names:
        raise FileRejected("This doesn't look like a Word document.")
    for n in names:
        if any(bad in "/" + n for bad in _DOCX_BAD_PARTS):
            raise FileRejected("This document contains macros or embedded objects we can't accept. "
                               "Please save it as a PDF or a plain .docx and try again.")
    ctypes = zf.read("[Content_Types].xml").lower()
    if b"macroenabled" in ctypes or b"vbaproject" in ctypes:
        raise FileRejected("Macro-enabled documents can't be accepted. Please save it as a PDF.")
    # External relationships: hyperlinks are fine (a LinkedIn link in a CV);
    # anything else external (remote templates, OLE links, frames) is a known
    # way to make Word fetch and run content when the file is opened.
    for n in names:
        if not n.endswith(".rels"):
            continue
        for rel in _EXTERNAL_REL.findall(zf.read(n)):
            t = _REL_TYPE.search(rel)
            if not t or not t.group(1).lower().endswith(b"/hyperlink"):
                raise FileRejected("This document links to external content we can't accept. "
                                   "Please save it as a PDF and try again.")


def _check_doc(data: bytes) -> None:
    if not data.startswith(OLE_MAGIC):
        raise FileRejected("This doesn't look like a valid DOC file.")
    # OLE directory entry names are UTF-16LE. A macro project lives in a
    # "Macros" (Word) or "_VBA_PROJECT" storage; embedded objects in "ObjectPool".
    # Directory names are NUL-terminated, which keeps a CV that merely
    # mentions "macros" in its (UTF-16) text from matching.
    for marker in ("Macros", "_VBA_PROJECT", "ObjectPool"):
        if (marker.encode("utf-16-le") + b"\x00\x00") in data:
            raise FileRejected("This document contains macros or embedded objects we can't accept. "
                               "Please save it as a PDF and try again.")
    if b"W\x00o\x00r\x00d\x00D\x00o\x00c\x00u\x00m\x00e\x00n\x00t" not in data:
        raise FileRejected("This doesn't look like a Word document.")


def check_cv(filename: str, declared_type: str, data: bytes) -> str:
    """Validate an uploaded CV. Returns the canonical extension, or raises
    FileRejected with a message that is safe to show the candidate."""
    ext = file_ext(filename)
    if ext not in ALLOWED:
        raise FileRejected("Upload your CV as a PDF, DOC or DOCX file.")
    if not data:
        raise FileRejected("This file is empty. Please choose another.")
    if len(data) > config.MAX_CV_BYTES:
        raise FileRejected("Please upload a CV of 10MB or less.")
    mime = (declared_type or "").split(";")[0].strip().lower()
    if mime and mime not in ALLOWED[ext]:
        raise FileRejected("The file type doesn't match its name. Please upload a PDF, DOC or DOCX.")
    {"pdf": _check_pdf, "docx": _check_docx, "doc": _check_doc}[ext](data)
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

    phone = g("phone", 25)
    digits = re.sub(r"\D", "", phone)
    if not PHONE_RE.match(phone) or not 8 <= len(digits) <= 15:
        r.fail("phone", "Enter a valid mobile number with the country code, for example +65 9123 4567.")
    d["phone"] = phone

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
        d["also_consider"] = ""
    else:
        d["interest_area"] = d["interest_detail"] = ""
        also_ok = bool(vacancy.get("also_consider_for"))
        d["also_consider"] = "Yes" if also_ok and form.get("also_consider") == "yes" else "No"

    # Non-identifying campaign attribution, for the tracker's source column.
    d["utm"] = {k: g(k, 100) for k in ("utm_source", "utm_medium", "utm_campaign", "utm_content")
                if g(k, 100)}
    d["source_page"] = g("source_page", 120)
    return r
