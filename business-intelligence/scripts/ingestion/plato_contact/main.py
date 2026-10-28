#!/usr/bin/env python3
"""
Cloud Run Job: ingest Plato /contact into marts.dim_referral_source.

Plato's /contact endpoint is a small registry of external referral channels
(GPs, specialist clinics, gyms, "Walk-in", online-booking sources). Patient
records reference these via the `referred_by` field — that field holds a
contact `_id`, NOT a patient_id. This job pulls the contact list and writes
a PII-safe shape: organisation name, named person at the channel, category,
plus a derived source_type bucket the dashboard groups on.

Discarded at ingest: email, phone, address, fax, url, notes. These are
professional contact details for partner clinics — useful inside Plato but
unused (and risk-increasing) in BI. Keep this list tight.

Env vars:
  PLATO_DB         Plato database name              default: gojihealth
  PLATO_API_KEY    Plato bearer token               (required, from Secret Manager)
  BQ_PROJECT       Target BQ project                default: goji-bi
  BQ_DATASET       Target dataset                   default: marts
  BQ_TABLE         Target table                     default: dim_referral_source

Exit codes: 0 success, 1 config error, 2 BQ failure, 3 Plato failure.
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
log = logging.getLogger("plato-contact-ingest")

PLATO_BASE = "https://clinic.platomedical.com/api"
PER_PAGE_SLEEP_S = 3
# The key's 20 req/min is shared with the website booking form. Once Plato
# reports this many or fewer left, wait for the window to reset rather than
# take them, so a patient picking a date always has budget.
PLATO_HEADROOM = 10
TIMEOUT_S = 30

# Buckets we surface on the dashboard's monthly-acquisition chart. Order
# matters: classify_source_type checks rules top to bottom and returns the
# first match.
SOURCE_TYPE_MEDICAL       = "medical"
SOURCE_TYPE_PARTNER       = "partner"
SOURCE_TYPE_WALK_IN       = "walk_in"
SOURCE_TYPE_ONLINE        = "online"
SOURCE_TYPE_WORD_OF_MOUTH = "word_of_mouth"
SOURCE_TYPE_OTHER         = "other"

# Category keywords that imply "medical referrer" regardless of name. Plato's
# `category` field is free-text, so we match on substrings.
MEDICAL_CATEGORY_TOKENS = (
    "gp", "obgyn", "spine", "ortho", "paediatr", "lactation",
    "physician", "specialist", "surgery", "clinic",
)


def env(name: str, default: str | None = None, required: bool = True) -> str:
    v = os.environ.get(name, default)
    if required and not v:
        log.error(f"missing env var: {name}")
        sys.exit(1)
    return v  # type: ignore[return-value]


def classify_source_type(name: str, person: str, category: str) -> str:
    """Bucket a contact into one of six source_type values.

    Rules, top to bottom:
      1. category contains a medical keyword           -> medical
      2. name is "Walk-in" (case-insensitive)          -> walk_in
      3. person looks like an online-booking marker    -> online
      4. name == "Goji Physio" with a personal `person`-> word_of_mouth
         (in-house clinician referral via patient network)
      5. otherwise — if name looks like a clinic/named org -> partner
      6. fallback                                       -> other

    The rules are derived from the actual 19-row contact list in Plato as of
    seed time. If new contact patterns show up the function is the place to
    extend — not the dashboard SQL.
    """
    n = (name or "").strip()
    p = (person or "").strip()
    c = (category or "").strip().lower()
    n_lower = n.lower()
    p_lower = p.lower()

    if c and any(tok in c for tok in MEDICAL_CATEGORY_TOKENS):
        return SOURCE_TYPE_MEDICAL
    # Doctors are medical referrers even when Plato's category column was left
    # blank. We treat "Dr X" / "Dr. X" / "DR " as the marker.
    if p_lower.startswith("dr ") or p_lower.startswith("dr."):
        return SOURCE_TYPE_MEDICAL
    if n_lower == "walk-in":
        return SOURCE_TYPE_WALK_IN
    if "online booking" in p_lower:
        return SOURCE_TYPE_ONLINE
    if n_lower == "goji physio":
        # In-house clinician network: "Goji Physio" + a personal name
        # (Claire/Cheryl/Kristy) means this patient came via that clinician's
        # personal/word-of-mouth referral channel.
        return SOURCE_TYPE_WORD_OF_MOUTH
    if n:
        # Named external organisation without a medical category we recognised
        # — treat as a partner (gyms, allied-health, friend-of-clinic).
        return SOURCE_TYPE_PARTNER
    return SOURCE_TYPE_OTHER


def display_label(name: str, person: str, source_type: str) -> str:
    """Return a short label for dashboard tables.

    - For online sources, the `person` field carries the channel name
      ("Online Booking - Instagram"), so we display that.
    - For everything else, prefer the organisation `name` ("UFIT", "Trinity
      Women's", "Walk-in"). Append the person in parens when both exist and
      they're not redundant.
    """
    n = (name or "").strip()
    p = (person or "").strip()
    if source_type == SOURCE_TYPE_ONLINE and p:
        # "Online Booking - Instagram" -> "Online: Instagram"
        return p.replace("Online Booking - ", "Online: ") if "Online Booking - " in p else p
    if source_type == SOURCE_TYPE_WORD_OF_MOUTH and p:
        return f"Word-of-mouth ({p})"
    if n and p and p.lower() not in n.lower():
        return f"{n} ({p})"
    return n or p or "(unnamed)"


def created_on_date(created_on_str: object) -> str | None:
    """Extract the date portion of Plato's `created_on` ("YYYY-MM-DD HH:MM:SS")."""
    if not isinstance(created_on_str, str) or len(created_on_str) < 10:
        return None
    head = created_on_str[:10]
    try:
        date.fromisoformat(head)
    except ValueError:
        return None
    return head


def paged_get(session: requests.Session, url: str,
              params: dict | None = None) -> Iterator[dict]:
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


def main() -> None:
    plato_db   = env("PLATO_DB",   "gojihealth",         required=False)
    plato_key  = env("PLATO_API_KEY")
    bq_project = env("BQ_PROJECT", "goji-bi",            required=False)
    bq_dataset = env("BQ_DATASET", "marts",              required=False)
    bq_table   = env("BQ_TABLE",   "dim_referral_source", required=False)

    table_ref = f"{bq_project}.{bq_dataset}.{bq_table}"
    updated_at_iso = datetime.now(timezone.utc).isoformat()

    log.info(f"plato_db={plato_db} target={table_ref}")

    session = requests.Session()
    session.headers.update({
        "accept": "application/json",
        "Authorization": f"Bearer {plato_key}",
    })

    rows: list[dict] = []
    seen_ids: set[str] = set()
    skipped_no_id = 0

    try:
        for c in paged_get(session, f"{PLATO_BASE}/{plato_db}/contact"):
            contact_id = str(c.get("_id") or "").strip()
            if not contact_id:
                skipped_no_id += 1
                continue
            if contact_id in seen_ids:
                continue
            seen_ids.add(contact_id)

            name     = (c.get("name") or "").strip()
            person   = (c.get("person") or "").strip()
            category = (c.get("category") or "").strip()

            source_type = classify_source_type(name, person, category)
            label       = display_label(name, person, source_type)
            created_on  = created_on_date(c.get("created_on"))

            rows.append({
                "contact_id":    contact_id,
                "name":          name or None,
                "person":        person or None,
                "category":      category or None,
                "source_type":   source_type,
                "display_label": label,
                "created_on":    created_on,
                "_updated_at":   updated_at_iso,
            })
            # Explicit lifetime for raw payload reference: GC the original
            # contact dict (with email/phone/address/notes) before the next
            # iteration. The values we kept have already been copied above.
            del c

    except requests.RequestException as e:
        log.exception(f"plato fetch failed: {e}")
        sys.exit(3)

    if not rows:
        log.info("no contact rows produced. exiting clean.")
        return

    log.info(f"loading {len(rows)} contact rows into {table_ref} "
             f"(skipped {skipped_no_id} without ids)")
    bq = bigquery.Client(project=bq_project)
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        schema=[
            bigquery.SchemaField("contact_id",    "STRING",    mode="REQUIRED"),
            bigquery.SchemaField("name",          "STRING"),
            bigquery.SchemaField("person",        "STRING"),
            bigquery.SchemaField("category",      "STRING"),
            bigquery.SchemaField("source_type",   "STRING"),
            bigquery.SchemaField("display_label", "STRING"),
            bigquery.SchemaField("created_on",    "DATE"),
            bigquery.SchemaField("_updated_at",   "TIMESTAMP", mode="REQUIRED"),
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
