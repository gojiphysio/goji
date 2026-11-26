"""
Submit a WhatsApp message template in this folder to Meta, or check its status,
through the provider (Dualhook: POST /<WABA_ID>/message_templates).

  WA_TOKEN=$(gcloud secrets versions access latest --secret=wa-token --project goji-bi) \\
    python -m wa_agent.templates.submit goji_referral_followup --waba <WABA_ID>
  ... --status        # the template's current status and category

The WABA id is shown on the Dualhook connection (Connection > Overview); the
API key is bound to it, so no other id works. Meta may re-categorise a
UTILITY template as MARKETING; the status output shows the category it kept.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

import requests

HERE = pathlib.Path(__file__).parent
BASE = os.environ.get("WA_API_BASE", "https://api.dualhook.com/v25.0").rstrip("/")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--waba", required=True)
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args(argv)
    token = os.environ.get("WA_TOKEN", "")
    if not token:
        sys.exit("set WA_TOKEN (the wa-token secret)")
    headers = {"Authorization": f"Bearer {token}"}
    if a.status:
        r = requests.get(f"{BASE}/{a.waba}/message_templates", headers=headers, timeout=30,
                         params={"name": a.name, "fields": "id,name,language,status,category,"
                                 "rejected_reason"})
    else:
        body = json.loads((HERE / f"{a.name}.json").read_text())
        r = requests.post(f"{BASE}/{a.waba}/message_templates", json=body, headers=headers,
                          timeout=30)
    print(r.status_code, r.text)
    return 0 if r.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
