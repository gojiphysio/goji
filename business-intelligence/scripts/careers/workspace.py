"""
Google Drive + Sheets, the only two Google APIs this service uses.

Thin REST calls over google-auth's AuthorizedSession (no discovery client), so
the image stays small and every call is visible here. Credentials never leave
the server: the browser talks only to our API.

Two ways to authenticate (config.GOOGLE_AUTH_MODE, setup in README.md):
  service_account  Cloud Run's runtime identity. The recruitment folder must be
                   in a Shared Drive the service account is a member of; a
                   service account has no My Drive quota, so uploads into a
                   folder merely *shared* with it fail.
  oauth            A refresh token for hello@gojiphysio.com (Secret Manager),
                   for a recruitment folder in hello@'s own My Drive.

The service never creates sharing permissions. Who can see applications is
decided entirely by membership of the Shared Drive / folder.
"""
from __future__ import annotations

import json
import logging
import time

from . import config

log = logging.getLogger("careers.workspace")

SCOPES = ["https://www.googleapis.com/auth/drive",
          "https://www.googleapis.com/auth/spreadsheets"]
DRIVE = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3"
SHEETS = "https://sheets.googleapis.com/v4/spreadsheets"
FOLDER_MIME = "application/vnd.google-apps.folder"
COMMON = {"supportsAllDrives": "true"}


class WorkspaceError(RuntimeError):
    """A Drive/Sheets call failed. Message carries the API + status only."""


def credentials():
    import google.auth
    if config.GOOGLE_AUTH_MODE == "oauth":
        from google.oauth2.credentials import Credentials
        info = json.loads(config.GOOGLE_OAUTH_CLIENT_JSON or "{}")
        if not info.get("refresh_token"):
            raise WorkspaceError("GOOGLE_OAUTH_CLIENT_JSON has no refresh_token")
        return Credentials(None, refresh_token=info["refresh_token"],
                           client_id=info["client_id"], client_secret=info["client_secret"],
                           token_uri="https://oauth2.googleapis.com/token", scopes=SCOPES)
    creds, _ = google.auth.default(scopes=SCOPES)
    return creds


def _q(value: str) -> str:
    """Escape a value for a Drive query string literal."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


class Workspace:
    """Drive + Sheets operations the submission flow needs."""

    def __init__(self, session=None):
        if session is None:
            from google.auth.transport.requests import AuthorizedSession
            session = AuthorizedSession(credentials())
        self.s = session

    # ---- transport -----------------------------------------------------------
    def _call(self, method: str, url: str, what: str, **kw):
        for attempt in range(4):
            try:
                r = self.s.request(method, url, timeout=60, **kw)
            except Exception as e:  # network
                err = f"{what}: {type(e).__name__}"
            else:
                if r.status_code < 300:
                    return r.json() if r.content else {}
                err = f"{what}: HTTP {r.status_code}"
                if r.status_code not in (429, 500, 502, 503, 504):
                    raise WorkspaceError(err)
            if attempt < 3:
                time.sleep(0.5 * (2 ** attempt))
        raise WorkspaceError(err)

    # ---- Drive -----------------------------------------------------------------
    def _list(self, q: str, fields: str = "files(id,name,appProperties,webViewLink)") -> list[dict]:
        out, token = [], None
        while True:
            params = {"q": q, "fields": f"nextPageToken,{fields}", "pageSize": "200",
                      "includeItemsFromAllDrives": "true", "corpora": "allDrives", **COMMON}
            if token:
                params["pageToken"] = token
            body = self._call("GET", f"{DRIVE}/files", "drive.list", params=params)
            out += body.get("files", [])
            token = body.get("nextPageToken")
            if not token:
                return out

    def find_by_property(self, key: str, value: str) -> dict | None:
        hits = self._list(f"appProperties has {{ key='{_q(key)}' and value='{_q(value)}' }} "
                          f"and mimeType='{FOLDER_MIME}' and trashed=false")
        return hits[0] if hits else None

    def find_child(self, parent_id: str, name: str, folder: bool = True) -> dict | None:
        q = f"'{_q(parent_id)}' in parents and name='{_q(name)}' and trashed=false"
        if folder:
            q += f" and mimeType='{FOLDER_MIME}'"
        hits = self._list(q)
        return hits[0] if hits else None

    def children(self, parent_id: str) -> list[dict]:
        return self._list(f"'{_q(parent_id)}' in parents and trashed=false")

    def folder_names_containing(self, text: str) -> list[str]:
        return [f["name"] for f in self._list(
            f"name contains '{_q(text)}' and mimeType='{FOLDER_MIME}' and trashed=false",
            fields="files(name)")]

    def create_folder(self, name: str, parent_id: str, props: dict | None = None) -> dict:
        meta = {"name": name, "mimeType": FOLDER_MIME, "parents": [parent_id]}
        if props:
            meta["appProperties"] = props
        return self._call("POST", f"{DRIVE}/files", "drive.create_folder",
                          params={**COMMON, "fields": "id,name,appProperties,webViewLink"},
                          json=meta)

    def ensure_folder(self, parent_id: str, name: str) -> dict:
        return self.find_child(parent_id, name) or self.create_folder(name, parent_id)

    def upload(self, name: str, parent_id: str, mime: str, data: bytes,
               props: dict | None = None) -> dict:
        meta = {"name": name, "parents": [parent_id]}
        if props:
            meta["appProperties"] = props
        boundary = "goji-careers-boundary-7c1f"
        body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
                f"{json.dumps(meta)}\r\n--{boundary}\r\nContent-Type: {mime}\r\n\r\n").encode()
        body += data + f"\r\n--{boundary}--".encode()
        return self._call("POST", f"{UPLOAD}/files", "drive.upload",
                          params={**COMMON, "uploadType": "multipart",
                                  "fields": "id,name,appProperties,webViewLink"},
                          data=body,
                          headers={"Content-Type": f"multipart/related; boundary={boundary}"})

    def set_properties(self, file_id: str, props: dict) -> None:
        self._call("PATCH", f"{DRIVE}/files/{file_id}", "drive.update",
                   params={**COMMON, "fields": "id"}, json={"appProperties": props})

    # ---- Sheets ------------------------------------------------------------------
    def _range(self, a1: str) -> str:
        from urllib.parse import quote
        return quote(f"'{config.TRACKER_TAB}'!{a1}", safe="")

    def tracker_ids(self) -> list[str]:
        body = self._call("GET", f"{SHEETS}/{config.TRACKER_SHEET_ID}/values/{self._range('A2:A')}",
                          "sheets.get")
        return [row[0] for row in body.get("values", []) if row]

    def append_row(self, values: list) -> None:
        # RAW: every value is stored exactly as text/number, never parsed, so an
        # applicant typing "=IMPORTXML(...)" gets a literal string, not a formula.
        # INSERT_ROWS: appends below the table without overwriting anything.
        self._call("POST",
                   f"{SHEETS}/{config.TRACKER_SHEET_ID}/values/{self._range('A1')}:append",
                   "sheets.append",
                   params={"valueInputOption": "RAW", "insertDataOption": "INSERT_ROWS"},
                   json={"values": [values]})


def folder_url(folder_id: str) -> str:
    return f"https://drive.google.com/drive/folders/{folder_id}"


def file_url(file_id: str) -> str:
    return f"https://drive.google.com/file/d/{file_id}/view"


def sheet_url() -> str:
    return f"https://docs.google.com/spreadsheets/d/{config.TRACKER_SHEET_ID}/edit"
