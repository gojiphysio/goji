"""
Operator CLI for the careers service. Run from business-intelligence/scripts:

  python3 -m careers.admin authorize                 # one-time: get hello@'s refresh token
  python3 -m careers.admin setup [--test]            # one-time: create folders + tracker
  python3 -m careers.admin check-access              # no link sharing on the folder tree
  python3 -m careers.admin reconcile [--dry-run]     # finish part-stored applications
  python3 -m careers.admin retention [--as-of DATE]  # list applications due for review
  python3 -m careers.admin delete GOJI-APP-2026-0001 --confirm

Everything except `authorize` needs the three CAREERS_GOOGLE_* env vars (and,
after setup, the CAREERS_DRIVE_* / CAREERS_TRACKER_ID ones). Full steps are in
README.md. Output never prints applicant names or contact details: references
only.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import http.server
import secrets
import sys
import threading
import urllib.parse
import webbrowser
from datetime import date

import requests

from . import config
from .google_store import (SCOPE, TOKEN_URL, GoogleStore, folder_url, sheet_url)
from .pipeline import STATUS_COLUMN, STATUSES, TRACKER_COLUMNS, reconcile

TRACKER_NAME = "Goji Recruitment — Applicant Tracker"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"


# ---- authorize ----------------------------------------------------------------
def cmd_authorize(args) -> int:
    """Loopback OAuth (Desktop-app client) with PKCE. Sign in as
    hello@gojiphysio.com when the browser opens. Prints the refresh token once;
    put it straight into Secret Manager (README) and don't save it anywhere else."""
    cid = args.client_id or config.GOOGLE_CLIENT_ID
    secret = args.client_secret or config.GOOGLE_CLIENT_SECRET
    if not (cid and secret):
        print("Set CAREERS_GOOGLE_CLIENT_ID / CAREERS_GOOGLE_CLIENT_SECRET (or pass "
              "--client-id/--client-secret).", file=sys.stderr)
        return 2
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    got: dict = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            got.update({k: v[0] for k, v in q.items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Done. You can close this tab and return to the terminal.")

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    redirect = f"http://127.0.0.1:{srv.server_port}"
    url = AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": cid, "redirect_uri": redirect, "response_type": "code",
        "scope": SCOPE, "access_type": "offline", "prompt": "consent",
        "login_hint": "hello@gojiphysio.com", "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256"})
    print("Opening the Google consent page. Sign in as hello@gojiphysio.com.\n"
          f"If no browser opens, visit:\n{url}\n")
    webbrowser.open(url)
    t = threading.Thread(target=srv.handle_request)
    t.start()
    t.join(timeout=300)
    srv.server_close()
    if got.get("state") != state or "code" not in got:
        print(f"Authorisation failed: {got.get('error', 'no code received')}", file=sys.stderr)
        return 1
    r = requests.post(TOKEN_URL, timeout=15, data={
        "client_id": cid, "client_secret": secret, "code": got["code"],
        "code_verifier": verifier, "grant_type": "authorization_code",
        "redirect_uri": redirect})
    body = r.json()
    if "refresh_token" not in body:
        print(f"No refresh token returned: {body.get('error')}", file=sys.stderr)
        return 1
    if body.get("scope", "").strip() != SCOPE:
        print(f"Warning: granted scope is {body.get('scope')!r}, expected {SCOPE}.")
    print("Refresh token (store it in Secret Manager now, then clear your terminal):\n")
    print(body["refresh_token"])
    return 0


# ---- setup ----------------------------------------------------------------------
def _tracker_requests(sheet_gid: int) -> list[dict]:
    ncols = len(TRACKER_COLUMNS)
    return [
        {"updateSheetProperties": {
            "properties": {"sheetId": sheet_gid, "gridProperties": {"frozenRowCount": 1}},
            "fields": "gridProperties.frozenRowCount"}},
        {"repeatCell": {
            "range": {"sheetId": sheet_gid, "startRowIndex": 0, "endRowIndex": 1},
            "cell": {"userEnteredFormat": {"textFormat": {"bold": True},
                                           "wrapStrategy": "WRAP"}},
            "fields": "userEnteredFormat(textFormat,wrapStrategy)"}},
        {"setBasicFilter": {"filter": {"range": {
            "sheetId": sheet_gid, "startRowIndex": 0, "startColumnIndex": 0,
            "endColumnIndex": ncols}}}},
        {"setDataValidation": {
            "range": {"sheetId": sheet_gid, "startRowIndex": 1,
                      "startColumnIndex": STATUS_COLUMN, "endColumnIndex": STATUS_COLUMN + 1},
            "rule": {"condition": {"type": "ONE_OF_LIST",
                                   "values": [{"userEnteredValue": s} for s in STATUSES]},
                     "strict": True, "showCustomUi": True}}},
        {"setDataValidation": {
            "range": {"sheetId": sheet_gid, "startRowIndex": 1,
                      "startColumnIndex": TRACKER_COLUMNS.index("Interview date"),
                      "endColumnIndex": TRACKER_COLUMNS.index("Interview date") + 1},
            "rule": {"condition": {"type": "DATE_IS_VALID"}, "strict": False}}},
        # Warn (not block) before anyone edits the header row: the service and
        # reconcile match on these column positions.
        {"addProtectedRange": {"protectedRange": {
            "range": {"sheetId": sheet_gid, "startRowIndex": 0, "endRowIndex": 1},
            "description": "Header row - the careers service relies on this column order",
            "warningOnly": True}}},
    ]


