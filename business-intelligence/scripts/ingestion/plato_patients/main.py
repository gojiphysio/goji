#!/usr/bin/env python3
"""
Cloud Run Job: ingest Plato /patient into marts.dim_patient.

PII boundary: this job is the ONLY code in the BI stack that ever sees a full
patient name, DOB, or postal code. We pull each patient record, derive
PII-safe scalars in memory (initial_lastname, age_band, postal_sector, ...)
and write ONLY those derived values to BigQuery. Raw name/DOB/contacts are
discarded before the BQ load job runs.

If a patient's name in Plato is "Charles Wong" -> we store "C. Wong".
If their DOB is 1985-04-12                     -> we store age_band "40-49".
If their postal is 788887                      -> we store postal_sector "78".

Each derivation is a single Python function with a unit-testable rule. There
is no SQL view shape that could later expose more PII — the data simply never
arrives in BQ in the first place.

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
from datetime import date, datetime, timezone
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


def age_band(dob_str: str | None, today: date | None = None) -> str | None:
    """Bucket a Plato DOB string into a coarse age band.

    Plato gives ISO-ish "YYYY-MM-DD". We parse it, compute age in whole years
    against `today` (or the real date if not supplied — `today` exists so this
    is unit-testable), and bucket. The raw DOB is never persisted; only the
    bucket label is returned.

    Returns None if the DOB is missing, malformed, or pre-1900 (Plato
    occasionally has placeholder DOBs like "0000-00-00").
    """
    if not dob_str:
        return None
    try:
        y, m, d = (int(x) for x in dob_str.split("-"))
        if y < 1900 or not (1 <= m <= 12) or not (1 <= d <= 31):
            return None
    except (ValueError, AttributeError):
        return None
    today = today or date.today()
    age = today.year - y - ((today.month, today.day) < (m, d))
    if age < 0 or age > 120:
        return None
    if age < 18:  return "Under 18"
    if age < 30:  return "18-29"
    if age < 40:  return "30-39"
    if age < 50:  return "40-49"
    if age < 60:  return "50-59"
    return "60+"


def postal_sector(postal: str | None) -> str | None:
    """Singapore postal sector = first 2 digits of the 6-digit postal code.

    A sector covers thousands of households (e.g. "78" = Yishun/Lentor area),
    so it's a public geographic unit rather than PII. Strip non-digits first
    in case the field has spaces or hyphens.
    """
    if not postal:
        return None
    digits = "".join(c for c in str(postal) if c.isdigit())
    if len(digits) < 2:
        return None
    return digits[:2]


def primary_doctor(doctor_field: object) -> str | None:
    """Return the first entry of Plato's `doctor` array, or None.

    Plato stores this as a list like ["PCL"]. Sometimes it's empty or absent.
    """
    if not isinstance(doctor_field, list) or not doctor_field:
        return None
    first = doctor_field[0]
    return str(first).strip() or None


def tag_list(tag_field: object) -> list[str]:
    """Flatten Plato's `tag` field into a list of tag strings.

    Plato shapes seen in samples:
      - None / missing                     -> []
      - [{"tag": "Musculoskeletal"}, ...]  -> ["Musculoskeletal", ...]
      - ["Musculoskeletal", ...]           -> ["Musculoskeletal", ...]   (defensive)

    Empty/whitespace tags are dropped; ordering is preserved.
    """
    if not isinstance(tag_field, list):
        return []
    out: list[str] = []
    for t in tag_field:
        if isinstance(t, dict):
            val = t.get("tag")
        elif isinstance(t, str):
            val = t
        else:
            val = None
        if val:
            s = str(val).strip()
            if s:
                out.append(s)
    return out


def created_on_date(created_on_str: object) -> str | None:
    """Extract the date portion of Plato's `created_on` ("YYYY-MM-DD HH:MM:SS").

    Returns an ISO date string (the JSON-loadable form BigQuery wants for DATE
    columns), or None if the value is missing/unparseable.
    """
    if not isinstance(created_on_str, str) or len(created_on_str) < 10:
        return None
    head = created_on_str[:10]
    try:
        date.fromisoformat(head)
    except ValueError:
        return None
    return head


def referred_by_id(value: object) -> str | None:
    """Plato stores referred_by as a patient_id string, or empty when absent."""
    if not isinstance(value, str):
        return None
    v = value.strip()
    return v or None


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
    age_ref_date = date.today()

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

            # Derive every other PII-safe attribute in this scope; the raw
            # source fields (dob, postal, doctor array, etc.) are read once
            # and never persisted or logged.
            row_age_band      = age_band(p.get("dob"), today=age_ref_date)
            row_sex           = (p.get("sex") or "").strip() or None
            row_postal_sector = postal_sector(p.get("postal"))
            row_tags          = tag_list(p.get("tag"))
            row_primary_doc   = primary_doctor(p.get("doctor"))
            row_created_on    = created_on_date(p.get("created_on"))
            row_referred_by   = referred_by_id(p.get("referred_by"))

            rows.append({
                "patient_id":       patient_id,
                "initial_lastname": label,
                "age_band":         row_age_band,
                "sex":              row_sex,
                "postal_sector":    row_postal_sector,
                "tags":             row_tags,
                "primary_doctor":   row_primary_doc,
                "created_on":       row_created_on,
                "referred_by":      row_referred_by,
                "_updated_at":      updated_at_iso,
            })
            # Belt-and-braces: blow away the raw source references as soon as
            # we've derived from them. Python GC would get them anyway once
            # the loop iterates, but this makes the lifetime explicit and
            # makes a future reviewer think twice before re-using `p` below.
            del raw_name, name_field, p

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
            bigquery.SchemaField("patient_id",       "STRING", mode="REQUIRED"),
            bigquery.SchemaField("initial_lastname", "STRING"),
            bigquery.SchemaField("age_band",         "STRING"),
            bigquery.SchemaField("sex",              "STRING"),
            bigquery.SchemaField("postal_sector",    "STRING"),
            bigquery.SchemaField("tags",             "STRING", mode="REPEATED"),
            bigquery.SchemaField("primary_doctor",   "STRING"),
            bigquery.SchemaField("created_on",       "DATE"),
            bigquery.SchemaField("referred_by",      "STRING"),
            bigquery.SchemaField("_updated_at",      "TIMESTAMP", mode="REQUIRED"),
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
