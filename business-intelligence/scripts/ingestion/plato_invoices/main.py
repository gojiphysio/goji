#!/usr/bin/env python3
"""
Cloud Run Job: ingest Plato /invoice into raw_plato.invoices_raw.

Pages Plato's invoice list, stamps each row with _loaded_at, and appends to
BigQuery using a single load job (free tier). Dedupe to "latest version per
invoice_id" happens in stg.invoices, so this stays append-only and idempotent.

Plato ignores the modified_since filter on /invoice (verified 2026-10-27: a
2-day window returned all 1,149 invoices), but it does return invoices newest
first. So daytime runs stop once a full page is older than RECENT_DAYS by
invoice date (~1-2 pages instead of ~58), and a nightly run with RECENT_DAYS=0
sweeps everything to pick up payments on older invoices.

Env vars:
  PLATO_DB         Plato database name              default: gojihealth
  PLATO_API_KEY    Plato bearer token               (required, from Secret Manager)
  LOOKBACK_DAYS    modified_since sent to Plato     default: 7 (ignored by Plato)
  RECENT_DAYS      Stop after invoices this old     default: 14 (0 = full sweep)
  BQ_PROJECT       Target BQ project                default: goji-bi
  BQ_DATASET       Target dataset                   default: raw_plato
  BQ_TABLE         Target table                     default: invoices_raw

Exit codes: 0 on success, 1 on config error, 2 on BQ failure, 3 on Plato failure.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Iterator

import requests
from google.cloud import bigquery

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("plato-invoices-ingest")

PLATO_BASE = "https://clinic.platomedical.com/api"
PER_PAGE_SLEEP_S = 3
# The key's 20 req/min is shared with the website booking form. Once Plato
# reports this many or fewer left, wait for the window to reset rather than
# take them, so a patient picking a date always has budget.
PLATO_HEADROOM = 10
TIMEOUT_S = 30


def env(name: str, default: str | None = None, required: bool = True) -> str:
    v = os.environ.get(name, default)
    if required and not v:
        log.error(f"missing env var: {name}")
        sys.exit(1)
    return v  # type: ignore[return-value]


def paged_get(session: requests.Session, url: str,
              params: dict | None = None) -> Iterator[dict]:
    """Yield rows from a paginated Plato endpoint using current_page."""
    page = 1
    params = dict(params or {})
    while True:
        params["current_page"] = page
        r = session.get(url, params=params, timeout=TIMEOUT_S)
        if r.status_code == 429:
            log.warning("plato rate limited (429), sleeping 60s")
            time.sleep(60)
            continue
        if r.status_code >= 500:
            log.warning(f"plato {r.status_code}, sleeping 10s and retrying page {page}")
            time.sleep(10)
            continue
        r.raise_for_status()
        batch = r.json()
        if not isinstance(batch, list) or not batch:
            return
        yield from batch
        rem = r.headers.get("x-ratelimit-remaining")
        # Plato resets every 60s; leave PLATO_HEADROOM for the booking form.
        time.sleep(60 if (rem and rem.isdigit() and int(rem) <= PLATO_HEADROOM)
                   else PER_PAGE_SLEEP_S)
        page += 1


def recent_only(invoices: Iterator[dict], cutoff_date: str | None,
                page_size: int = 20) -> Iterator[dict]:
    """Pass invoices through until a full page in a row is dated before
    cutoff_date (YYYY-MM-DD), then stop so no further pages are requested.
    Plato lists invoices newest first; rows without a date never count as old.
    cutoff_date=None passes everything (full sweep)."""
    older = 0
    for inv in invoices:
        yield inv
        if not cutoff_date:
            continue
        day = (inv.get("date") or "")[:10]
        if day and day < cutoff_date:
            older += 1
            if older >= page_size:
                return
        else:
            older = 0


def to_iso_utc(value: str | None) -> str | None:
    """Plato timestamps come as 'YYYY-MM-DD HH:MM:SS' (assumed UTC).
    Return an ISO 8601 UTC string for BQ TIMESTAMP, or None on failure."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace(" ", "T"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError):
        return None


