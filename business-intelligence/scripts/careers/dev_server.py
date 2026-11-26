"""
Local harness for the careers form: the real Flask app with in-memory
Drive/Sheets and emails printed instead of sent. Safe to click through with
made-up data.

    cd business-intelligence/scripts
    uv run --with-requirements careers/requirements.txt python -m careers.dev_server

Pair it with the website started with PUBLIC_CAREERS_API=http://localhost:8090
(the `website-careers-dev` entry in .claude/launch.json). DEV_FAIL=upload or
DEV_FAIL=append makes storage fail, to see the error message.
"""
from __future__ import annotations

import os

from . import app as app_module
from . import config, mailer, vacancies
from .fakes import VACANCIES, FakeWorkspace


def main() -> None:
    ws = FakeWorkspace()
    ws.fail = {f for f in os.environ.get("DEV_FAIL", "").split(",") if f}
    app_module._ws = ws
    config.APPLICATIONS_FOLDER_ID = "LOCAL-FOLDER"
    config.TRACKER_SHEET_ID = "LOCAL-SHEET"
    config.CORS_ORIGINS = ["http://localhost:4232", "http://localhost:4233", "http://localhost:4234"]
    config.MIN_FILL_MS = int(os.environ.get("CAREERS_MIN_FILL_MS", "3000"))
    config.SMTP_PASS = "dev"
    vacancies._fetch = lambda: VACANCIES
    mailer._send = lambda msg: print(f"[dev email] To={msg['To']} Subject={msg['Subject']}")

    @app_module.app.route("/dev/state")
    def _state():  # local only: what the fake Drive/Sheets now hold
        return {"files": [f["name"] for f in ws.files.values()], "rows": len(ws.rows)}

    app_module.app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "8090")))


if __name__ == "__main__":
    main()
