#!/usr/bin/env python3
"""
Cloud Run Job: ingest Plato /appointment into raw_plato.appointments_raw.

Pulls every appointment with starttime ∈ [today - PAST_DAYS, today + FUTURE_DAYS]
via Plato's `start_date`/`end_date` filters, stamps each with _loaded_at, and
appends to BigQuery using a single load job (free tier). Dedupe to "latest
version per appointment_id" happens in stg.appointments, so this stays
append-only and idempotent.

Why we don't use `modified_since` here (unlike plato_invoices, which does):

  The dashboard's invoice-doctor mismatch alert needs to know "who was the
  patient's appointment doctor on the invoice's date." If an appointment for
  yesterday was scheduled four weeks ago and never edited, its `last_edited`
  is four weeks old — so `modified_since=last_15min` wouldn't return it. The
  data point we care about is the appointment's session DATE (`starttime`),
  not when it was last touched. So we scan by `start_date`/`end_date` instead.

  Trade-off: each run re-fetches the same ~140 rows for the recent past
  window. This is fine — the data volume is tiny (~7 pages, ~25s wall time),
  and `stg.appointments` dedupes by latest `_loaded_at`.

Env vars:
  PLATO_DB           Plato database name              default: gojihealth
  PLATO_API_KEY      Plato bearer token               (required, from Secret Manager)
  PAST_DAYS          Days of past sessions to scan    default: 14
  FUTURE_DAYS        Days of future sessions to scan  default: 31
  BQ_PROJECT         Target BQ project                default: goji-bi
  BQ_DATASET         Target dataset                   default: raw_plato
  BQ_TABLE           Target table                     default: appointments_raw

Exit codes: 0 on success, 1 on config error, 2 on BQ failure, 3 on Plato failure.
"""
from __future__ import annotations

import logging
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from typing import Iterator

import requests
from google.cloud import bigquery

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("plato-appointments-ingest")

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
    past_days = int(env("PAST_DAYS", "14", required=False))
    future_days = int(env("FUTURE_DAYS", "31", required=False))
    bq_project = env("BQ_PROJECT", "goji-bi", required=False)
    bq_dataset = env("BQ_DATASET", "raw_plato", required=False)
    bq_table = env("BQ_TABLE", "appointments_raw", required=False)

    table_ref = f"{bq_project}.{bq_dataset}.{bq_table}"
    today = date.today()
    start_date = today - timedelta(days=past_days)
    end_date = today + timedelta(days=future_days)
    loaded_at_iso = datetime.now(timezone.utc).isoformat()

    log.info(
        f"plato_db={plato_db} window={start_date}..{end_date} "
        f"(past={past_days}d, future={future_days}d) target={table_ref}"
    )

    session = requests.Session()
    session.headers.update({
        "accept": "application/json",
        "Authorization": f"Bearer {plato_key}",
    })

    rows: list[dict] = []
    seen_ids: set[str] = set()
    try:
        for appt in paged_get(
            session,
            f"{PLATO_BASE}/{plato_db}/appointment",
            {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
        ):
            appt_id = str(appt.get("_id") or appt.get("id") or "").strip()
            if not appt_id:
                continue
            # If Plato pages return the same appointment twice in one run, keep
            # only the last sighting (it's the freshest within this run).
            if appt_id in seen_ids:
                rows = [r for r in rows if r["appointment_id"] != appt_id]
            seen_ids.add(appt_id)
            rows.append({
                "_loaded_at": loaded_at_iso,
                "_source_modified_at": to_iso_utc(appt.get("last_edited")),
                "appointment_id": appt_id,
                "appt_date": (appt.get("starttime") or "")[:10] or None,
                # Pass the dict directly. load_table_from_json serialises to
                # NDJSON; BigQuery JSON columns want a JSON value, not a
                # JSON-encoded string.
                "payload": appt,
            })
    except requests.RequestException as e:
        log.exception(f"plato fetch failed: {e}")
        sys.exit(3)

    if not rows:
        log.info("no appointments to load. exiting clean.")
        return

    log.info(f"loading {len(rows)} appointment rows into {table_ref}")
    bq = bigquery.Client(project=bq_project)
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        schema=[
            bigquery.SchemaField("_loaded_at", "TIMESTAMP", mode="REQUIRED"),
            bigquery.SchemaField("_source_modified_at", "TIMESTAMP"),
            bigquery.SchemaField("appointment_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("appt_date", "DATE"),
            bigquery.SchemaField("payload", "JSON", mode="REQUIRED"),
        ],
    )
    try:
        load_job = bq.load_table_from_json(rows, table_ref, job_config=job_config)
        load_job.result()
    except Exception as e:
        log.exception(f"bq load failed: {e}")
        sys.exit(2)

    log.info(f"done: inserted {load_job.output_rows} rows into {table_ref}")


if __name__ == "__main__":
    main()
