"""
CV upload safety checks: the file is what it claims to be, and carries no
active content.

Every rule below runs server-side; the browser's checks are only a courtesy.
Order, cheapest first:
  1. size (<= 10 MB, > 0)
  2. extension in {pdf, doc, docx}
  3. declared MIME type matches that extension (or is the generic
     octet-stream some mobile browsers send)
  4. file signature (magic bytes) matches the extension
  5. no active content:
       PDF  - no JavaScript, launch actions, embedded files, rich media or XFA
       DOCX - a sane zip (entry count / expansion ratio), no macros (vbaProject),
              ActiveX, embedded OLE objects or externally attached templates
       DOC  - no VBA / macro storage

Anything that fails is rejected with a reason code; nothing is stored. This is
a structural "quarantine at the door" check, not an antivirus engine. Reviewers
should open CVs in Drive's previewer (which renders them on Google's side)
rather than downloading them. See README "CV safety".
"""
from __future__ import annotations

import hashlib
import io
import re
import unicodedata
import zipfile
from dataclasses import dataclass

from . import config

PDF_MAGIC = b"%PDF-"
OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
ZIP_MAGIC = b"PK\x03\x04"

MIME_BY_EXT = {
    "pdf": "application/pdf",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
# Declared types we tolerate per extension. Browsers on some phones send a
# generic type (or none) for documents picked from Files/Drive.
GENERIC_MIME = {"", "application/octet-stream", "binary/octet-stream"}
ALSO_OK = {
    "pdf": {"application/x-pdf"},
    "doc": {"application/vnd.ms-word"},
    "docx": {"application/zip"},
}

# PDF names that mean "this document can run or carry something".
PDF_ACTIVE = (b"/JavaScript", b"/JS", b"/Launch", b"/EmbeddedFile",
              b"/RichMedia", b"/XFA", b"/SubmitForm", b"/ImportData")
# DOCX zip limits (zip-bomb guard). A real CV is a few dozen entries.
DOCX_MAX_ENTRIES = 1000
DOCX_MAX_UNCOMPRESSED = 60 * 1024 * 1024
DOCX_MAX_RATIO = 120


class FileRejected(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class CheckedFile:
    data: bytes
    ext: str
    mime: str           # the MIME type we store it as (from the signature)
    safe_name: str      # sanitised original filename, for the summary only
    sha256: str
    size: int


def sanitise_filename(name: str, max_len: int = 80) -> str:
    """Basename only; letters, digits, space, dot, dash, underscore; no leading
    dots; collapsed whitespace. Never used as a path, only kept for reviewers."""
    name = (name or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name)
    name = re.sub(r"\s+", " ", name).strip(" ._")
    if len(name) > max_len:
        stem, dot, ext = name.rpartition(".")
        name = (stem[: max_len - len(ext) - 1] + "." + ext) if dot and len(ext) <= 5 \
            else name[:max_len]
    return name or "cv"


def _ext(name: str) -> str:
    base = (name or "").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    return base.rsplit(".", 1)[-1].lower() if "." in base else ""


def _pdf_normalise_names(data: bytes) -> bytes:
    """Undo #xx hex escapes inside PDF names (/J#61vaScript -> /JavaScript),
    a standard trick for hiding a name from naive scanners."""
    return re.sub(rb"#([0-9A-Fa-f]{2})", lambda m: bytes([int(m.group(1), 16)]), data)


def _check_pdf(data: bytes) -> None:
    if not data.startswith(PDF_MAGIC) and PDF_MAGIC not in data[:1024]:
        raise FileRejected("bad_signature", "This file doesn't look like a PDF.")
    norm = _pdf_normalise_names(data)
    for name in PDF_ACTIVE:
        # Match the name as a whole token (/JS but not /JSomething).
        if re.search(re.escape(name) + rb"(?![A-Za-z0-9])", norm):
            raise FileRejected("active_content",
                               "This PDF contains interactive or embedded content "
                               "we can't accept. Please save it as a plain PDF.")


def _check_docx(data: bytes) -> None:
    if not data.startswith(ZIP_MAGIC):
        raise FileRejected("bad_signature", "This file doesn't look like a Word document.")
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        infos = zf.infolist()
    except zipfile.BadZipFile:
        raise FileRejected("bad_signature", "This Word document appears to be damaged.")
    if len(infos) > DOCX_MAX_ENTRIES:
        raise FileRejected("suspicious", "This Word document has an unusual structure.")
    total = 0
    for i in infos:
        total += i.file_size
        if i.compress_size and i.file_size / max(i.compress_size, 1) > DOCX_MAX_RATIO \
                and i.file_size > 1024 * 1024:
            raise FileRejected("suspicious", "This Word document has an unusual structure.")
    if total > DOCX_MAX_UNCOMPRESSED:
        raise FileRejected("suspicious", "This Word document has an unusual structure.")
    names = {i.filename for i in infos}
    lower = {n.lower() for n in names}
    if "[content_types].xml" not in lower or "word/document.xml" not in lower:
        raise FileRejected("bad_signature", "This file doesn't look like a Word document.")
    if any(n.endswith("vbaproject.bin") or n.startswith("word/activex/")
           or n.startswith("word/embeddings/") for n in lower):
        raise FileRejected("active_content",
                           "This document contains macros or embedded objects we "
                           "can't accept. Please save it as a plain .docx or PDF.")
    ct = zf.read(next(n for n in names if n.lower() == "[content_types].xml"))
    if b"macroEnabled" in ct or b"vbaProject" in ct:
        raise FileRejected("active_content",
                           "This document contains macros we can't accept. "
                           "Please save it as a plain .docx or PDF.")
    # Remote-template / external OLE links (a known Word attack): any external
    # relationship of those kinds is refused. Hyperlinks stay allowed.
    for n in names:
        if n.lower().endswith(".rels"):
            rels = zf.read(n)
            for m in re.finditer(rb"<Relationship\b[^>]*>", rels):
                tag = m.group(0)
                if b'TargetMode="External"' in tag and (
                        b"attachedTemplate" in tag or b"oleObject" in tag
                        or b"frame" in tag or b"subDocument" in tag):
                    raise FileRejected("active_content",
                                       "This document links to external content we "
                                       "can't accept. Please save it as a PDF.")


def _check_doc(data: bytes) -> None:
    if not data.startswith(OLE_MAGIC):
        raise FileRejected("bad_signature", "This file doesn't look like a Word document.")
    # OLE directory entry names are UTF-16LE. Macro storage is _VBA_PROJECT /
    # VBA / Macros; refuse any of them.
    for marker in ("_VBA_PROJECT", "Macros", "VBA"):
        if marker.encode("utf-16-le") + b"\x00\x00" in data:
            raise FileRejected("active_content",
                               "This document contains macros we can't accept. "
                               "Please save it as a .docx or PDF.")


def check_cv(filename: str, declared_mime: str, data: bytes) -> CheckedFile:
    """Validate an uploaded CV or raise FileRejected (with a user-safe message)."""
    size = len(data)
    if size == 0:
        raise FileRejected("empty", "The selected file is empty.")
    if size > config.MAX_CV_BYTES:
        raise FileRejected("too_large", "Your CV must be 10 MB or smaller.")
    ext = _ext(filename)
    if ext not in MIME_BY_EXT:
        raise FileRejected("bad_type", "Please upload your CV as a PDF, DOC or DOCX file.")
    declared = (declared_mime or "").split(";")[0].strip().lower()
    if declared not in GENERIC_MIME | {MIME_BY_EXT[ext]} | ALSO_OK[ext]:
        raise FileRejected("bad_type", "Please upload your CV as a PDF, DOC or DOCX file.")
    {"pdf": _check_pdf, "docx": _check_docx, "doc": _check_doc}[ext](data)
    return CheckedFile(data=data, ext=ext, mime=MIME_BY_EXT[ext],
                       safe_name=sanitise_filename(filename),
                       sha256=hashlib.sha256(data).hexdigest(), size=size)
