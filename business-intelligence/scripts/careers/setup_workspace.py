"""
One-time setup of the recruitment folder tree and applicant tracker.

    cd business-intelligence/scripts
    GOOGLE_AUTH_MODE=service_account \\
      python3 -m careers.setup_workspace --parent <SHARED_DRIVE_OR_FOLDER_ID> [--test]

Creates, inside --parent:

    Goji Recruitment            ("Goji Recruitment (TEST)" with --test)
      Goji Recruitment — Applicant Tracker   (Google Sheet)
      Applications
        <this year>/  Physiotherapist, Senior Physiotherapist,
                      General Expressions of Interest
        <next year>/  (same)

Further year/role folders are created by the service on demand. The tracker
gets the header row, a frozen header, a filter, and dropdowns for
Recruitment status / Assessed seniority level / Talent pool consent.
Prints the env vars to give the service. Re-running creates a second tree, so
run it once per environment. It creates no sharing permissions: access comes
from the Shared Drive's (or parent folder's) membership.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

from . import config
from .workspace import DRIVE, SHEETS, Workspace, folder_url

ROLE_FOLDERS = ["Physiotherapist", "Senior Physiotherapist", config.GENERAL_FOLDER]
TRACKER_NAME = "Goji Recruitment — Applicant Tracker"


def _col(name: str) -> int:
    return config.TRACKER_COLUMNS.index(name)


def _dropdown(sheet_id: int, col: int, values: list[str]) -> dict:
    return {"setDataValidation": {
        "range": {"sheetId": sheet_id, "startRowIndex": 1, "startColumnIndex": col,
                  "endColumnIndex": col + 1},
        "rule": {"condition": {"type": "ONE_OF_LIST",
                               "values": [{"userEnteredValue": v} for v in values]},
                 "showCustomUi": True, "strict": False}}}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parent", required=True, help="Shared Drive ID or folder ID to create the tree in")
    ap.add_argument("--test", action="store_true", help="name the tree as the TEST environment")
    a = ap.parse_args()

    ws = Workspace()
    suffix = " (TEST)" if a.test else ""
    root = ws.create_folder(f"Goji Recruitment{suffix}", a.parent)
    apps = ws.create_folder("Applications", root["id"])
    year = datetime.now(timezone(timedelta(hours=8))).year
    for y in (year, year + 1):
        yf = ws.create_folder(str(y), apps["id"])
        for name in ROLE_FOLDERS:
            ws.create_folder(name, yf["id"])

    sheet = ws._call("POST", f"{DRIVE}/files", "drive.create_sheet",
                     params={"supportsAllDrives": "true", "fields": "id"},
                     json={"name": TRACKER_NAME + suffix, "parents": [root["id"]],
                           "mimeType": "application/vnd.google-apps.spreadsheet"})
    sid = sheet["id"]
    meta = ws._call("GET", f"{SHEETS}/{sid}", "sheets.meta",
                    params={"fields": "sheets.properties"})
    tab_id = meta["sheets"][0]["properties"]["sheetId"]
    n = len(config.TRACKER_COLUMNS)
    requests_ = [
        {"updateSheetProperties": {
            "properties": {"sheetId": tab_id, "title": config.TRACKER_TAB,
                           "gridProperties": {"frozenRowCount": 1, "columnCount": n}},
            "fields": "title,gridProperties.frozenRowCount,gridProperties.columnCount"}},
        {"updateCells": {
            "range": {"sheetId": tab_id, "startRowIndex": 0, "endRowIndex": 1,
                      "startColumnIndex": 0, "endColumnIndex": n},
            "rows": [{"values": [{"userEnteredValue": {"stringValue": c},
                                  "userEnteredFormat": {"textFormat": {"bold": True},
                                                        "wrapStrategy": "WRAP"}}
                                 for c in config.TRACKER_COLUMNS]}],
            "fields": "userEnteredValue,userEnteredFormat"}},
        {"setBasicFilter": {"filter": {"range": {"sheetId": tab_id, "startRowIndex": 0,
                                                 "startColumnIndex": 0, "endColumnIndex": n}}}},
        _dropdown(tab_id, _col("Recruitment status"), config.RECRUITMENT_STATUSES),
        _dropdown(tab_id, _col("Assessed seniority level"), config.ASSESSED_LEVELS),
        _dropdown(tab_id, _col("Talent pool consent"), ["Yes", "No"]),
        # Warn (not block) anyone editing the header, so the columns the service
        # appends into can't be renamed or reordered by accident.
        {"addProtectedRange": {"protectedRange": {
            "range": {"sheetId": tab_id, "startRowIndex": 0, "endRowIndex": 1},
            "description": "Tracker header: the careers service writes by column position",
            "warningOnly": True}}},
    ]
    ws._call("POST", f"{SHEETS}/{sid}:batchUpdate", "sheets.batchUpdate",
             json={"requests": requests_})

    print("Created:")
    print(f"  Recruitment folder : {folder_url(root['id'])}")
    print(f"  Applicant tracker  : https://docs.google.com/spreadsheets/d/{sid}/edit")
    print("\nService env vars:")
    print(f"  RECRUITMENT_APPLICATIONS_FOLDER_ID={apps['id']}")
    print(f"  RECRUITMENT_TRACKER_SHEET_ID={sid}")
    print(f"  RECRUITMENT_TRACKER_TAB={config.TRACKER_TAB}")


if __name__ == "__main__":
    main()