def cmd_setup(args) -> int:
    s = GoogleStore()
    suffix = " (TEST)" if args.test else ""
    root = s.create_folder(f"Goji Recruitment{suffix}", None,
                           {"kind": "careers_root", "env": "test" if args.test else "prod"})
    apps = s.create_folder("Applications", root["id"])
    sheet = s.create_spreadsheet({
        "properties": {"title": TRACKER_NAME + suffix, "timeZone": "Asia/Singapore",
                       "locale": "en_GB"},
        "sheets": [{"properties": {"title": config.TRACKER_TAB, "sheetId": 0}}]})
    sid = sheet["spreadsheetId"]
    s.move(sid, root["id"])
    s.append_row(sid, config.TRACKER_TAB, TRACKER_COLUMNS)
    s.batch_update(sid, _tracker_requests(0))
    print(f"Created{suffix}:")
    print(f"  Root folder:    {folder_url(root['id'])}")
    print(f"  Tracker:        {sheet_url(sid)}")
    print("\nSet these on the service (deploy.sh / the workflow):")
    print(f"  CAREERS_DRIVE_ROOT_ID={root['id']}")
    print(f"  CAREERS_DRIVE_APPLICATIONS_ID={apps['id']}")
    print(f"  CAREERS_TRACKER_ID={sid}")
    print("\nThe folder is private to hello@. Share it (Editor) with named HR / "
          "management people only - never 'Anyone with the link'.")
    return 0


# ---- check-access ------------------------------------------------------------
def cmd_check_access(_args) -> int:
    s = GoogleStore()
    bad = 0
    for fid, label in ((config.DRIVE_ROOT_ID, "root folder"), (config.TRACKER_ID, "tracker")):
        for p in s.permissions(fid):
            who = p.get("emailAddress") or p.get("type")
            flag = p.get("type") in ("anyone", "domain")
            bad += flag
            print(f"{'!! ' if flag else '   '}{label}: {p.get('role')} - {who}")
    if bad:
        print("\nLink or domain-wide sharing found. Remove it in Drive (Share -> "
              "General access -> Restricted).")
    return 1 if bad else 0


# ---- reconcile -----------------------------------------------------------------
def cmd_reconcile(args) -> int:
    actions = reconcile(GoogleStore(), dry_run=args.dry_run)
    print("\n".join(actions) or "Nothing to do: every application is complete.")
    return 0


# ---- retention -------------------------------------------------------------------
def cmd_retention(args) -> int:
    """Read-only. Lists applications whose retention review date has passed and
    whose status is not Hired, so a person can decide what to delete."""
    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
    s = GoogleStore()
    rows = s.rows(config.TRACKER_ID, config.TRACKER_TAB)
    i_ref = 0
    i_status = STATUS_COLUMN
    i_review = TRACKER_COLUMNS.index("Retention review date")
    i_pool = TRACKER_COLUMNS.index("Talent pool consent")
    due = []
    for r in rows[1:]:
        r = r + [""] * (len(TRACKER_COLUMNS) - len(r))
        try:
            review = date.fromisoformat(r[i_review][:10])
        except ValueError:
            continue
        if review <= as_of and r[i_status] != "Hired":
            due.append(f"{r[i_ref]}  status={r[i_status] or '-'}  "
                       f"talent_pool={r[i_pool]}  review_date={review}")
    print("\n".join(due) or f"No applications due for review as of {as_of}.")
    return 0


# ---- delete ----------------------------------------------------------------------
def cmd_delete(args) -> int:
    s = GoogleStore()
    folder = s.find_folder_by_property("reference", args.reference)
    if not folder:
        print(f"No application folder for {args.reference}.", file=sys.stderr)
        return 1
    if not args.confirm:
        print(f"Would move {args.reference}'s folder (CV + summary) to Drive's Bin. "
              "Re-run with --confirm.")
        return 0
    s.trash(folder["id"])
    print(f"{args.reference}: folder moved to the Bin (Google empties it after 30 "
          "days). Now delete its row in the tracker by hand, and any emails "
          "about it in hello@'s mailbox.")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="careers.admin")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("authorize")
    a.add_argument("--client-id")
    a.add_argument("--client-secret")
    a.set_defaults(fn=cmd_authorize)
    st = sub.add_parser("setup")
    st.add_argument("--test", action="store_true", help="create the TEST folder + tracker")
    st.set_defaults(fn=cmd_setup)
    sub.add_parser("check-access").set_defaults(fn=cmd_check_access)
    rc = sub.add_parser("reconcile")
    rc.add_argument("--dry-run", action="store_true")
    rc.set_defaults(fn=cmd_reconcile)
    rt = sub.add_parser("retention")
    rt.add_argument("--as-of")
    rt.set_defaults(fn=cmd_retention)
    d = sub.add_parser("delete")
    d.add_argument("reference")
    d.add_argument("--confirm", action="store_true")
    d.set_defaults(fn=cmd_delete)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
