"""
Google Drive + Sheets access for the careers service, as hello@gojiphysio.com.

Why an OAuth refresh token and not a service account: Goji's Workspace has no
Shared Drive, and a service account has no Drive storage quota, so it cannot
own uploaded files in My Drive ("Service Accounts do not have storage quota").
Files created with hello@'s token are owned by hello@ and count against its
quota, which is what we want.

Least privilege: the token's only scope is `drive.file`, which lets this app
see and change **only the files and folders it created itself** (the
recruitment folder tree and the tracker, made by `admin.py setup`). It cannot
read, list or touch anything else in hello@'s Drive. The Sheets API accepts
`drive.file` for sheets the app created.

Plain `requests`, no Google client library: the service needs a handful of REST
calls and one token refresh.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid

import requests

from . import config

log = logging.getLogger("careers.google")

SCOPE = "https://www.googleapis.com/auth/drive.file"
TOKEN_URL = "https://oauth2.googleapis.com/token"
DRIVE = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
SHEETS = "https://sheets.googleapis.com/v4/spreadsheets"
FOLDER_MIME = "application/vnd.google-apps.folder"


class StoreError(Exception):
    """A Google call failed. `retryable` is True for 429/5xx/network errors."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status
        self.retryable = status is None or status == 429 or status >= 500


def folder_url(fid: str) -> str:
    return f"https://drive.google.com/drive/folders/{fid}"


def file_url(fid: str) -> str:
    return f"https://drive.google.com/file/d/{fid}/view"


