#!/usr/bin/env python3
"""
Cloud Run Job: ingest Plato /patient into marts.dim_patient.

PII boundary: this job is the ONLY code in the BI stack that ever sees a full
patient name. We pull each patient record, derive `initial_lastname` (e.g.
"C. Wong") in memory, and write ONLY that derived scalar to BigQuery. The
raw name, DOB, contact info, etc. are discarded before the BQ load job runs.

If a patient's name in Plato is "Charles Wong" -> we store "C. Wong".
If it's a single token "Madonna"            -> we store "Madonna".
If it's empty / missing                      -> we store NULL.

This is intentionally a flat dimension table, not a raw+stg+dim layer, so the
derivation is a single Python function (see `initial_lastname`) rather than a
SQL view that could be edited to surface more PII later.

Env vars:
  PLATO_DB         Plato database name              default: gojihealth
  PLATO_API_KEY    Plato bearer token               (required, from Secret Manager)
  BQ_PROJECT       Target BQ project                default: goji-bi
  BQ_DATASET       Target dataset                   default: marts
  BQ_TABLE         Target table                     default: dim_patient

Exit codes: 0 on success, 1 on config error, 2 on BQ failure, 3 on Plato failure.
"""
from __future__ import annotations

import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Iterator

import requests
from google.cloud import bigquery

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("plato-patients-ingest")

PLATO_BASE = "https://clinic.platomedical.com/api"
PER_PAGE_SLEEP_S = 3
TIMEOUT_S = 30


def env(name: str, default: str | None = None, required: bool = True) -> str:
    v = os.environ.get(name, default)
    if required and not v:
        log.error(f"missing env var: {name}")
        sys.exit(1)
    return v  # type: ignore[return-value]


def initial_lastname(raw_name: str | None) -> str | None:
    """Derive a PII-safe display label: "C. Wong" from "Charles Wong".

    Rules:
      - None / empty / whitespace-only -> None
      - One token ("Madonna")          -> the token itself, unchanged
      - Two or more tokens             -> first char of first token + ". " + last token

    This is intentionally simple and Western-name-shaped; Singapore Chinese
    names where the surname appears first will yield e.g. "W. Hwa" for "Wong
    Chee Hwa". That's acceptable as a first iteration — operators can spot the
    pattern and we can refine the rule (or add a manual override column) once
    we see real data.
    """
    if not raw_name:
        return None
    cleaned = raw_name.strip()
    if not cleaned:
        return None
    tokens = cleaned.split()
    if len(tokens) == 1:
        return tokens[0]
    first = tokens[0][0].upper()
    last  = tokens[-1]
    return f"{first}. {last}"


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


def main() -> None:
    plato_db = env("PLATO_DB", "gojihealth", required=False)
    plato_key = env("PLATO_API_KEY")
    bq_project = env("BQ_PROJECT", "goji-bi", required=False)
    bq_dataset = env("BQ_DATASET", "marts", required=False)
    bq_table = env("BQ_TABLE", "dim_patient", required=False)

    table_ref = f"{bq_project}.{bq_dataset}.{bq_table}"
    updated_at_iso = datetime.now(timezone.utc).isoformat()

    log.info(f"plato_db={plato_db} target={table_ref}")

    session = requests.Session()
    session.headers.update({
        "accept": "application/json",
        "Authorization": f"Bearer {plato_key}",
    })

    # We buffer the derived rows in memory and write the table in one shot
    # with WRITE_TRUNCATE. This is a dimension, not an event stream; the
    # latest snapshot fully supersedes the previous one. Goji's patient
    # count (~thousands) fits comfortably in memory.
    rows: list[dict] = []
    seen_ids: set[str] = set()
    skipped_no_id = 0

    try:
        for p in paged_get(
            session,
            f"{PLATO_BASE}/{plato_db}/patient",
        ):
            patient_id = str(p.get("_id") or p.get("id") or "").strip()
            if not patient_id:
                skipped_no_id += 1
                continue
            if patient_id in seen_ids:
                # Plato sometimes returns the same row across pages near
                # boundaries — keep the first sighting and skip.
                continue
            seen_ids.add(patient_id)

            # Plato may expose the name as a plain string, or as a dict with
            # first/last fields. Handle both. NB: regardless of shape, only
            # the *derived* initial_lastname leaves this scope.
            name_field = p.get("name")
            if isinstance(name_field, dict):
                first = name_field.get("first") or ""
                last  = name_field.get("last") or ""
                raw_name = f"{first} {last}".strip()
            elif isinstance(name_field, str):
                raw_name = name_field
            else:
                raw_name = ""

            label = initial_lastname(raw_name)

            rows.append({
                "patient_id":       patient_id,
                "initial_lastname": label,
                "_updated_at":      updated_at_iso,
            })
            # Belt-and-braces: blow away the raw name reference as soon as
            # we've derived from it. (Python GC would get it anyway once the
            # loop iterates, but this makes the lifetime explicit.)
            del raw_name, name_field

    except requests.RequestException as e:
        log.exception(f"plato fetch failed: {e}")
        sys.exit(3)

    if not rows:
        log.info("no patient rows produced. exiting clean.")
        return

    log.info(f"loading {len(rows)} patient rows into {table_ref} "
             f"(skipped {skipped_no_id} without ids)")
    bq = bigquery.Client(project=bq_project)
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        schema=[
            bigquery.SchemaField("patient_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("initial_lastname", "STRING"),
            bigquery.SchemaField("_updated_at", "TIMESTAMP", mode="REQUIRED"),
        ],
    )
    try:
        load_job = bq.load_table_from_json(rows, table_ref, job_config=job_config)
        load_job.result()
    except Exception as e:
        log.exception(f"bq load failed: {e}")
        sys.exit(2)

    log.info(f"done: wrote {load_job.output_rows} rows to {table_ref}")


if __name__ == "__main__":
    main()
