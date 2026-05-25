#!/usr/bin/env python3
"""
Cloud Run Job: ingest Plato /invoice into raw_plato.invoices_raw.

Pulls every invoice with modified_at within the last LOOKBACK_DAYS via Plato's
modified_since filter, stamps each with _loaded_at, and appends to BigQuery
using a single load job (free tier). Dedupe to "latest version per invoice_id"
happens in stg.invoices, so this stays append-only and idempotent.

Env vars:
  PLATO_DB         Plato database name              default: gojihealth
  PLATO_API_KEY    Plato bearer token               (required, from Secret Manager)
  LOOKBACK_DAYS    How many days back to scan       default: 7
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
        # Plato resets every 60s; if we're nearly out, wait a full window.
        time.sleep(60 if (rem and rem.isdigit() and int(rem) < 2) else PER_PAGE_SLEEP_S)
        page += 1


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
    bq_project = env("BQ_PROJECT", "goji-bi", required=False)
    bq_dataset = env("BQ_DATASET", "raw_plato", required=False)
    bq_table = env("BQ_TABLE", "invoices_raw", required=False)

    table_ref = f"{bq_project}.{bq_dataset}.{bq_table}"
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    modified_since = cutoff.strftime("%Y-%m-%d %H:%M:%S")
    loaded_at_iso = datetime.now(timezone.utc).isoformat()

    log.info(
        f"plato_db={plato_db} lookback_days={lookback_days} "
        f"modified_since={modified_since} target={table_ref}"
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
        for inv in paged_get(
            session,
            f"{PLATO_BASE}/{plato_db}/invoice",
            {"modified_since": modified_since},
        ):
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
