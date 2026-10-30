# Marketing-metrics ingestion job

One consolidated Cloud Run **Job** for the Marketing-tab integration seams. Each
run pulls the enabled `SOURCES` (comma list) from their external APIs and appends
to `goji-bi.raw_marketing.*`. Today: **Instagram reach, profile views, and
follower count**. Next seams (same job, sibling handlers + tables): GBP booking
clicks/calls, Google-review velocity.

Why one job and not one-per-card: cost is identical (~$0 — a daily job is well
inside the Cloud Run free tier); consolidating cuts the operational surface to a
single image / scheduler / deploy gate. It is deliberately **not** folded into
the `plato_*` jobs — different domain and failure mode (a Meta token expiry must
not touch patient ingest).

## Local layout

```
marketing_ingest/
|-- main.py              per-source dispatch (entrypoint)
|-- requirements.txt
|-- Dockerfile
|-- .dockerignore
|-- schema.sql           DDL for raw_marketing.instagram_raw (run once)
`-- README.md            this file
```

## Data flow

```
Meta Graph API ─▶ raw_marketing.instagram_raw ─▶ stg.instagram ─▶ marts.fct_instagram_* ─▶ dashboard cards
   (per run)        (append-only)                 (latest per       (reach / profile_views /  (Marketing tab)
                                                    metric,date)      followers)
```

Each metric aggregates differently, and the marts encode how to read it:
- **reach** (`metric = 'reach_days_28'`) is **de-duplicated** (unique accounts),
  so it is not additive: monthly reach ≠ sum of daily reach. Downstream reads the
  **latest reading in-window** (`marts.fct_instagram_reach`), never a SUM.
- **profile_views** (`metric = 'profile_views'`, `period=day`) IS additive:
  downstream **SUMs** over the window (`marts.fct_instagram_profile_views`).
- **followers_count** (`metric = 'followers_count'`) is a running **total**
  snapshot: downstream reads the **latest** for the count and derives growth as
  `latest − first` (`marts.fct_instagram_followers`), never a SUM.

Reach is the proven core and is fatal on API failure (exit 3); profile_views and
followers_count are **best-effort** (a metric-name/permission hiccup logs a
warning and is skipped) so they can never break reach ingestion.

## One-time setup

### 0. Meta prerequisites (manual, one-time)
- The Instagram account must be a **Business/Creator** account linked to a
  Facebook Page.
- Create a Meta app with `instagram_basic` + `instagram_manage_insights`, mint a
  **long-lived** access token, and note the IG user id
  (`GET /{page-id}?fields=instagram_business_account`).
- Store the token in Secret Manager:
  ```bash
  printf "%s" "<LONG_LIVED_TOKEN>" | \
    gcloud secrets create meta-graph-token --data-file=- --project=goji-bi
  ```

### 1. Create the dataset + raw table
```bash
bq --location=asia-southeast1 mk --dataset goji-bi:raw_marketing   # if absent
bq --project_id=goji-bi --location=asia-southeast1 \
  query --use_legacy_sql=false < scripts/ingestion/marketing_ingest/schema.sql
```

### 2. Deploy stg + mart
```bash
cd scripts/sql && ./deploy_all.sh
```

### 3. Grant the dashboard SA read on the new dataset
```bash
bq add-iam-policy-binding \
  --member="serviceAccount:dashboard-sa@goji-bi.iam.gserviceaccount.com" \
  --role="roles/bigquery.dataViewer" goji-bi:raw_marketing
