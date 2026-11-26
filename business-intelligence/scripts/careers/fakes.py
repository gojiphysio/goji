"""In-memory stand-ins for Drive/Sheets and SMTP, shared by the tests and the
local dev server. Nothing here touches Google or the network. Not shipped in
the image."""
from __future__ import annotations

import itertools

from .workspace import WorkspaceError

VACANCIES = {
    "physiotherapist": {"id": "physiotherapist", "title": "Physiotherapist", "open": True,
                        "form": "physio", "closing_date": None,
                        "also_consider_for": ["senior-physiotherapist"]},
    "senior-physiotherapist": {"id": "senior-physiotherapist", "title": "Senior Physiotherapist",
                               "open": True, "form": "physio", "closing_date": None,
                               "also_consider_for": ["physiotherapist"]},
    "old-role": {"id": "old-role", "title": "Old role", "open": False, "form": "physio",
                 "closing_date": None, "also_consider_for": []},
}

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
DOCX = b"PK\x03\x04" + b"\x00" * 64


class FakeWorkspace:
    def __init__(self):
        self.files: dict[str, dict] = {}
        self.rows: list[list] = []
        self.fail: set[str] = set()   # "upload" and/or "append"
        self._ids = (f"file{n}" for n in itertools.count(1))

    def upload(self, name, mime, data):
        if "upload" in self.fail:
            raise WorkspaceError("drive.upload: HTTP 503")
        fid = next(self._ids)
        self.files[fid] = {"name": name, "mime": mime, "bytes": len(data)}
        return fid

    def tracker_ids(self):
        return [r[0] for r in self.rows]

    def append_row(self, values):
        if "append" in self.fail:
            raise WorkspaceError("sheets.append: HTTP 503")
        self.rows.append(values)
