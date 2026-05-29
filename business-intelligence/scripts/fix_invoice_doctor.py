#!/usr/bin/env python3
"""
Correct the `doctor` field on a hard-coded list of Plato invoices using
PUT /{db}/invoice. Preserves and appends to any existing `remarks` so the
correction is auditable.

This is a one-shot script for the 2026-05-26 mis-attribution cleanup.
Re-runs are safe: if an invoice already has the target doctor, the PUT is
skipped.

Usage:
    export PLATO_API_KEY=$(gcloud secrets versions access latest --secret=plato-api-key)
    python3 fix_invoice_doctor.py            # dry-run, prints what would happen
    python3 fix_invoice_doctor.py --apply    # actually call Plato
"""
from __future__ import annotations

import os
import sys
import time
from datetime import date

import requests

PLATO_BASE = "https://clinic.platomedical.com/api"
AUDIT_NOTE = f"Doctor corrected by BI cross-ref vs same-day appointment calendar on {date.today().isoformat()}"

CORRECTIONS = [
    # (invoice_no_label, invoice_id, expected_current_doctor, target_doctor)
    ("GLM-68",  "8e3e50ebe59025645bec6a2b7b80abaa", "PCN", "PKN"),
    ("GLM-82",  "8ccc92ad023b679254fc3883df2fe067", "PCN", "PCL"),
    ("GLM-94",  "eb6f2564d65070ba3e0b4168564821dd", "PCN", "PCL"),
    ("GLM-112", "40411bb9033ab6fde9fdeb7875d70205", "PCN", "PCL"),
    ("GLM-123", "6e7b779b87cb0a1cf0402045dd51c930", "PCN", "PCL"),
]


def must_env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        sys.exit(f"set {name}")
    return v


def fetch_invoice(s: requests.Session, db: str, invoice_id: str) -> dict:
    """Pull current invoice state so we can check doctor + preserve remarks."""
    r = s.get(f"{PLATO_BASE}/{db}/invoice", params={"invoice_id": invoice_id, "include_drafts": "true"}, timeout=30)
    r.raise_for_status()
    body = r.json()
    rows = body if isinstance(body, list) else (body.get("invoices") or body.get("data") or [])
    for inv in rows:
        if (inv.get("_id") or inv.get("id")) == invoice_id:
            return inv
    sys.exit(f"invoice_id={invoice_id} not found in API response")


def main() -> int:
    apply_changes = "--apply" in sys.argv
    api_key = must_env("PLATO_API_KEY")
    db = os.environ.get("PLATO_DB", "gojihealth")

    mode = "APPLY" if apply_changes else "DRY-RUN"
    print(f"=== {mode} mode  db={db}  audit_note={AUDIT_NOTE!r} ===\n")

    s = requests.Session()
    s.headers.update({
        "accept": "application/json",
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    })

    summary = []
    for label, invoice_id, expected_doctor, target_doctor in CORRECTIONS:
        print(f"--- {label}  invoice_id={invoice_id} ---")
        inv = fetch_invoice(s, db, invoice_id)
        current_doctor = inv.get("doctor")
        current_remarks = inv.get("remarks") or ""

        if current_doctor == target_doctor:
            print(f"  SKIP: already doctor={target_doctor!r}")
            summary.append((label, "skip-already-correct"))
            continue
        if current_doctor != expected_doctor:
            print(f"  WARN: expected current doctor={expected_doctor!r} but found {current_doctor!r}. "
                  f"Aborting this invoice — re-investigate before forcing.")
            summary.append((label, f"abort-doctor-was-{current_doctor}"))
            continue

        new_remarks = (current_remarks + ("\n" if current_remarks else "") + AUDIT_NOTE)

        body = {
            "invoice_id": invoice_id,
            "doctor": target_doctor,
            "remarks": new_remarks,
        }
        print(f"  PLAN: doctor {current_doctor!r} -> {target_doctor!r}, "
              f"remarks: {len(current_remarks)} chars + audit line ({len(new_remarks)} total)")

        if not apply_changes:
            summary.append((label, "dry-run"))
            continue

        r = s.put(f"{PLATO_BASE}/{db}/invoice", json=body, timeout=30)
        if r.status_code >= 300:
            print(f"  FAIL status={r.status_code} body={r.text[:400]}")
            summary.append((label, f"http-{r.status_code}"))
            continue
        # Re-fetch to confirm
        time.sleep(1)
        confirm = fetch_invoice(s, db, invoice_id)
        if confirm.get("doctor") == target_doctor:
            print(f"  OK: confirmed doctor={confirm.get('doctor')!r}  last_edited_by={confirm.get('last_edited_by')!r}")
            summary.append((label, "applied"))
        else:
            print(f"  WARN: post-PUT doctor is {confirm.get('doctor')!r}, expected {target_doctor!r}")
            summary.append((label, f"post-doctor-{confirm.get('doctor')}"))
        # gentle pacing
        time.sleep(2)

    print("\n=== Summary ===")
    for label, status in summary:
        print(f"  {label:<8}  {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
