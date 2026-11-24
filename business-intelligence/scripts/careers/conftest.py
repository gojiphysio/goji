"""Shared fixtures: an in-memory Drive/Sheets double with failure injection,
synthetic CV files, and a form payload builder. No test touches Google,
SMTP or the network; all applicant data here is synthetic."""
from __future__ import annotations

import io
import itertools
import zipfile
import zlib

import pytest

from careers import app as app_module
from careers import config, mailer, store, vacancies
from careers.workspace import WorkspaceError


class FakeWorkspace:
    def __init__(self):
        self.files: dict[str, dict] = {}
        self.rows: list[list] = []
        self.ids = (f"id{n}" for n in itertools.count(1))
        self.fail = set()  # e.g. {"upload", "append"}
        self.calls: list[str] = []
        self.files["APPS"] = {"id": "APPS", "name": "Applications", "parents": [], "folder": True,
                              "appProperties": {}}

    def _maybe_fail(self, what):
        self.calls.append(what)
        if what in self.fail:
            raise WorkspaceError(f"{what}: HTTP 503")

    def _new(self, name, parent, folder, props=None, data=None, mime=None):
        fid = next(self.ids)
        self.files[fid] = {"id": fid, "name": name, "parents": [parent], "folder": folder,
                           "appProperties": dict(props or {}), "data": data, "mime": mime}
        return dict(self.files[fid])

    # Drive
    def find_by_property(self, key, value):
        self._maybe_fail("find")
        for f in self.files.values():
            if f["folder"] and f["appProperties"].get(key) == value:
                return dict(f, appProperties=dict(f["appProperties"]))
        return None

    def find_child(self, parent, name, folder=True):
        for f in self.files.values():
            if parent in f["parents"] and f["name"] == name and f["folder"] == folder:
                return dict(f)
        return None

    def ensure_folder(self, parent, name):
        self._maybe_fail("ensure_folder")
        return self.find_child(parent, name) or self._new(name, parent, True)

    def create_folder(self, name, parent, props=None):
        self._maybe_fail("create_folder")
        return self._new(name, parent, True, props)

    def children(self, parent):
        return [dict(f) for f in self.files.values() if parent in f["parents"]]

    def folder_names_containing(self, text):
        return [f["name"] for f in self.files.values() if f["folder"] and text in f["name"]]

    def upload(self, name, parent, mime, data, props=None):
        self._maybe_fail("upload")
        return self._new(name, parent, False, props, data, mime)

    def set_properties(self, fid, props):
        self._maybe_fail("set_properties")
        self.files[fid]["appProperties"].update(props)

    # Sheets
    def tracker_ids(self):
        self._maybe_fail("tracker_ids")
        return [r[0] for r in self.rows]

    def append_row(self, values):
        self._maybe_fail("append")
        self.rows.append(list(values))

    # helpers for assertions
    def app_folders(self):
        return [f for f in self.files.values() if f["folder"] and f["appProperties"].get("goji_ref")]

    def files_in(self, fid):
        return [f for f in self.files.values() if fid in f["parents"] and not f["folder"]]


# ---- synthetic CVs ----------------------------------------------------------------

def make_pdf(extra: bytes = b"") -> bytes:
    return (b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n" + extra +
            b"\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n")


def make_pdf_with_compressed(payload: bytes) -> bytes:
    stream = zlib.compress(payload)
    return make_pdf(b"3 0 obj\n<< /Type /ObjStm /Filter /FlateDecode >>\nstream\n" + stream +
                    b"\nendstream\nendobj\n")


def make_docx(extra_parts: dict | None = None, rels: str | None = None,
              content_types: str | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types or
                   '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        z.writestr("word/document.xml", "<w:document><w:body><w:p>Synthetic CV</w:p></w:body></w:document>")
        z.writestr("word/_rels/document.xml.rels", rels or
                   '<Relationships><Relationship Id="rId1" '
                   'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" '
                   'Target="https://www.linkedin.com/in/example" TargetMode="External"/></Relationships>')
        for name, data in (extra_parts or {}).items():
            z.writestr(name, data)
    return buf.getvalue()


def make_doc(macros: bool = False) -> bytes:
    body = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 504
    body += "WordDocument".encode("utf-16-le") + b"\x00\x00"
    if macros:
        body += "Macros".encode("utf-16-le") + b"\x00\x00"
    return body + b"\x00" * 512


# ---- form payloads ------------------------------------------------------------------

def form_data(**over) -> dict:
    d = {
        "role": "physiotherapist",
        "full_name": "Test Applicant",
        "email": "applicant@example.com",
        "phone": "+65 9123 4567",
        "employment": "full-time",
        "years_experience": "4",
        "ahpc_status": "Fully registered",
        "clinical_experience": "Outpatient MSK, sports injuries",
        "start_availability": "One month's notice",
        "intro": "Synthetic applicant for automated tests.",
        "privacy_ack": "yes",
        "talent_pool": "no",
        "also_consider": "no",
        "idempotency_key": "test-key-0000000000000001",
        "elapsed_ms": "60000",
        "source_page": "/careers/physiotherapist/",
    }
    d.update(over)
    return {k: v for k, v in d.items() if v is not None}


VACANCIES = {
    "physiotherapist": {"id": "physiotherapist", "title": "Physiotherapist", "open": True,
                        "form": "physio", "min_days_per_week": 3, "closing_date": None,
                        "also_consider_for": ["senior-physiotherapist"],
                        "drive_folder": "Physiotherapist"},
    "senior-physiotherapist": {"id": "senior-physiotherapist", "title": "Senior Physiotherapist",
                               "open": True, "form": "physio", "min_days_per_week": 3,
                               "closing_date": None, "also_consider_for": ["physiotherapist"],
                               "drive_folder": "Senior Physiotherapist"},
    "clinical-lead": {"id": "clinical-lead", "title": "Clinical Lead", "open": False,
                      "form": "physio", "closing_date": None, "also_consider_for": [],
                      "drive_folder": "Clinical Lead"},
}


@pytest.fixture
def fake_ws(monkeypatch):
    ws = FakeWorkspace()
    monkeypatch.setattr(app_module, "_ws", ws)
    monkeypatch.setattr(config, "APPLICATIONS_FOLDER_ID", "APPS")
    monkeypatch.setattr(config, "TRACKER_SHEET_ID", "SHEET")
    return ws


@pytest.fixture
def sent(monkeypatch):
    """Capture emails instead of sending them."""
    out: list = []
    monkeypatch.setattr(config, "SMTP_PASS", "test-password")
    monkeypatch.setattr(mailer, "_send", lambda msg: out.append(msg))
    return out


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    monkeypatch.setattr(config, "CORS_ORIGINS", ["https://www.gojiphysio.com"])
    monkeypatch.setattr(config, "TURNSTILE_SECRET", "")
    monkeypatch.setattr(config, "TEST_MODE", False)
    monkeypatch.setattr(config, "TEST_EMAIL", "")
    monkeypatch.setattr(config, "SMTP_PASS", None)
    monkeypatch.setattr(vacancies, "_fetch", lambda: VACANCIES)
    vacancies.reset_cache()
    app_module._hits.clear()
    app_module._human_keys.clear()
    yield
