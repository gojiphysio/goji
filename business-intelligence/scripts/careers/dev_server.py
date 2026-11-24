"""
Local harness for the careers form: the real Flask app, with an in-memory
Drive/Sheets double and emails printed instead of sent. Nothing leaves the
machine, so it is safe to click through with made-up data.

    cd business-intelligence/scripts
    uv run --with-requirements careers/requirements.txt --with pytest \\
        python -m careers.dev_server            # http://localhost:8090

Pair it with the website started with PUBLIC_CAREERS_API=http://localhost:8090
(the `website-careers-dev` entry in .claude/launch.json does both URLs).
Inject failures with DEV_FAIL=upload|append|... to exercise the error paths.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import app as app_module
from . import config, mailer, vacancies
from .conftest import FakeWorkspace

SITE_DIST = Path(__file__).resolve().parents[3] / "marketing" / "website" / "dist" / "careers" / "vacancies.json"
SITE_SRC = Path(__file__).resolve().parents[3] / "marketing" / "website" / "src" / "lib" / "vacancies.ts"


def _local_vacancies():
    if SITE_DIST.exists():
        rows = json.loads(SITE_DIST.read_text())["vacancies"]
        return {v["id"]: v for v in rows}
    # No build yet: both physio roles open, as configured on the site.
    return {i: {"id": i, "title": t, "open": True, "form": "physio", "min_days_per_week": 3,
                "closing_date": None, "also_consider_for": [o], "drive_folder": t}
            for i, t, o in (("physiotherapist", "Physiotherapist", "senior-physiotherapist"),
                            ("senior-physiotherapist", "Senior Physiotherapist", "physiotherapist"))}


def main() -> None:
    ws = FakeWorkspace()
    ws.fail = {f for f in os.environ.get("DEV_FAIL", "").split(",") if f}
    app_module._ws = ws
    config.APPLICATIONS_FOLDER_ID = "APPS"
    config.TRACKER_SHEET_ID = "LOCAL-SHEET"
    config.CORS_ORIGINS = ["http://localhost:4232", "http://localhost:4234", "http://localhost:4233"]
    config.MIN_FILL_MS = int(os.environ.get("CAREERS_MIN_FILL_MS", "3000"))
    config.SMTP_PASS = "dev"
    vacancies._fetch = _local_vacancies

    def fake_send(msg):
        print(f"[dev email] To={msg['To']} Subject={msg['Subject']}")
    mailer._send = fake_send

    @app_module.app.route("/dev/state")
    def _state():  # local only: what the fake Drive/Sheets now hold
        return {"folders": [f["name"] for f in ws.app_folders()],
                "rows": len(ws.rows),
                "files": [f["name"] for f in ws.files.values() if not f["folder"]]}

    app_module.app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "8090")))


if __name__ == "__main__":
    main()
