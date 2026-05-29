#!/usr/bin/env python3
"""
Cross-reference appointment.doctor (resolved via calendar) against
invoice.doctor for the same patient on the same date, to find invoice
mis-attributions while appointments are correct.

Appointments carry a `color` field that maps to a calendar; each calendar
in /appointment/calendars carries a `doctor` code. That doctor is the
"intended" provider. We compare it to:
  - the EARLIEST snapshot of the invoice's doctor (closest we have to
    "what was first entered")
  - the LATEST snapshot of the invoice's doctor (current state, after
    any corrections)

Output: every (patient, date) pair where appointment.doctor disagreed
with either the initial or current invoice.doctor.

Usage:
    export PLATO_API_KEY=$(gcloud secrets versions access latest --secret=plato-api-key)
    python3 cross_reference_invoice_doctor.py [days_back]
        days_back defaults to 30
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

PLATO_BASE = "https://clinic.platomedical.com/api"
BQ_PROJECT = "goji-bi"


def must_env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        sys.exit(f"set {name}")
    return v


def fetch_calendars(s: requests.Session, db: str) -> dict[str, str]:
    """Return {color: doctor_code}. Plato calendars carry a single doctor
    each; the appointment.color picks which calendar an appt belongs to."""
    r = s.get(f"{PLATO_BASE}/{db}/appointment/calendars", timeout=30)
    r.raise_for_status()
    out: dict[str, str] = {}
    for cal in r.json():
        c, d = cal.get("color"), cal.get("doctor")
        if c and d:
            out[c] = d
    return out


def fetch_appointments(s: requests.Session, db: str, start: str, end: str) -> list[dict]:
    """Pull all appointments in [start, end] (YYYY-MM-DD)."""
    rows: list[dict] = []
    page = 1
    while True:
        r = s.get(
            f"{PLATO_BASE}/{db}/appointment",
            params={"start_date": start, "end_date": end, "current_page": page},
            timeout=30,
        )
        if r.status_code != 200:
            sys.exit(f"appointment fetch failed page={page} status={r.status_code} body={r.text[:400]}")
        body = r.json()
        page_rows = body if isinstance(body, list) else (body.get("appointments") or body.get("data") or [])
        if not page_rows:
            break
        rows.extend(page_rows)
        if len(page_rows) < 20:  # default page size on Plato
            break
        page += 1
        time.sleep(2)
    return rows


def bq_query(sql: str) -> list[dict]:
    out = subprocess.run(
        ["bq", "query", "--use_legacy_sql=false", "--format=json", "--max_rows=100000", sql],
        capture_output=True, text=True, check=False,
    )
    if out.returncode != 0:
        sys.exit(f"bq query failed:\n{out.stderr}")
    return json.loads(out.stdout or "[]")


def fetch_invoice_states(start: str, end: str) -> list[dict]:
    """One row per invoice with both initial and current doctor."""
    sql = f"""
    WITH ranked AS (
      SELECT
        invoice_id,
        invoice_date,
        _loaded_at,
        JSON_VALUE(payload, '$.patient_id')   AS patient_id,
        JSON_VALUE(payload, '$.doctor')       AS doctor,
        JSON_VALUE(payload, '$.created_by')   AS created_by,
        JSON_VALUE(payload, '$.created_on')   AS created_on,
        JSON_VALUE(payload, '$.last_edited_by') AS last_edited_by,
        JSON_VALUE(payload, '$.last_edited')    AS last_edited,
        JSON_VALUE(payload, '$.invoice_prefix') AS invoice_prefix,
        SAFE_CAST(JSON_VALUE(payload, '$.invoice') AS INT64) AS invoice_no,
        SAFE_CAST(JSON_VALUE(payload, '$.void') AS INT64) = 1 AS is_void,
        ROW_NUMBER() OVER (PARTITION BY invoice_id ORDER BY _loaded_at ASC)  AS rn_first,
        ROW_NUMBER() OVER (PARTITION BY invoice_id ORDER BY _loaded_at DESC) AS rn_last
      FROM `goji-bi.raw_plato.invoices_raw`
      WHERE invoice_date BETWEEN DATE('{start}') AND DATE('{end}')
    ),
    first_state AS (
      SELECT invoice_id, doctor AS initial_doctor, _loaded_at AS first_loaded_at
      FROM ranked WHERE rn_first = 1
    ),
    last_state AS (
      SELECT invoice_id, doctor AS current_doctor, _loaded_at AS last_loaded_at,
             patient_id, invoice_date, created_by, created_on,
             last_edited_by, last_edited, invoice_prefix, invoice_no, is_void
      FROM ranked WHERE rn_last = 1
    )
    SELECT
      l.invoice_id, l.invoice_date, l.patient_id,
      f.initial_doctor, l.current_doctor,
      l.created_by, l.created_on,
      l.last_edited_by, l.last_edited,
      l.invoice_prefix, l.invoice_no, l.is_void,
      FORMAT_TIMESTAMP('%Y-%m-%d %H:%M:%S', f.first_loaded_at) AS first_loaded_at,
      FORMAT_TIMESTAMP('%Y-%m-%d %H:%M:%S', l.last_loaded_at)  AS last_loaded_at
    FROM last_state l
    JOIN first_state f USING (invoice_id)
    ORDER BY l.invoice_date, l.invoice_no
    """
    return bq_query(sql)


def main() -> int:
    days_back = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    api_key = must_env("PLATO_API_KEY")
    db = os.environ.get("PLATO_DB", "gojihealth")

    today = datetime.now(timezone.utc).date()
    start = (today - timedelta(days=days_back)).isoformat()
    end = today.isoformat()
    print(f"window: {start} .. {end}  (days_back={days_back})", file=sys.stderr)

    s = requests.Session()
    s.headers.update({"accept": "application/json", "Authorization": f"Bearer {api_key}"})

    color_to_doctor = fetch_calendars(s, db)
    print(f"calendars: {color_to_doctor}", file=sys.stderr)

    appts = fetch_appointments(s, db, start, end)
    print(f"appointments fetched: {len(appts)}", file=sys.stderr)

    # Index appointments by (patient_id, date). One patient could have
    # multiple appointments on the same day; collect all calendar doctors.
    appt_idx: dict[tuple[str, str], list[dict]] = {}
    for a in appts:
        pid = a.get("patient_id")
        st = a.get("starttime") or ""
        date = st[:10]
        if not pid or not date:
            continue
        doc_from_cal = color_to_doctor.get(a.get("color") or "")
        appt_idx.setdefault((pid, date), []).append({
            "doctor_from_calendar": doc_from_cal,
            "doctor_field": a.get("doctor") or None,  # almost always blank in Plato
            "color": a.get("color"),
            "starttime": st,
            "created_by": a.get("created_by"),
            "last_edited_by": a.get("last_edited_by"),
            "title": a.get("title"),
        })

    invoices = fetch_invoice_states(start, end)
    print(f"invoices in window: {len(invoices)}\n", file=sys.stderr)

    # Walk invoices, find matched appointment, compare doctors.
    mismatches: list[dict] = []
    no_appt: list[dict] = []
    matched_ok = 0
    corrected_after_load = 0

    for inv in invoices:
        # bq query --format=json returns all values as strings, including bools
        if str(inv.get("is_void")).lower() == "true":
            continue
        key = (inv["patient_id"], inv["invoice_date"])
        appts_today = appt_idx.get(key, [])
        if not appts_today:
            no_appt.append(inv)
            continue
        appt_doctors = {a["doctor_from_calendar"] for a in appts_today if a["doctor_from_calendar"]}
        if not appt_doctors:
            no_appt.append(inv)
            continue
        initial = inv.get("initial_doctor")
        current = inv.get("current_doctor")
        if initial != current:
            corrected_after_load += 1
        # An invoice is consistent if either the initial OR current doctor
        # appears among the patient's appointment-calendar doctors that day.
        # The interesting cases:
        #   1) initial NOT in appt_doctors -> wrong from the start
        #   2) current NOT in appt_doctors -> currently wrong (maybe never fixed)
        if initial in appt_doctors and current in appt_doctors:
            matched_ok += 1
            continue
        mismatches.append({
            "invoice_id": inv["invoice_id"],
            "invoice_no": f"{inv.get('invoice_prefix') or ''}{inv.get('invoice_no') or ''}",
            "date": inv["invoice_date"],
            "patient_id": inv["patient_id"],
            "appointment_doctors": sorted(appt_doctors),
            "initial_doctor": initial,
            "current_doctor": current,
            "created_by": inv.get("created_by"),
            "last_edited_by": inv.get("last_edited_by"),
            "last_edited": inv.get("last_edited"),
        })

    non_void = [i for i in invoices if str(i.get("is_void")).lower() != "true"]
    print(f"=== Cross-reference summary ===")
    print(f"  invoices total (non-void):     {len(non_void)}")
    print(f"  matched OK:                    {matched_ok}")
    print(f"  no appointment same-day:       {len(no_appt)}")
    print(f"  doctor changed since ingest:   {corrected_after_load}")
    print(f"  MISMATCHES (initial OR current != any appt.doctor): {len(mismatches)}")
    print()

    if mismatches:
        print("=== Mismatches ===")
        for m in mismatches:
            change_marker = ""
            if m["initial_doctor"] != m["current_doctor"]:
                change_marker = f"   [CORRECTED {m['initial_doctor']} -> {m['current_doctor']}]"
            print(f"  {m['date']}  {m['invoice_no']:<10}  appt={m['appointment_doctors']}  "
                  f"inv_initial={m['initial_doctor']!r}  inv_current={m['current_doctor']!r}{change_marker}")
            print(f"    created_by={m['created_by']!r}  last_edited_by={m['last_edited_by']!r} on {m['last_edited']}  "
                  f"invoice_id={m['invoice_id']}  patient_id={m['patient_id']}")
        print()
    if no_appt:
        print(f"=== {len(no_appt)} invoices with no appointment on same date (skipped) ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
