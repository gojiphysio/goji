"""Shared fixtures: an in-memory Drive/Sheets fake with failure injection,
synthetic CV files, and a valid synthetic application form. No network, no
Google, no SMTP: every test runs offline."""
from __future__ import annotations

import io
import itertools
import uuid
import zipfile

import pytest

from careers import config, mailer, vacancies
from careers.google_store import StoreError
from careers.vacancies import Vacancy

PHYSIO = Vacancy(id="physiotherapist", title="Physiotherapist / Senior Physiotherapist",
                 active=True, form="physio", location="Lentor Modern, Singapore",
                 drive_folder="Physiotherapist", min_days=3)
CLOSED = Vacancy(id="pilates-instructor", title="Pilates Instructor", active=False,
                 form="general", location="Lentor Modern, Singapore",
                 drive_folder="Pilates Instructor")


class FakeStore:
    """Just enough of GoogleStore. `fail` maps a method name to how many of its
    next calls raise a retryable StoreError."""

    def __init__(self):
        self.files: dict[str, dict] = {}
        self.blobs: dict[str, bytes] = {}
        self.rows_: list[list] = [["Application ID"]]
        self.fail: dict[str, int] = {}
        self._ids = (f"id{n}" for n in itertools.count(1))
        self.files["root"] = {"id": "root", "name": "Goji Recruitment", "parents": [],
                              "appProperties": {}, "folder": True}
        self.files["apps"] = {"id": "apps", "name": "Applications", "parents": ["root"],
                              "appProperties": {}, "folder": True}

    def _maybe_fail(self, name):
        if self.fail.get(name, 0) > 0:
            self.fail[name] -= 1
            raise StoreError(f"injected {name} failure", status=503)

    # Drive
    def find_folder_by_property(self, key, value):
        self._maybe_fail("find_folder_by_property")
        for f in self.files.values():
            if f["folder"] and f["appProperties"].get(key) == value:
                return {**f, "appProperties": dict(f["appProperties"])}
        return None

    def find_files(self, q, fields=""):
        return [{**f, "appProperties": dict(f["appProperties"])}
                for f in self.files.values()
                if f["folder"] and f["name"].startswith("GOJI-APP-")]

    def get_file(self, fid, fields=""):
        f = self.files[fid]
        return {**f, "appProperties": dict(f["appProperties"])}

    def set_app_properties(self, fid, props):
        self._maybe_fail("set_app_properties")
        self.files[fid]["appProperties"].update(props)
        return self.get_file(fid)

    def create_folder(self, name, parent=None, app_properties=None):
        self._maybe_fail("create_folder")
        fid = next(self._ids)
        self.files[fid] = {"id": fid, "name": name, "parents": [parent] if parent else [],
                           "appProperties": dict(app_properties or {}), "folder": True}
        return self.get_file(fid)

    def ensure_folder(self, parent, name):
        for f in self.files.values():
            if f["folder"] and f["name"] == name and parent in f["parents"]:
                return f["id"]
        return self.create_folder(name, parent)["id"]

    def upload(self, parent, name, mime, data, app_properties=None):
        self._maybe_fail("upload")
        fid = next(self._ids)
        self.files[fid] = {"id": fid, "name": name, "parents": [parent], "mime": mime,
                           "appProperties": dict(app_properties or {}), "folder": False}
        self.blobs[fid] = data
        return {"id": fid, "name": name}

    def download(self, fid):
        return self.blobs[fid]

    # Sheets
    def column_values(self, sheet_id, tab, column="A"):
        self._maybe_fail("column_values")
        return [str(r[0]) for r in self.rows_]

    def append_row(self, sheet_id, tab, values):
        self._maybe_fail("append_row")
        self.rows_.append(list(values))

    # helpers for assertions
    def app_folders(self):
        return [f for f in self.files.values() if f["folder"] and f["name"].startswith("GOJI-APP-")]

    def uploads(self, kind):
        return [f for f in self.files.values() if not f["folder"]
                and f["appProperties"].get("kind") == kind]


@pytest.fixture
def store(monkeypatch):
    monkeypatch.setattr(config, "DRIVE_ROOT_ID", "root")
    monkeypatch.setattr(config, "DRIVE_APPLICATIONS_ID", "apps")
    monkeypatch.setattr(config, "TRACKER_ID", "sheet1")
    return FakeStore()


@pytest.fixture
def sent(monkeypatch):
    """Capture emails instead of sending them. Set sent.ok = False to make
    every send fail."""
    class Sent(list):
        ok = True
    box = Sent()

    def fake_send(msg, what, ref):
        if not box.ok:
            return False
        box.append({"what": what, "to": msg["To"], "subject": msg["Subject"],
                    "body": msg.get_body(("plain",)).get_content()})
        return True
    monkeypatch.setattr(mailer, "_send", fake_send)
    monkeypatch.setattr(config, "TEST_MODE", False)
    return box


@pytest.fixture(autouse=True)
def _known_vacancies(monkeypatch):
    roles = {PHYSIO.id: PHYSIO, CLOSED.id: CLOSED}
    monkeypatch.setattr(vacancies, "all_vacancies", lambda: roles)


# ---- synthetic CVs -----------------------------------------------------------
def pdf_bytes(extra: bytes = b"") -> bytes:
    return (b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R " + extra +
            b">>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [] /Count 0 >>\nendobj\n"
            b"trailer\n<< /Root 1 0 R >>\n%%EOF\n")


def docx_bytes(extra: dict | None = None, content_types: bytes | None = None,
               rels: bytes | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types or
                   b'<?xml version="1.0"?><Types><Override PartName="/word/document.xml" '
                   b'ContentType="application/vnd.openxmlformats-officedocument.'
                   b'wordprocessingml.document.main+xml"/></Types>')
        z.writestr("word/document.xml", b"<w:document><w:body><w:p>Jane Test CV</w:p>"
                                        b"</w:body></w:document>")
        z.writestr("word/_rels/document.xml.rels", rels or
                   b'<Relationships><Relationship Id="rId1" Type="http://x/hyperlink" '
                   b'Target="https://example.com" TargetMode="External"/></Relationships>')
        for name, data in (extra or {}).items():
            z.writestr(name, data)
    return buf.getvalue()


def doc_bytes(with_macros: bool = False) -> bytes:
    body = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 504
    body += "WordDocument".encode("utf-16-le") + b"\x00\x00"
    if with_macros:
        body += "Macros".encode("utf-16-le") + b"\x00\x00"
    return body + b"\x00" * 512


def form(**over) -> dict:
    """A complete, valid full-time physiotherapist application (synthetic)."""
    base = {
        "submission_id": str(uuid.uuid4()),
        "job_id": "physiotherapist",
        "full_name": "Test Applicant",
        "email": "test.applicant@example.com",
        "phone": "+65 9123 4567",
        "employment_pref": "full_time",
        "years_experience": "3-5",
        "start_availability": "One month's notice",
        "intro": "I'm a physiotherapist with four years in private MSK practice.",
        "ahpc_status": "full",
        "clinical_areas": ["msk", "sports"],
        "privacy_ack": "on",
        "elapsed_ms": "60000",
    }
    base.update(over)
    return {k: v for k, v in base.items() if v is not None}