def sheet_url(sid: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{sid}/edit"


def _q(value: str) -> str:
    """Escape a value for a Drive `q` string literal."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


class GoogleStore:
    def __init__(self, client_id: str | None = None, client_secret: str | None = None,
                 refresh_token: str | None = None, session: requests.Session | None = None):
        self.client_id = client_id or config.GOOGLE_CLIENT_ID
        self.client_secret = client_secret or config.GOOGLE_CLIENT_SECRET
        self.refresh_token = refresh_token or config.GOOGLE_REFRESH_TOKEN
        if not (self.client_id and self.client_secret and self.refresh_token):
            raise StoreError("Google credentials are not configured", status=503)
        self.s = session or requests.Session()
        self._token: tuple[str, float] | None = None
        self._lock = threading.Lock()

    # ---- auth ---------------------------------------------------------------
    def _access_token(self) -> str:
        with self._lock:
            if self._token and time.monotonic() < self._token[1]:
                return self._token[0]
            try:
                r = self.s.post(TOKEN_URL, timeout=15, data={
                    "client_id": self.client_id, "client_secret": self.client_secret,
                    "refresh_token": self.refresh_token, "grant_type": "refresh_token"})
            except requests.RequestException as e:
                raise StoreError(f"token refresh failed: {type(e).__name__}") from e
            if r.status_code != 200:
                # invalid_grant = token revoked/expired: re-run `admin.py authorize`.
                err = (r.json() or {}).get("error") if r.headers.get(
                    "content-type", "").startswith("application/json") else r.status_code
                raise StoreError(f"token refresh rejected: {err}", status=r.status_code)
            body = r.json()
            self._token = (body["access_token"],
                           time.monotonic() + int(body.get("expires_in", 3600)) - 120)
            return self._token[0]

    def _call(self, method: str, url: str, *, ok=(200,), **kw) -> requests.Response:
        headers = kw.pop("headers", {})
        headers["Authorization"] = f"Bearer {self._access_token()}"
        try:
            r = self.s.request(method, url, headers=headers, timeout=60, **kw)
        except requests.RequestException as e:
            raise StoreError(f"{method} {url.split('?')[0]} failed: {type(e).__name__}") from e
        if r.status_code not in ok:
            # Google's error bodies describe the request, not our data; still,
            # keep only the reason so nothing applicant-related lands in logs.
            reason = ""
            try:
                reason = r.json()["error"]["message"][:200]
            except Exception:
                pass
            raise StoreError(f"{method} {url.split('?')[0]} -> {r.status_code} {reason}",
                             status=r.status_code)
        return r

    # ---- Drive --------------------------------------------------------------
    def find_files(self, q: str, fields: str = "id,name,appProperties") -> list[dict]:
        out: list[dict] = []
        token = None
        while True:
            params = {"q": q, "fields": f"nextPageToken,files({fields})",
                      "pageSize": 200, "spaces": "drive"}
            if token:
                params["pageToken"] = token
            body = self._call("GET", f"{DRIVE}/files", params=params).json()
            out += body.get("files", [])
            token = body.get("nextPageToken")
            if not token:
                return out

    def find_folder_by_property(self, key: str, value: str) -> dict | None:
        files = self.find_files(
            f"appProperties has {{ key='{_q(key)}' and value='{_q(value)}' }} "
            f"and mimeType='{FOLDER_MIME}' and trashed=false")
        return files[0] if files else None

    def find_child_folder(self, parent: str, name: str) -> dict | None:
        files = self.find_files(
            f"'{_q(parent)}' in parents and name='{_q(name)}' "
            f"and mimeType='{FOLDER_MIME}' and trashed=false")
        return files[0] if files else None

    def list_children(self, parent: str, folders_only: bool = False) -> list[dict]:
        q = f"'{_q(parent)}' in parents and trashed=false"
        if folders_only:
            q += f" and mimeType='{FOLDER_MIME}'"
        return self.find_files(q, fields="id,name,mimeType,appProperties,createdTime")

    def get_file(self, fid: str, fields: str = "id,name,appProperties") -> dict:
        return self._call("GET", f"{DRIVE}/files/{fid}", params={"fields": fields}).json()

    def create_folder(self, name: str, parent: str | None = None,
                      app_properties: dict | None = None) -> dict:
        meta: dict = {"name": name, "mimeType": FOLDER_MIME}
        if parent:
            meta["parents"] = [parent]
        if app_properties:
            meta["appProperties"] = app_properties
        return self._call("POST", f"{DRIVE}/files", params={"fields": "id,name,appProperties"},
                          json=meta).json()

    def ensure_folder(self, parent: str, name: str) -> str:
        found = self.find_child_folder(parent, name)
        return found["id"] if found else self.create_folder(name, parent)["id"]

    def set_app_properties(self, fid: str, props: dict) -> dict:
        return self._call("PATCH", f"{DRIVE}/files/{fid}",
                          params={"fields": "id,appProperties"},
                          json={"appProperties": props}).json()

    def upload(self, parent: str, name: str, mime: str, data: bytes,
               app_properties: dict | None = None) -> dict:
        """Multipart upload. The file inherits the folder's (private) sharing."""
        meta: dict = {"name": name, "parents": [parent], "mimeType": mime}
        if app_properties:
            meta["appProperties"] = app_properties
        boundary = f"goji{uuid.uuid4().hex}"
        body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
                f"{json.dumps(meta)}\r\n--{boundary}\r\nContent-Type: {mime}\r\n\r\n"
                ).encode() + data + f"\r\n--{boundary}--".encode()
        return self._call("POST", UPLOAD, params={"uploadType": "multipart",
                                                  "fields": "id,name"},
                          headers={"Content-Type": f"multipart/related; boundary={boundary}"},
                          data=body).json()

    def download(self, fid: str) -> bytes:
        return self._call("GET", f"{DRIVE}/files/{fid}", params={"alt": "media"}).content

    def permissions(self, fid: str) -> list[dict]:
        r = self._call("GET", f"{DRIVE}/files/{fid}/permissions",
                       params={"fields": "permissions(type,role,emailAddress)"})
        return r.json().get("permissions", [])

    def trash(self, fid: str) -> None:
        self._call("PATCH", f"{DRIVE}/files/{fid}", json={"trashed": True})

    # ---- Sheets -------------------------------------------------------------
    def append_row(self, sheet_id: str, tab: str, values: list) -> None:
        """Append one row. valueInputOption=RAW stores every value as literal
        text, so an applicant typing `=HYPERLINK(...)` gets that text, never a
        formula. INSERT_ROWS never overwrites the rows reviewers maintain."""
        rng = requests.utils.quote(f"'{tab}'!A1", safe="")
        self._call("POST", f"{SHEETS}/{sheet_id}/values/{rng}:append",
                   params={"valueInputOption": "RAW", "insertDataOption": "INSERT_ROWS"},
                   json={"values": [values]})

    def column_values(self, sheet_id: str, tab: str, column: str = "A") -> list[str]:
        rng = requests.utils.quote(f"'{tab}'!{column}:{column}", safe="")
        r = self._call("GET", f"{SHEETS}/{sheet_id}/values/{rng}",
                       params={"majorDimension": "COLUMNS"})
        cols = r.json().get("values") or [[]]
        return [str(v) for v in cols[0]]

    def rows(self, sheet_id: str, tab: str) -> list[list[str]]:
        rng = requests.utils.quote(f"'{tab}'", safe="")
        r = self._call("GET", f"{SHEETS}/{sheet_id}/values/{rng}")
        return [[str(c) for c in row] for row in r.json().get("values", [])]

    def create_spreadsheet(self, body: dict) -> dict:
        return self._call("POST", SHEETS, json=body).json()

    def batch_update(self, sheet_id: str, requests_: list[dict]) -> dict:
        return self._call("POST", f"{SHEETS}/{sheet_id}:batchUpdate",
                          json={"requests": requests_}).json()

    def move(self, fid: str, new_parent: str) -> None:
        cur = self.get_file(fid, fields="parents").get("parents", [])
        self._call("PATCH", f"{DRIVE}/files/{fid}", params={
            "addParents": new_parent, "removeParents": ",".join(cur), "fields": "id"},
            json={})
