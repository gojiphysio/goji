#!/usr/bin/env python3
"""
Plato probe v2 - targeted gap-fill.

The first probe answered 'does the API work and what's the rough shape?'.
This second probe answers the specific questions in architecture/objectives.md:

  Q1: Selling vs delivering clinician on redemptions
  Q2: Discount semantics (selling_price vs sub_total vs discount vs disc_abs)
  Q3: Full inventory list - to seed the treatment-category mapping
  Q4: Where do condition tags live? (patient.custom / patient_note / patient.tags)
  Q5: Full queue_status_list (only saw 1 of 4 last time)
  Q6: Appointment cancellation signal - status change or hard delete?

Plus a few bonus probes that came up while writing this:
  - Full appointment_codes detail (the code_Bottom 'hDWW' on appointments)
  - Decode the patient.custom keys we saw (CrKA/WjbS/YuGW)
  - Pull patient_note structure

Run on your machine:
    cd "/Users/charles/Documents/Claude/Projects/Goji Business Inteligence/scripts"
    source ../.envrc        # or rely on direnv
    python3 plato_probe2.py

Writes probe2_output.json. Contains real patient info - gitignored.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE = "https://clinic.platomedical.com/api"
PAGE_SLEEP_S = 3
TIMEOUT_S = 30


def env(name):
    v = os.environ.get(name)
    if not v:
        sys.exit(f"set {name}")
    return v


def hit(session, method, url, **kw):
    r = session.request(method, url, timeout=TIMEOUT_S, **kw)
    rem = r.headers.get("x-ratelimit-remaining")
    time.sleep(60 if (rem and rem.isdigit() and int(rem) < 2) else PAGE_SLEEP_S)
    try:
        body = r.json()
    except ValueError:
        body = r.text[:2000]
    return r.status_code, body


def paged(session, url, params=None, max_pages=200):
    """Yield all rows across all pages."""
    page = 1
    while page <= max_pages:
        p = dict(params or {})
        p["current_page"] = page
        status, body = hit(session, "GET", url, params=p)
        if status != 200 or not isinstance(body, list) or not body:
            return
        for row in body:
            yield row
        page += 1


def main():
    db = env("PLATO_DB")
    key = env("PLATO_API_KEY")
    session = requests.Session()
    session.headers.update({
        "accept": "application/json",
        "Authorization": f"Bearer {key}",
    })

    out = {"ran_at": datetime.now(timezone.utc).isoformat(), "db": db, "findings": {}}

    # -- Q3: Full inventory list --
    print("=> Q3: full inventory list (all pages)")
    inventory = list(paged(session, f"{BASE}/{db}/inventory"))
    print(f"   pulled {len(inventory)} inventory items")
    out["findings"]["inventory_full"] = inventory

    # -- Q5: Full queue status list --
    print("=> Q5: queue_status_list (full)")
    status, body = hit(session, "GET", f"{BASE}/{db}/queue/status/list")
    out["findings"]["queue_statuses"] = body
    print(f"   {status}, statuses: {[s.get('name') for s in body] if isinstance(body, list) else body}")

    # -- systemsetup decoder for custom keys + appointment codes --
    print("=> systemsetup full body")
    status, body = hit(session, "GET", f"{BASE}/{db}/systemsetup")
    out["findings"]["systemsetup_full"] = body
    # Print top-level keys with sizes for orientation
    if isinstance(body, dict):
        for k, v in body.items():
            n = len(v) if isinstance(v, (list, dict)) else 1
            print(f"   systemsetup.{k}: {type(v).__name__} ({n})")

    # -- appointment_codes detail (we only saw the keys before) --
    print("=> appointment_codes (full)")
    status, body = hit(session, "GET", f"{BASE}/{db}/appointment/codes")
    out["findings"]["appointment_codes"] = body
    if isinstance(body, dict):
        for k, v in body.items():
            print(f"   codes.{k}: len={len(v) if isinstance(v,list) else '?'}")

    # -- Q4: pick a patient with rich data, fetch full record --
    print("=> Q4: pulling 5 patients (first page) to find a populated one")
    status, body = hit(session, "GET", f"{BASE}/{db}/patient", params={"current_page": 1})
    if isinstance(body, list) and body:
        # Pick one with a non-empty 'custom' or most fields populated
        out["findings"]["patient_list_sample"] = body[:5]
        # Choose the one with the longest stringified body (proxy for "richest")
        richest = max(body, key=lambda p: len(json.dumps(p, default=str)))
        pid = richest.get("_id")
        print(f"   richest patient id: {pid}")
        if pid:
            status, full = hit(session, "GET", f"{BASE}/{db}/patient/{pid}")
            out["findings"]["patient_full_sample"] = full
            print(f"   GET /patient/{pid}: {status}")
            # See if there's a 'note' subresource on this patient
            status, notes = hit(session, "GET", f"{BASE}/{db}/patient/{pid}/note")
            out["findings"]["patient_notes_sample"] = notes
            print(f"   GET /patient/{pid}/note: {status}, "
                  f"{(len(notes) if isinstance(notes, list) else 'object')}")

    # -- patient_note general list --
    print("=> patient_note list (first page)")
    status, body = hit(session, "GET", f"{BASE}/{db}/patient/note", params={"current_page": 1})
    out["findings"]["patient_note_list"] = body[:5] if isinstance(body, list) else body
    if isinstance(body, list) and body:
        print(f"   sample note keys: {sorted(body[0].keys())}")

    # -- Q2: find a discounted invoice --
    print("=> Q2: scanning recent invoices for a discounted one")
    found_discount = None
    found_adj = None
    found_redemption_with_different_doctor = None
    sample_lim = 60
    for inv in paged(session, f"{BASE}/{db}/invoice"):
        sample_lim -= 1
        if sample_lim <= 0:
            break
        # invoice-level adjustment
        if not found_adj and inv.get("adj_amount") and float(inv.get("adj_amount") or 0) != 0:
            found_adj = inv
        # line-level discount
        for it in inv.get("item") or []:
            if not found_discount and (
                float(it.get("discount") or 0) > 0
                or (float(it.get("selling_price") or 0) > 0
                    and float(it.get("sub_total") or 0) < float(it.get("selling_price") or 0)
                    * float(it.get("qty") or 1))
            ):
                found_discount = inv
                break
            # Redemption with potentially different delivering clinician
            others = it.get("others") or {}
            if isinstance(others, dict) and others.get("redeem_from"):
                if not found_redemption_with_different_doctor:
                    found_redemption_with_different_doctor = {
                        "redemption_invoice": inv,
                        "redeem_from_id": others.get("redeem_from"),
                        "redeem_alloc": others.get("redeem_alloc"),
                    }
        if found_discount and found_adj and found_redemption_with_different_doctor:
            break

    out["findings"]["discounted_invoice_example"] = found_discount
    out["findings"]["adjusted_invoice_example"] = found_adj
    print(f"   discounted invoice: {'FOUND' if found_discount else 'NOT FOUND'}")
    print(f"   adjusted invoice:   {'FOUND' if found_adj else 'NOT FOUND'}")

    # -- Q1: For the redemption we found, fetch the source invoice and compare doctors --
    if found_redemption_with_different_doctor:
        red_inv = found_redemption_with_different_doctor["redemption_invoice"]
        src_id = found_redemption_with_different_doctor["redeem_from_id"]
        print(f"=> Q1: comparing doctors on redemption {red_inv.get('_id', '')[:8]} vs source {src_id[:8]}")
        status, src = hit(session, "GET", f"{BASE}/{db}/invoice/{src_id}") if src_id else (None, None)
        out["findings"]["redemption_vs_source"] = {
            "redemption_doctor": red_inv.get("doctor"),
            "redemption_finalized_by": red_inv.get("finalized_by"),
            "redemption_date": red_inv.get("date"),
            "source_doctor": (src or {}).get("doctor") if isinstance(src, dict) else None,
            "source_finalized_by": (src or {}).get("finalized_by") if isinstance(src, dict) else None,
            "source_date": (src or {}).get("date") if isinstance(src, dict) else None,
            "redemption_inv_id": red_inv.get("_id"),
            "source_inv_id": src_id,
        }
        print(f"   redemption doctor: {red_inv.get('doctor')}  source doctor: "
              f"{(src or {}).get('doctor') if isinstance(src, dict) else '?'}")

    # -- Q6: appointment status / cancellation --
    print("=> Q6: pulling 50 appointments, look at status-like fields")
    appts = list(paged(session, f"{BASE}/{db}/appointment", max_pages=3))
    out["findings"]["appointments_sample"] = appts[:50]
    # Look for any field that suggests cancellation
    status_keys = set()
    for a in appts:
        for k in a.keys():
            if any(t in k.lower() for t in ["status", "cancel", "void", "delete", "code_"]):
                status_keys.add(k)
    out["findings"]["appointment_status_like_keys"] = sorted(status_keys)
    print(f"   appointment status-like keys seen: {sorted(status_keys)}")

    # -- Write output --
    out_path = Path(__file__).parent / "probe2_output.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
