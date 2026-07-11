# Marketing-metrics ingestion job

One consolidated Cloud Run **Job** for the Marketing-tab integration seams. Each
run pulls the enabled `SOURCES` (comma list) from their external APIs and appends
to `goji-bi.raw_marketing.*`. Today: **Instagram reach**. Next seams (same job,
sibling handlers + tables): GBP booking clicks/calls, Google-review velocity.

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
Meta Graph API ─▶ raw_marketing.instagram_raw ─▶ stg.instagram ─▶ marts.fct_instagram_reach ─▶ dashboard card
   (per run)        (append-only)                 (latest per       (reach series)             (Marketing tab)
                                                    metric,date)
```

Reach is **de-duplicated** (unique accounts), so it is not additive: monthly
reach ≠ sum of daily reach. The job stores Meta's rolling 28-day reach
(`metric = 'reach_days_28'`); downstream reads the **latest reading in-window**,
never a SUM.

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