def main() -> None:
    plato_db = env("PLATO_DB", "gojihealth", required=False)
    plato_key = env("PLATO_API_KEY")
    lookback_days = int(env("LOOKBACK_DAYS", "7", required=False))
    recent_days = int(env("RECENT_DAYS", "14", required=False))
    bq_project = env("BQ_PROJECT", "goji-bi", required=False)
    bq_dataset = env("BQ_DATASET", "raw_plato", required=False)
    bq_table = env("BQ_TABLE", "invoices_raw", required=False)

    table_ref = f"{bq_project}.{bq_dataset}.{bq_table}"
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    modified_since = cutoff.strftime("%Y-%m-%d %H:%M:%S")
    recent_cutoff = ((datetime.now(timezone.utc) - timedelta(days=recent_days))
                     .strftime("%Y-%m-%d") if recent_days > 0 else None)
    loaded_at_iso = datetime.now(timezone.utc).isoformat()

    log.info(
        f"plato_db={plato_db} lookback_days={lookback_days} "
        f"modified_since={modified_since} recent_cutoff={recent_cutoff or 'full sweep'} "
        f"target={table_ref}"
    )

    session = requests.Session()
    session.headers.update({
        "accept": "application/json",
        "Authorization": f"Bearer {plato_key}",
    })

    # Buffer all rows in memory then do a single BQ load job (free vs streaming).
    # Goji's invoice volume is tiny so this never threatens Cloud Run memory.
    rows: list[dict] = []
    seen_ids: set[str] = set()
    try:
        for inv in recent_only(paged_get(
            session,
            f"{PLATO_BASE}/{plato_db}/invoice",
            {"modified_since": modified_since},
        ), recent_cutoff):
            # Plato returns the invoice id as `_id` (Mongo-style). Fall back to
            # `id` defensively in case a future API rev renames it.
            invoice_id = str(inv.get("_id") or inv.get("id") or "").strip()
            if not invoice_id:
                continue
            # If Plato pages return the same invoice twice in one run, keep only
            # the last sighting (it's the freshest within this run).
            if invoice_id in seen_ids:
                rows = [r for r in rows if r["invoice_id"] != invoice_id]
            seen_ids.add(invoice_id)
            rows.append({
                "_loaded_at": loaded_at_iso,
                "_source_modified_at": to_iso_utc(inv.get("modified_at")),
                "invoice_id": invoice_id,
                "invoice_date": (inv.get("date") or "")[:10] or None,
                # Pass the dict directly. load_table_from_json serialises the
                # whole row to NDJSON, and BigQuery's JSON column type expects a
                # JSON value (object), NOT a JSON-encoded string. Passing a
                # string lands a "string"-typed JSON value that JSON_VALUE and
                # JSON_QUERY_ARRAY cannot traverse into.
                "payload": inv,
            })
    except requests.RequestException as e:
        log.exception(f"plato fetch failed: {e}")
        sys.exit(3)

    if not rows:
        log.info("no invoices to load. exiting clean.")
        return

    log.info(f"loading {len(rows)} invoice rows into {table_ref}")
    bq = bigquery.Client(project=bq_project)
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        schema=[
            bigquery.SchemaField("_loaded_at", "TIMESTAMP", mode="REQUIRED"),
            bigquery.SchemaField("_source_modified_at", "TIMESTAMP"),
            bigquery.SchemaField("invoice_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("invoice_date", "DATE"),
            bigquery.SchemaField("payload", "JSON", mode="REQUIRED"),
        ],
    )
    try:
        load_job = bq.load_table_from_json(rows, table_ref, job_config=job_config)
        load_job.result()  # blocks until done; raises on failure
    except Exception as e:
        log.exception(f"bq load failed: {e}")
        sys.exit(2)

    log.info(f"done: inserted {load_job.output_rows} rows into {table_ref}")


if __name__ == "__main__":
    main()
