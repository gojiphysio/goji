"""
Google Drive + Sheets: the two calls this service makes.

Thin REST calls over google-auth's AuthorizedSession, authenticated as Cloud
Run's runtime identity (careers-sa). careers-sa is a Content manager on the
"Goji Recruitment" Shared Drive; a service account has no Drive storage of its
own, so the CV folder must be inside a Shared Drive. The service never creates
sharing permissions: who can see applications is the drive's membership.
"""
from __future__ import annotations

import json
import time
from urllib.parse import quote

from . import config

SCOPES = ["https://www.googleapis.com/auth/drive",
          "https://www.googleapis.com/auth/spreadsheets"]
UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
SHEETS = "https://sheets.googleapis.com/v4/spreadsheets"


class WorkspaceError(RuntimeError):
    """A Drive/Sheets call failed. The message carries the API and status only."""


class Workspace:
    def __init__(self, session=None):
        if session is None:
            import google.auth
            from google.auth.transport.requests import AuthorizedSession
            creds, _ = google.auth.default(scopes=SCOPES)
            session = AuthorizedSession(creds)
        self.s = session

    def _call(self, method: str, url: str, what: str, **kw) -> dict:
        """One call, retried on rate limits and server errors."""
        err = what
        for attempt in range(3):
            try:
                r = self.s.request(method, url, timeout=60, **kw)
            except Exception as e:
                err = f"{what}: {type(e).__name__}"
            else:
                if r.status_code < 300:
                    return r.json() if r.content else {}
                err = f"{what}: HTTP {r.status_code}"
                if r.status_code not in (429, 500, 502, 503, 504):
                    break
            time.sleep(0.5 * (2 ** attempt))
        raise WorkspaceError(err)

    def upload(self, name: str, mime: str, data: bytes) -> str:
        """Upload a file into the applications folder. Returns its file ID."""
        meta = {"name": name, "parents": [config.APPLICATIONS_FOLDER_ID]}
        boundary = "goji-careers-boundary-7c1f"
        body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
                f"{json.dumps(meta)}\r\n--{boundary}\r\nContent-Type: {mime}\r\n\r\n").encode()
        body += data + f"\r\n--{boundary}--".encode()
        return self._call("POST", UPLOAD, "drive.upload",
                          params={"supportsAllDrives": "true", "uploadType": "multipart",
                                  "fields": "id"},
                          data=body,
                          headers={"Content-Type": f"multipart/related; boundary={boundary}"})["id"]

    def _range(self, a1: str) -> str:
        return quote(f"'{config.TRACKER_TAB}'!{a1}", safe="")

    def tracker_ids(self) -> list[str]:
        body = self._call("GET", f"{SHEETS}/{config.TRACKER_SHEET_ID}/values/{self._range('A2:A')}",
                          "sheets.get")
        return [row[0] for row in body.get("values", []) if row]

    def append_row(self, values: list) -> None:
        # RAW: values are stored as typed, never parsed, so "=IMPORTXML(...)" in a
        # form field stays a literal string. INSERT_ROWS never overwrites a row.
        self._call("POST",
                   f"{SHEETS}/{config.TRACKER_SHEET_ID}/values/{self._range('A1')}:append",
                   "sheets.append",
                   params={"valueInputOption": "RAW", "insertDataOption": "INSERT_ROWS"},
                   json={"values": [values]})


def file_url(file_id: str) -> str:
    return f"https://drive.google.com/file/d/{file_id}/view"


def folder_url() -> str:
    return f"https://drive.google.com/drive/folders/{config.APPLICATIONS_FOLDER_ID}"


def sheet_url() -> str:
    return f"https://docs.google.com/spreadsheets/d/{config.TRACKER_SHEET_ID}/edit"
