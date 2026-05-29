#!/usr/bin/env python3
"""
Investigate whether an invoice's `doctor` field was changed by a human,
and reconstruct the timeline from BigQuery snapshots + Plato's own
created_by / last_edited_by / finalized_by audit fields baked into the
invoice payload.

Plato has no audit-log API, but `raw_plato.invoices_raw` is append-only:
every time an invoice's modified_at ticks, we land a fresh row with the
full payload. Replay the doctor + last_edited_by fields across snapshots
to see who flipped what and when.

Usage:
    export PLATO_API_KEY=$(gcloud secrets versions access latest --secret=plato-api-key)
    python3 investigate_invoice_doctor.py 00048

Resolves Plato patient given_id (e.g. "00048") to the internal patient_id,
then queries BQ for every invoice belonging to that patient and prints a
per-invoice timeline of doctor changes with attribution.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone

import requests

PLATO_BASE = "https://clinic.platomedical.com/api"
BQ_PROJECT = "goji-bi"


def resolve_patient_id(api_key: str, db: str, given_id: str) -> tuple[str, str | None]:
    """Look up Plato patient by given_id (the displayed number like '00048').

    Returns (patient_id, display_name) or exits.
    """
    s = requests.Session()
    s.headers.update({"accept": "application/json", "Authorization": f"Bearer {api_key}"})
    # /search/patient is the lookup-by-given_id endpoint (the list /patient
    # endpoint only filters by patient_id/dob).
    r = s.get(f"{PLATO_BASE}/{db}/search/patient", params={"given_id": given_id}, timeout=30)
    r.raise_for_status()
    body = r.json()
    rows = body if isinstance(body, list) else body.get("patients") or body.get("data") or body.get("results") or []
    matches = [p for p in rows if str(p.get("given_id", "")).strip() == given_id]
    if not matches:
        sys.exit(f"no patient with given_id={given_id!r}. raw response keys: {list(body) if isinstance(body, dict) else type(body).__name__}")
    if len(matches) > 1:
        print(f"WARN: {len(matches)} patients matched given_id={given_id!r}; using first", file=sys.stderr)
    p = matches[0]
    pid = p.get("_id") or p.get("id")
    name = p.get("name") or p.get("patient_name")
    return pid, name


def fetch_invoice_timeline(patient_id: str) -> list[dict]:
    """Return every snapshot row for the patient's invoices, ordered by
    invoice_id then _loaded_at. Shells out to `bq` to reuse the user's
    gcloud auth (avoids ADC setup)."""
    sql = f"""
    SELECT
      invoice_id,
      FORMAT_TIMESTAMP('%Y-%m-%d %H:%M:%S', _loaded_at) AS _loaded_at,
      FORMAT_TIMESTAMP('%Y-%m-%d %H:%M:%S', _source_modified_at) AS _source_modified_at,
      JSON_VALUE(payload, '$.doctor')          AS doctor,
      JSON_VALUE(payload, '$.invoice_prefix')  AS invoice_prefix,
      SAFE_CAST(JSON_VALUE(payload, '$.invoice') AS INT64) AS invoice_no,
      SAFE_CAST(JSON_VALUE(payload, '$.total')   AS NUMERIC) AS total,
      JSON_VALUE(payload, '$.created_by')      AS created_by,
      JSON_VALUE(payload, '$.created_on')      AS created_on,
      JSON_VALUE(payload, '$.last_edited_by')  AS last_edited_by,
      JSON_VALUE(payload, '$.last_edited')     AS last_edited,
      JSON_VALUE(payload, '$.finalized_by')    AS finalized_by,
      JSON_VALUE(payload, '$.finalized_on')    AS finalized_on,
      JSON_VALUE(payload, '$.void_by')         AS void_by,
      JSON_VALUE(payload, '$.void_on')         AS void_on,
      SAFE_CAST(JSON_VALUE(payload, '$.finalized') AS INT64) = 1 AS is_finalized,
      SAFE_CAST(JSON_VALUE(payload, '$.void')      AS INT64) = 1 AS is_void
    FROM `goji-bi.raw_plato.invoices_raw`
    WHERE JSON_VALUE(payload, '$.patient_id') = '{patient_id}'
    ORDER BY invoice_id, _loaded_at
    """
    out = subprocess.run(
        ["bq", "query", "--use_legacy_sql=false", "--format=json",
         "--max_rows=100000", sql],
        capture_output=True, text=True, check=False,
    )
    if out.returncode != 0:
        sys.exit(f"bq query failed:\n{out.stderr}")
    return json.loads(out.stdout or "[]")


def print_timeline(patient_id: str, name: str | None, rows: list[dict]) -> None:
    print(f"\nPatient: {name or '(unknown)'}  patient_id={patient_id}")
    print(f"Snapshots: {len(rows)} rows across {len({r['invoice_id'] for r in rows})} invoice(s)\n")
    if not rows:
        print("  (no invoices found in raw_plato.invoices_raw)")
        return

    by_inv: dict[str, list[dict]] = {}
    for r in rows:
        by_inv.setdefault(r["invoice_id"], []).append(r)

    for invoice_id, snaps in by_inv.items():
        head = snaps[-1]
        label = f"{head.get('invoice_prefix') or ''}{head.get('invoice_no') or ''}".strip() or "(no invoice number)"
        print(f"=== Invoice {label}  id={invoice_id}  total={head.get('total')} ===")
        # Collapse to transitions: emit a row only when doctor OR last_edited
        # changes vs the previous snapshot.
        prev_doc = object()
        prev_edit = object()
        for s in snaps:
            doc = s.get("doctor")
            edit = s.get("last_edited")
            edit_by = s.get("last_edited_by")
            changed = (doc != prev_doc) or (edit != prev_edit)
            if not changed:
                continue
            marker = " *DOCTOR CHANGE*" if (prev_doc is not object() and doc != prev_doc) else ""
            print(f"  loaded={s['_loaded_at']}  src_mod={s.get('_source_modified_at')}  "
                  f"doctor={doc!r}  last_edited={edit}  by={edit_by!r}"
                  f"  finalized_by={s.get('finalized_by')!r}{marker}")
            prev_doc = doc
            prev_edit = edit
        # Provenance summary
        print(f"  --> created_by={head.get('created_by')!r} on {head.get('created_on')}")
        print(f"  --> finalized_by={head.get('finalized_by')!r} on {head.get('finalized_on')}  finalized={head.get('is_finalized')}  void={head.get('is_void')}")
        print()


def main() -> int:
    if len(sys.argv) != 2:
        sys.exit("usage: investigate_invoice_doctor.py <patient_given_id>  (e.g. 00048)")
    given_id = sys.argv[1].strip()
    api_key = os.environ.get("PLATO_API_KEY")
    if not api_key:
        sys.exit("set PLATO_API_KEY (e.g. gcloud secrets versions access latest --secret=plato-api-key)")
    db = os.environ.get("PLATO_DB", "gojihealth")

    patient_id, name = resolve_patient_id(api_key, db, given_id)
    rows = fetch_invoice_timeline(patient_id)
    print_timeline(patient_id, name, rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
