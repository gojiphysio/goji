#!/usr/bin/env python3
"""
Plato API probe - discovery script.

Goal: hit a wide set of endpoints once, capture one sample row from each,
and write everything to probe_output.json so we can inspect actual field names
and figure out where inventory movements live.

Run:
    cd "/Users/charles/Documents/Claude/Projects/Goji Business Inteligence/scripts"
    pip3 install requests
    export PLATO_DB=gojihealth
    export PLATO_API_KEY=...your_key...
    python3 plato_probe.py

It writes ./probe_output.json next to this script. Nothing is sent anywhere.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

BASE = "https://clinic.platomedical.com/api"
SWAGGER_URL = "https://clinic.platomedical.com/swagger/api.json?basePath=/api/"
PAGE_SLEEP_S = 3
TIMEOUT_S = 30


def must_env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        sys.exit(f"Set env var {name}")
    return v


def hit(session: requests.Session, method: str, url: str, **kwargs):
    """Single HTTP call with rate-limit aware throttling. Returns (status, body, headers)."""
    r = session.request(method, url, timeout=TIMEOUT_S, **kwargs)
    rem = r.headers.get("x-ratelimit-remaining")
    if rem is not None and rem.isdigit() and int(rem) < 2:
        time.sleep(60)
    else:
        time.sleep(PAGE_SLEEP_S)
    body: object
    try:
        body = r.json()
    except ValueError:
        body = r.text[:2000]
    return r.status_code, body, dict(r.headers)


def summarize(name: str, status: int, body) -> dict:
    """Build a compact summary that's safe to log."""
    summary = {"endpoint": name, "status": status}
    if isinstance(body, list):
        summary["type"] = "list"
        summary["count"] = len(body)
        summary["first_row"] = body[0] if body else None
        if body and isinstance(body[0], dict):
            summary["first_row_keys"] = sorted(body[0].keys())
    elif isinstance(body, dict):
        summary["type"] = "object"
        summary["keys"] = sorted(body.keys())
        summary["body"] = body
    else:
        summary["type"] = "raw"
        summary["body"] = body
    return summary


def main() -> None:
    db = must_env("PLATO_DB")
    key = must_env("PLATO_API_KEY")

    session = requests.Session()
    session.headers.update({
        "accept": "application/json",
        "Authorization": f"Bearer {key}",
    })

    today = datetime.now(timezone.utc).date().isoformat()
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")

    results = {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "db": db,
        "probes": [],
        "swagger": None,
    }

    # 1) Swagger JSON - the live endpoint catalogue
    print("=> swagger spec")
    try:
        r = session.get(SWAGGER_URL, timeout=TIMEOUT_S)
        if r.status_code == 200:
            spec = r.json()
            paths = sorted(spec.get("paths", {}).keys())
            results["swagger"] = {
                "status": 200,
                "path_count": len(paths),
                "paths": paths,
            }
            print(f"   {len(paths)} paths found")
            # Save full spec for offline browsing
            (Path(__file__).parent / "plato_swagger.json").write_text(json.dumps(spec, indent=2))
        else:
            results["swagger"] = {"status": r.status_code, "body": r.text[:500]}
    except Exception as e:
        results["swagger"] = {"error": str(e)}

    # 2) Probe list. Each tuple: (label, method, path, params)
    probes = [
        ("smoke:appointment_count",     "GET",  f"/{db}/appointment/count", None),
        ("systemsetup",                 "GET",  f"/{db}/systemsetup", None),
        ("appointment_list",            "GET",  f"/{db}/appointment", {"current_page": 1, "modified_since": week_ago}),
        ("appointment_calendars",       "GET",  f"/{db}/appointment/calendars", None),
        ("appointment_codes",           "GET",  f"/{db}/appointment/codes", None),
        ("invoice_list",                "GET",  f"/{db}/invoice", {"current_page": 1, "modified_since": week_ago}),
        ("invoice_count",               "GET",  f"/{db}/invoice/count", None),
        ("payment_list",                "GET",  f"/{db}/payment", {"current_page": 1, "modified_since": week_ago}),
        ("queue_today",                 "GET",  f"/{db}/queue", {"date": today}),
        ("queue_status_list",           "GET",  f"/{db}/queue/status/list", None),
        ("inventory_list",              "GET",  f"/{db}/inventory", {"current_page": 1}),
        ("patient_count",               "GET",  f"/{db}/patient/count", None),
        ("corporate_list",              "GET",  f"/{db}/corporate", {"current_page": 1}),
        ("reports_outstanding",         "GET",  f"/{db}/reports/outstanding", {"date": today}),
        ("reports_outstanding_packages","GET",  f"/{db}/reports/outstanding_packages", {"date": today}),
        ("reports_stock_count",         "GET",  f"/{db}/reports/stock_count", {"date": today}),
        ("reports_stock_count_detailed","GET",  f"/{db}/reports/stock_count_detailed", {"date": today}),
        # Inventory movement candidates - we don't know the exact endpoint yet
        ("transfer_list",               "GET",  f"/{db}/transfer", {"current_page": 1, "modified_since": week_ago}),
        ("adjustment_list",             "GET",  f"/{db}/adjustment", {"current_page": 1, "modified_since": week_ago}),
        ("deliveryorder_list",          "GET",  f"/{db}/deliveryorder", {"current_page": 1, "modified_since": week_ago}),
    ]

    for label, method, path, params in probes:
        url = BASE + path
        print(f"=> {label}")
        try:
            status, body, headers = hit(session, method, url, params=params)
            summary = summarize(label, status, body)
            results["probes"].append(summary)
            if status == 200:
                if summary.get("type") == "list":
                    print(f"   200 list len={summary['count']}")
                else:
                    print(f"   200 {summary.get('type')}")
            else:
                print(f"   {status}")
        except Exception as e:
            results["probes"].append({"endpoint": label, "error": str(e)})
            print(f"   ERROR {e}")

    out_path = Path(__file__).parent / "probe_output.json"
    out_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nWrote {out_path}")
    print(f"Also wrote plato_swagger.json (full live spec).")


if __name__ == "__main__":
    main()
