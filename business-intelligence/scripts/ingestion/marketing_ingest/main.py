#!/usr/bin/env python3
"""
Cloud Run Job: ingest marketing-channel metrics into raw_marketing.*.

One consolidated job for the marketing-integration track (the Marketing-tab
"pending integration" seams). Today it pulls **Instagram reach, profile views,
and follower count**; GBP clicks/calls and Google-review velocity are the next
sources and slot in as sibling handlers writing sibling raw_marketing tables — a
single image / scheduler / deploy gate for the whole track (deliberately NOT
folded into the plato_* jobs: different domain and failure mode).

Which sources run is controlled by SOURCES (comma-separated); each handler
buffers rows then does a single load_table_from_json(..., WRITE_APPEND), same
free-tier pattern as the plato_* jobs. Dedupe to "latest per key" happens in
stg, never here.

### Instagram metrics — additive vs de-duplicated
Different Instagram metrics aggregate differently, so we store each honestly and
let downstream decide how to read it (ingestion/AGENTS.md):
  - **reach** counts *unique accounts reached*, so it is NOT additive: monthly
    reach is not the sum of daily reach. We pull Meta's rolling 28-day
    de-duplicated reach (`period=days_28`) once per run; downstream reads the
    latest reading in-window, it does not sum.
  - **profile_views** is an additive daily count (`period=day`): one row per day,
    summed downstream over the window — the "did reach turn into interest?" step.
  - **followers_count** is a running total (a field, not an insight): one snapshot
    row per day; downstream reads the latest and derives growth as latest−first.

The reach pull is the proven core and stays fatal on API failure (exit 3). The
newer profile_views / followers_count pulls are **best-effort**: a metric-name or
permission hiccup on them logs a warning and is skipped, so it can never break the
established reach ingestion. Each metric the run captures is buffered and written
in a single append load.

### Search Console — additive counts vs weighted position
`clicks` and `impressions` are additive; `ctr` and `position` are NOT. Position
is an impression-weighted average, so a window's position is
SUM(position*impressions)/SUM(impressions), never AVG(position) — the mart
encodes this so no caller has to remember. Search Console also backfills for
~2-3 days, so each run re-pulls a trailing window and the latest row wins in stg.

Env vars:
  SOURCES              Comma list of sources to run     default: instagram
  IG_USER_ID           Instagram Business/Creator id     (required for instagram)
  META_GRAPH_TOKEN     Long-lived Meta access token      (required for instagram; secret)
  GRAPH_API_VERSION    Graph API version                 default: v21.0
  IG_METRIC_PERIOD     Reach aggregation period          default: days_28
  GSC_SITE_URL         Property, e.g. sc-domain:gojiphysio.com  (required for search_console)
  GSC_LOOKBACK_DAYS    Trailing re-pull window           default: 7
  GSC_ROW_LIMIT        Max rows per dimension call       default: 5000
  BQ_PROJECT           Target BQ project                 default: goji-bi
  BQ_DATASET           Target dataset                    default: raw_marketing

Exit codes: 0 on success, 1 on config error, 2 on BQ failure, 3 on API failure.
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

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


def parse_insight_latest(body: dict) -> tuple[str, int]:
    """Extract (metric_date, value) from a Meta *insights* response. Pure, so it's
    unit-tested without a network call — the response shape is the failure-prone
    part. Takes the LAST datapoint (the most recent reading in the series).

    Shape: {"data":[{"name":"reach","values":[{"value":1234,
             "end_time":"2026-07-11T07:00:00+0000"}, ...]}]}
    Raises (KeyError/IndexError/ValueError/TypeError) on any unexpected shape,
    which the caller turns into exit code 3 (reach) or a skip (best-effort pulls).
    """
    latest = body["data"][0]["values"][-1]
    return latest["end_time"][:10], int(latest["value"])


# Backwards-compatible alias: reach is just the first insight metric we pulled.
parse_reach = parse_insight_latest


def parse_followers(body: dict, metric_date: str) -> tuple[str, int]:
    """Extract (metric_date, value) from a Meta *field* response for a running
    total (followers_count is a field on the IG user object, not an insight, so
    there's no time series — it's the current total). Pure for unit testing.

    Shape: {"followers_count": 1234, "id": "1784..."}
    metric_date is supplied by the caller (the run's UTC date) since the field
    response carries no timestamp. Raises on an unexpected shape.
    """
    return metric_date, int(body["followers_count"])


def _ig_get(url: str, params: dict) -> dict:
    """GET a Meta Graph endpoint and return the parsed JSON body. Raises
    requests.RequestException on transport/HTTP failure. Never logs the response
    body — it can echo the access token back."""
    r = requests.get(url, params=params, timeout=TIMEOUT_S)
    r.raise_for_status()
    return r.json()


def ingest_instagram(project: str, dataset: str) -> None:
    """Pull Instagram account metrics and append them to
    raw_marketing.instagram_raw. Generic (metric, metric_date, value, payload)
    shape so each metric is just more rows, not a schema change
    (ingestion/AGENTS.md):
      - reach          rolling-28-day de-duplicated reach     (fatal on failure)
      - profile_views  additive daily profile visits          (best-effort)
      - followers_count running follower total (snapshot)      (best-effort)

    Reach is the proven core and exits 3 if it fails. The two newer pulls are
    best-effort: a metric-name/permission issue logs a warning and is skipped so
    it can never break reach ingestion. All captured rows load in one append."""
    ig_user_id = env("IG_USER_ID")
    token = env("META_GRAPH_TOKEN")
    version = env("GRAPH_API_VERSION", "v21.0", required=False)
    period = env("IG_METRIC_PERIOD", "days_28", required=False)
    loaded_at = datetime.now(timezone.utc).isoformat()
    today = datetime.now(timezone.utc).date().isoformat()
    insights_url = f"{GRAPH_BASE}/{version}/{ig_user_id}/insights"
    account_url = f"{GRAPH_BASE}/{version}/{ig_user_id}"

    rows: list[dict] = []

    # 1) Reach — de-duplicated, rolling-28-day. FATAL on failure (the core metric).
    log.info("fetching IG reach: user=%s version=%s period=%s", ig_user_id, version, period)
    try:
        body = _ig_get(insights_url, {"metric": "reach", "period": period, "access_token": token})
    except requests.RequestException as e:
        log.exception("meta graph reach fetch failed: %s", e)
        sys.exit(3)
    try:
        metric_date, value = parse_insight_latest(body)
    except (KeyError, IndexError, ValueError, TypeError) as e:
        log.error("unexpected reach payload (%s): %s", e, body.get("data") if isinstance(body, dict) else body)
        sys.exit(3)
    rows.append({"_loaded_at": loaded_at, "metric": f"reach_{period}",
                 "metric_date": metric_date, "value": value,
                 "payload": body["data"][0]["values"][-1]})

    # 2) Profile views — additive daily count. BEST-EFFORT.
    log.info("fetching IG profile_views (period=day)")
    try:
        body = _ig_get(insights_url, {"metric": "profile_views", "period": "day", "access_token": token})
        metric_date, value = parse_insight_latest(body)
        rows.append({"_loaded_at": loaded_at, "metric": "profile_views",
                     "metric_date": metric_date, "value": value,
                     "payload": body["data"][0]["values"][-1]})
    except (requests.RequestException, KeyError, IndexError, ValueError, TypeError) as e:
        log.warning("IG profile_views skipped (%s) — check metric availability for %s", e, version)

    # 3) Followers count — running total snapshot (a field, not an insight). BEST-EFFORT.
    log.info("fetching IG followers_count")
    try:
        body = _ig_get(account_url, {"fields": "followers_count", "access_token": token})
        metric_date, value = parse_followers(body, today)
        rows.append({"_loaded_at": loaded_at, "metric": "followers_count",
                     "metric_date": metric_date, "value": value, "payload": body})
    except (requests.RequestException, KeyError, ValueError, TypeError) as e:
        log.warning("IG followers_count skipped (%s)", e)

    schema = [
        bigquery.SchemaField("_loaded_at", "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("metric", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("metric_date", "DATE", mode="REQUIRED"),
        bigquery.SchemaField("value", "INT64", mode="REQUIRED"),
        bigquery.SchemaField("payload", "JSON"),
    ]
    _bq_load(rows, f"{project}.{dataset}.instagram_raw", schema, project)


def parse_search_analytics(body: dict, dimension: str) -> list[dict]:
    """Flatten a Search Console `searchAnalytics.query` response into rows.

    Pure, so the response-shape handling is unit-tested without a network call
    (same reason `parse_insight_latest` is pure).

    Shape: {"rows":[{"keys":["2026-08-30","physio near me"],
                     "clicks":3,"impressions":40,"ctr":0.075,"position":8.2}]}

    The `date` dimension is always requested first, so `keys[0]` is the date and
    `keys[1]` (when present) is the query/page. A response with no `rows` at all
    is normal — Search Console returns nothing for a day with no impressions —
    so it yields [] rather than raising.

    **`position` is an impression-weighted average, never a sum.** It is stored
    per row and must be re-weighted downstream, which is why `impressions`
    always travels beside it.
    """
    out: list[dict] = []
    for r in body.get("rows", []) or []:
        keys = r.get("keys") or []
        if not keys:
            continue
        out.append({
            "metric_date":     keys[0],
            "dimension":       dimension,
            "dimension_value": keys[1] if len(keys) > 1 else "",
            "clicks":          int(r.get("clicks") or 0),
            "impressions":     int(r.get("impressions") or 0),
            "ctr":             float(r.get("ctr") or 0.0),
            "position":        float(r.get("position") or 0.0),
        })
    return out


def ingest_search_console(project: str, dataset: str) -> None:
    """Pull Google Search Console performance into raw_marketing.search_console_raw.

    Closes the organic-search blind spot: 30-odd condition/service pages are
    built for organic with no visibility into impressions, position, or query
    (`ads_PaidOrganicStats` is empty because GSC isn't linked to Ads either).

    Three dimensions per run, each a separate API call and all best-effort after
    the first:
      - `total` — one row per day, the headline clicks/impressions/CTR/position
      - `query` — top queries per day (what we actually rank for)
      - `page`  — top pages per day (which content earns the impressions)

    **Auth is the job's own service account** (ADC), not a stored secret — add
    the SA email as a *restricted* user on the Search Console property. That
    keeps this in the "free / DIY first" lane with no token to rotate.

    **Re-pulls a trailing window on every run** (`GSC_LOOKBACK_DAYS`, default 7)
    because Search Console backfills for ~2-3 days after the fact: a row pulled
    on day 1 is provisional. Append-only + dedupe-to-latest in `stg.search_console`
    means the late correction simply wins, same as the plato_* re-pull window.
    """
    site_url = env("GSC_SITE_URL")                                  # e.g. sc-domain:gojiphysio.com
    lookback = int(env("GSC_LOOKBACK_DAYS", "7", required=False))
    row_limit = int(env("GSC_ROW_LIMIT", "5000", required=False))
    loaded_at = datetime.now(timezone.utc).isoformat()

    # GSC has no data for the last ~2 days; asking anyway is harmless (empty rows).
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=lookback)

    try:
        import google.auth
        from google.auth.transport.requests import AuthorizedSession
        creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/webmasters.readonly"])
        session = AuthorizedSession(creds)
    except Exception as e:
        log.exception("search console auth failed: %s", e)
        sys.exit(1)

    endpoint = ("https://searchconsole.googleapis.com/webmasters/v3/sites/"
                f"{quote(site_url, safe='')}/searchAnalytics/query")

    def fetch(dimensions: list[str]) -> dict:
        r = session.post(endpoint, json={
            "startDate":  start.isoformat(),
            "endDate":    end.isoformat(),
            "dimensions": dimensions,
            "rowLimit":   row_limit,
            "dataState":  "all",     # include still-fresh (provisional) days
        }, timeout=TIMEOUT_S)
        r.raise_for_status()
        return r.json()

    rows: list[dict] = []

    # 1) Daily totals. FATAL — if this fails the source produced nothing useful.
    log.info("fetching GSC totals: site=%s %s..%s", site_url, start, end)
    try:
        body = fetch(["date"])
        rows.extend(parse_search_analytics(body, "total"))
    except requests.RequestException as e:
        log.exception("search console totals fetch failed "
                      "(is the job SA a user on %s?): %s", site_url, e)
        sys.exit(3)
    except (KeyError, IndexError, ValueError, TypeError) as e:
        log.error("unexpected search console payload: %s", e)
        sys.exit(3)

    # 2) + 3) Query and page breakdowns. BEST-EFFORT — a quota or shape problem
    # on these must not lose the day's headline numbers.
    for dim in ("query", "page"):
        log.info("fetching GSC by %s", dim)
        try:
            body = fetch(["date", dim])
            rows.extend(parse_search_analytics(body, dim))
        except (requests.RequestException, KeyError, IndexError, ValueError, TypeError) as e:
            log.warning("GSC %s breakdown skipped (%s)", dim, e)

    for r in rows:
        r["_loaded_at"] = loaded_at

    schema = [
        bigquery.SchemaField("_loaded_at", "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("metric_date", "DATE", mode="REQUIRED"),
        bigquery.SchemaField("dimension", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("dimension_value", "STRING"),
        bigquery.SchemaField("clicks", "INT64", mode="REQUIRED"),
        bigquery.SchemaField("impressions", "INT64", mode="REQUIRED"),
        bigquery.SchemaField("ctr", "FLOAT64"),
        bigquery.SchemaField("position", "FLOAT64"),
    ]
    _bq_load(rows, f"{project}.{dataset}.search_console_raw", schema, project)


# source name -> handler(project, dataset). Add "gbp"/"reviews" here next.
SOURCES = {
    "instagram":      ingest_instagram,
    "search_console": ingest_search_console,
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
