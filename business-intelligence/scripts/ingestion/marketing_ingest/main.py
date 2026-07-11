#!/usr/bin/env python3
"""
Cloud Run Job: ingest marketing-channel metrics into raw_marketing.*.

One consolidated job for the marketing-integration track (the Marketing-tab
"pending integration" seams). Today it pulls **Instagram reach**; GBP
clicks/calls and Google-review velocity are the next sources and slot in as
sibling handlers writing sibling raw_marketing tables — a single image /
scheduler / deploy gate for the whole track (deliberately NOT folded into the
plato_* jobs: different domain and failure mode).

Which sources run is controlled by SOURCES (comma-separated); each handler
buffers rows then does a single load_table_from_json(..., WRITE_APPEND), same
free-tier pattern as the plato_* jobs. Dedupe to "latest per key" happens in
stg, never here.

### Instagram reach — why a period-level pull, not daily
Reach counts *unique accounts reached*, so it is NOT additive: monthly reach is
not the sum of daily reach (a person reached on Mon and Tue counts once a month,
twice a day). We therefore pull Meta's rolling 28-day de-duplicated reach
(`period=days_28`) once per run and store one row per reading. Downstream
(marts.fct_instagram_reach + the dashboard) reads the latest reading in-window,
it does not sum. See ingestion/AGENTS.md.

Env vars:
  SOURCES              Comma list of sources to run     default: instagram
  IG_USER_ID           Instagram Business/Creator id     (required for instagram)
  META_GRAPH_TOKEN     Long-lived Meta access token      (required for instagram; secret)
  GRAPH_API_VERSION    Graph API version                 default: v21.0
  IG_METRIC_PERIOD     Reach aggregation period          default: days_28
  BQ_PROJECT           Target BQ project                 default: goji-bi
  BQ_DATASET           Target dataset                    default: raw_marketing

Exit codes: 0 on success, 1 on config error, 2 on BQ failure, 3 on API failure.
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone

import requests
from google.cloud import bigquery

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("marketing-ingest")

GRAPH_BASE = "https://graph.facebook.com"
TIMEOUT_S = 30


def env(name: str, default: str | None = None, required: bool = True) -> str:
    v = os.environ.get(name, default)
    if required and not v:
        log.error(f"missing env var: {name}")
        sys.exit(1)
    return v  # type: ignore[return-value]


def _bq_load(rows: list[dict], table_ref: str, schema: list[bigquery.SchemaField],
             project: str) -> None:
    """Single append-only load job (free tier), same shape as the plato_* jobs."""
    if not rows:
        log.info("no rows for %s; nothing to load", table_ref)
        return
    log.info("loading %d rows into %s", len(rows), table_ref)
    bq = bigquery.Client(project=project)
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        schema=schema,
    )
    try:
        job = bq.load_table_from_json(rows, table_ref, job_config=job_config)
        job.result()  # blocks; raises on failure
    except Exception as e:
        log.exception("bq load failed: %s", e)
        sys.exit(2)
    log.info("done: inserted %d rows into %s", job.output_rows, table_ref)


def parse_reach(body: dict) -> tuple[str, int]:
    """Extract (metric_date, value) from a Meta insights response. Pure, so it's
    unit-tested without a network call — the response shape is the failure-prone
    part. Takes the LAST datapoint (the most recent reading in the series).

    Shape: {"data":[{"name":"reach","values":[{"value":1234,
             "end_time":"2026-07-11T07:00:00+0000"}, ...]}]}
    Raises (KeyError/IndexError/ValueError/TypeError) on any unexpected shape,
    which the caller turns into exit code 3.
    """
    latest = body["data"][0]["values"][-1]
    return latest["end_time"][:10], int(latest["value"])


def ingest_instagram(project: str, dataset: str) -> None:
    """Pull rolling 28-day Instagram reach and append one row to
    raw_marketing.instagram_raw. Generic (metric, metric_date, value, payload)
    shape so followers / profile-views / etc. later become more rows, not a
    schema change (ingestion/AGENTS.md)."""
    ig_user_id = env("IG_USER_ID")
    token = env("META_GRAPH_TOKEN")
    version = env("GRAPH_API_VERSION", "v21.0", required=False)
    period = env("IG_METRIC_PERIOD", "days_28", required=False)
    loaded_at = datetime.now(timezone.utc).isoformat()

    url = f"{GRAPH_BASE}/{version}/{ig_user_id}/insights"
    params = {"metric": "reach", "period": period, "access_token": token}
    log.info("fetching IG reach: user=%s version=%s period=%s", ig_user_id, version, period)
    try:
        r = requests.get(url, params=params, timeout=TIMEOUT_S)
        r.raise_for_status()
        body = r.json()
    except requests.RequestException as e:
        # Don't log the response body — it can echo the access token back.
        log.exception("meta graph fetch failed: %s", e)
        sys.exit(3)

    try:
        metric_date, value = parse_reach(body)
    except (KeyError, IndexError, ValueError, TypeError) as e:
        log.error("unexpected insights payload (%s): %s", e, body.get("data") if isinstance(body, dict) else body)
        sys.exit(3)

    rows = [{
        "_loaded_at": loaded_at,
        "metric": f"reach_{period}",
        "metric_date": metric_date,
        "value": value,
        "payload": body["data"][0]["values"][-1],
    }]
    schema = [
        bigquery.SchemaField("_loaded_at", "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("metric", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("metric_date", "DATE", mode="REQUIRED"),
        bigquery.SchemaField("value", "INT64", mode="REQUIRED"),
        bigquery.SchemaField("payload", "JSON"),
    ]
    _bq_load(rows, f"{project}.{dataset}.instagram_raw", schema, project)


# source name -> handler(project, dataset). Add "gbp"/"reviews" here next.
SOURCES = {
    "instagram": ingest_instagram,
}


def main() -> None:
    project = env("BQ_PROJECT", "goji-bi", required=False)
    dataset = env("BQ_DATASET", "raw_marketing", required=False)
    requested = [s.strip() for s in env("SOURCES", "instagram", required=False).split(",") if s.strip()]

    unknown = [s for s in requested if s not in SOURCES]
    if unknown:
        log.error("unknown source(s): %s (known: %s)", unknown, list(SOURCES))
        sys.exit(1)

    for name in requested:
        log.info("=== source: %s ===", name)
        SOURCES[name](project, dataset)


if __name__ == "__main__":
    main()
