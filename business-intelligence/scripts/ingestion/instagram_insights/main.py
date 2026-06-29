#!/usr/bin/env python3
"""
Cloud Run Job: ingest Instagram account insights into raw_instagram.insights_raw.

Pulls a small set of glanceable account metrics from the (free) Instagram Graph
API and lands them append-only; stg/marts dedupe and shape downstream. No
per-post storage (the dashboard shows headline metrics, not drilldowns).

Metrics (the three the Marketing tab surfaces):
  - reach          : people reached. De-duplicated, so fetched at PERIOD grain
                     (days_28) for the headline "reach / month", plus a daily
                     series for trend context. Never sum daily reach.
  - profile_views  : profile visits. Additive — daily series, summed downstream.
  - follower_count : total followers. Point-in-time daily series (growth = delta).

Auth: a long-lived access token (Meta app + IG Business/Creator account linked to
a Facebook Page). Tokens last ~60 days — rotate before expiry (see README).

Env vars:
  IG_USER_ID       Instagram Business account id            (required)
  IG_ACCESS_TOKEN  Long-lived access token (Secret Manager) (required)
  GRAPH_VERSION    Graph API version                        default: v21.0
  GRAPH_BASE       Graph API base URL                       default: https://graph.facebook.com
  BQ_PROJECT       Target BQ project                        default: goji-bi
  BQ_DATASET       Target dataset                           default: raw_instagram
  BQ_TABLE         Target table                             default: insights_raw
  LOOKBACK_DAYS    Days of daily history to pull            default: 30

Exit codes: 0 ok / 1 config / 2 BQ failure / 3 Instagram API failure.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import date, datetime, timedelta, timezone

import requests
from google.cloud import bigquery

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("instagram-insights-ingest")

TIMEOUT_S = 30

# (metric, period) specs. reach is fetched twice: a daily series (trend) and the
# de-duplicated 28-day total (the headline monthly reach). Each metric is fetched
# in its own request so one unavailable metric can't sink the others.
INSIGHT_SPECS = [
    ("reach",          "day"),
    ("reach",          "days_28"),
    ("profile_views",  "day"),
    ("follower_count", "day"),
]


def env(name: str, default: str | None = None, required: bool = True) -> str:
    v = os.environ.get(name, default)
    if required and not v:
        log.error(f"missing env var: {name}")
        sys.exit(1)
    return v  # type: ignore[return-value]


def _metric_date(end_time: str | None, fallback: str) -> str:
    """Insight timestamps are ISO like '2026-06-28T07:00:00+0000'; we keep the
    date. Falls back to the window end when a total_value entry has no end_time."""
    if isinstance(end_time, str) and len(end_time) >= 10:
        head = end_time[:10]
        try:
            date.fromisoformat(head)
            return head
        except ValueError:
            pass
    return fallback


def insight_rows(response: dict, ig_user_id: str, period: str,
                 loaded_at: str, window_end: str) -> list[dict]:
    """Convert one Graph API /insights response into raw rows — PURE, unit-tested.

    Handles both response shapes the API uses across versions:
      - time series: data[].values[] = [{value, end_time}, ...]
      - total value: data[].total_value = {value}   (one row, dated window_end)
    A value that isn't a number (some metrics nest dicts) is skipped, not crashed.
    """
    rows: list[dict] = []
    for item in response.get("data", []) or []:
        metric = item.get("name")
        if not metric:
            continue
        values = item.get("values")
        if isinstance(values, list) and values:
            for v in values:
                val = v.get("value") if isinstance(v, dict) else None
                if not isinstance(val, (int, float)):
                    continue
                rows.append({
                    "_loaded_at": loaded_at,
                    "ig_user_id": ig_user_id,
                    "metric":     metric,
                    "metric_date": _metric_date(v.get("end_time"), window_end),
                    "period":     period,
                    "value":      int(val),
                    "payload":    json.dumps(v),
                })
        elif isinstance(item.get("total_value"), dict):
            val = item["total_value"].get("value")
            if isinstance(val, (int, float)):
                rows.append({
                    "_loaded_at": loaded_at,
                    "ig_user_id": ig_user_id,
                    "metric":     metric,
                    "metric_date": window_end,
                    "period":     period,
                    "value":      int(val),
                    "payload":    json.dumps(item["total_value"]),
                })
    return rows


def fetch_metric(session: requests.Session, base_url: str, params: dict) -> dict:
    """One /insights GET. Raises requests.RequestException on transport failure;
    returns {} (logged) on a 4xx the API uses to say 'metric not available for
    this account/version' so a single bad metric doesn't fail the whole job."""
    r = session.get(base_url, params=params, timeout=TIMEOUT_S)
    if r.status_code == 400:
        log.warning("metric %s unavailable (400): %s", params.get("metric"),
                    r.text[:300])
        return {}
    r.raise_for_status()
    return r.json()


def main() -> None:
    ig_user_id = env("IG_USER_ID")
    token      = env("IG_ACCESS_TOKEN")
    version    = env("GRAPH_VERSION", "v21.0", required=False)
    graph_base = env("GRAPH_BASE", "https://graph.facebook.com", required=False)
    bq_project = env("BQ_PROJECT", "goji-bi", required=False)
    bq_dataset = env("BQ_DATASET", "raw_instagram", required=False)
    bq_table   = env("BQ_TABLE", "insights_raw", required=False)
    lookback   = int(env("LOOKBACK_DAYS", "30", required=False))

    table_ref = f"{bq_project}.{bq_dataset}.{bq_table}"
    loaded_at = datetime.now(timezone.utc).isoformat()
    until_d   = date.today()
    since_d   = until_d - timedelta(days=lookback)
    window_end = until_d.isoformat()
    base_url  = f"{graph_base}/{version}/{ig_user_id}/insights"

    log.info("ig_user_id=%s target=%s window=%s..%s", ig_user_id, table_ref,
             since_d, until_d)

    session = requests.Session()
    rows: list[dict] = []
    try:
        for metric, period in INSIGHT_SPECS:
            params = {
                "metric":       metric,
                "period":       period,
                "access_token": token,
            }
            # days_28 is a single trailing window; a day series needs the range.
            if period == "day":
                params["since"] = since_d.isoformat()
                params["until"] = until_d.isoformat()
            resp = fetch_metric(session, base_url, params)
            rows.extend(insight_rows(resp, ig_user_id, period, loaded_at, window_end))
    except requests.RequestException as e:
        log.exception("instagram fetch failed: %s", e)
        sys.exit(3)

    if not rows:
        log.info("no insight rows produced (check account type/token). exiting clean.")
        return

    log.info("loading %d insight rows into %s", len(rows), table_ref)
    bq = bigquery.Client(project=bq_project)
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        schema=[
            bigquery.SchemaField("_loaded_at",  "TIMESTAMP", mode="REQUIRED"),
            bigquery.SchemaField("ig_user_id",  "STRING",    mode="REQUIRED"),
            bigquery.SchemaField("metric",      "STRING",    mode="REQUIRED"),
            bigquery.SchemaField("metric_date", "DATE",      mode="REQUIRED"),
            bigquery.SchemaField("period",      "STRING",    mode="REQUIRED"),
            bigquery.SchemaField("value",       "INT64",     mode="REQUIRED"),
            bigquery.SchemaField("payload",     "JSON"),
        ],
    )
    try:
        load_job = bq.load_table_from_json(rows, table_ref, job_config=job_config)
        load_job.result()
    except Exception as e:
        log.exception("bq load failed: %s", e)
        sys.exit(2)

    log.info("done: wrote %d rows to %s", load_job.output_rows, table_ref)


if __name__ == "__main__":
    main()