```

Deploy is otherwise handled by `.github/workflows/deploy-dashboard.yml` on push
to `main` (build + `gcloud run jobs deploy`); a daily Cloud Scheduler trigger
runs the job. Until the token + data exist, the dashboard card degrades to "—".

## Env vars

| Var | Default | Notes |
|---|---|---|
| `SOURCES` | `instagram` | comma list of sources to run |
| `IG_USER_ID` | — | Instagram Business/Creator id (required for instagram) |
| `META_GRAPH_TOKEN` | — | long-lived token (secret; required for instagram) |
| `GRAPH_API_VERSION` | `v21.0` | Graph API version |
| `IG_METRIC_PERIOD` | `days_28` | reach aggregation period |
| `BQ_PROJECT` / `BQ_DATASET` | `goji-bi` / `raw_marketing` | target |

Exit codes: 0 ok / 1 config / 2 BQ / 3 API.

---

## Source: Google Search Console (organic search)

Closes the organic blind spot — 30-odd condition/service pages are built for
organic search with no visibility into impressions, position, or query.

### Why no secret

Unlike Instagram, this source authenticates as the **job's own service account**
(ADC). There is no token to mint, store, or rotate. One manual step instead:

> Search Console → **Settings** → **Users and permissions** → **Add user** →
> `ingestion-sa@goji-bi.iam.gserviceaccount.com`, permission **Restricted**.

And enable the API once on the project — easy to miss, because nothing else in
this repo uses it and the failure is a runtime `SERVICE_DISABLED`, not a deploy
error:

```bash
gcloud services enable searchconsole.googleapis.com --project=goji-bi
```

Then set the repo variable `GSC_SITE_URL` (e.g. `sc-domain:gojiphysio.com` for a
domain property, or `https://www.gojiphysio.com/` for a URL-prefix property).
The deploy step adds `search_console` to `SOURCES` once that variable exists;
Instagram and Search Console gate independently, so either can go live alone.

### One-time table

Paths below are **from the repo root** — `schema.sql` lives in this job's
directory, so a bare `< schema.sql` only works if you have already `cd`'d here.

```bash
bq query --use_legacy_sql=false \
  < business-intelligence/scripts/ingestion/marketing_ingest/schema.sql
```

The file holds both landing tables and every statement is
`CREATE TABLE IF NOT EXISTS`, so re-running it is a no-op for `instagram_raw`.

### What it pulls

Three dimensions per run, into `raw_marketing.search_console_raw`:

| `dimension` | Grain | Purpose |
|---|---|---|
| `total` | one row/day | headline clicks, impressions, CTR, position |
| `query` | day × query | what we actually rank for |
| `page`  | day × page  | which content earns the impressions |

`total` is fatal on failure; the two breakdowns are best-effort (a quota or
shape problem must not lose the day's headline numbers) — the same
fatal-core / best-effort-extras split as Instagram reach.

### Two traps this encodes

1. **`position` is impression-weighted, never averaged.** A window's true
   average position is `SUM(position*impressions)/SUM(impressions)`.
   `marts.fct_search_console_daily` exposes `position_weight` precisely so no
   caller reaches for `AVG(position)` and quietly gets a wrong number. CTR is
   likewise recomputed from summed clicks/impressions, never averaged.
2. **Search Console backfills for ~2-3 days.** Every run re-pulls a trailing
   window (`GSC_LOOKBACK_DAYS`, default 7) and the latest row per key wins in
   `stg.search_console` — same re-pull idiom as the `plato_*` jobs. A row read
   on day 1 is provisional; the correction simply overwrites it.

Also note Search Console **omits low-volume queries** for privacy, so the
`query` rows for a day will not sum to that day's `total` row. That is expected.
Use `fct_search_console_daily` for headline numbers and
`fct_search_console_terms` only for "what are we ranking for".

**Backfilling history** needs no code change: run the job once with a long
lookback and the API's maximum row limit (date×query is ~50 rows a day, so the
default 5000 truncates past ~3 months). Re-loaded days just win in stg.

```bash
gcloud run jobs execute marketing-ingest --region=asia-southeast1 --project=goji-bi \
  --update-env-vars=SOURCES=search_console,GSC_LOOKBACK_DAYS=400,GSC_ROW_LIMIT=25000 --wait
```

Done 2026-10-30: Google holds data for the property from **2026-07-13**, so that
is where history starts.

### Data flow

```
Search Console API ─▶ raw_marketing.search_console_raw ─▶ stg.search_console ─▶ marts.fct_search_console_daily  ─▶ Organic search card
      (per run)          (append-only)                     (latest per            marts.fct_search_console_terms
                                                            date+dim+value)
```
