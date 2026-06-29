# instagram_insights — Cloud Run Job

Pulls Instagram account insights (reach, profile views, follower count) from the
free Instagram Graph API into `raw_instagram.insights_raw`, append-only.
`stg.instagram` dedupes to the latest load; `marts.fct_instagram` is the thin
fact the dashboard reads to light the Marketing-tab Instagram cards.

Mirrors the `plato_*` jobs (same `env()` helper, exit codes 0/1/2/3, buffer →
single `load_table_from_json`). No per-post data — headline metrics only.

## One-time setup (prerequisites)

1. **Account:** Goji's Instagram must be a **Business or Creator** account
   **linked to a Facebook Page** (Graph API Insights require this).
2. **Meta app:** create a Business-type app at developers.facebook.com with
   `instagram_basic`, `instagram_manage_insights`, `pages_read_engagement`.
3. **Token + id:** generate a **long-lived access token** (~60 days) and note the
   **Instagram Business account id** (`IG_USER_ID`). Store the token in Secret
   Manager:

       printf '%s' "<LONG_LIVED_TOKEN>" | gcloud secrets create ig-access-token --data-file=-

4. **Dataset:** `bq mk --location=<your BQ location> raw_instagram`, then run
   `schema.sql` once to create `insights_raw`.
5. **Grants:** the **ingestion** job SA needs `dataEditor` on `raw_instagram`;
   the **dashboard** SA needs `dataViewer` on `raw_instagram` (so its stg/marts
   reads work) — see `scripts/dashboard/DEPLOY.md`.

## Token rotation

Long-lived tokens expire ~60 days out. Refresh before expiry (exchange via the
Graph API) and update the `ig-access-token` secret. **Ops cadence: rotate
monthly.** If insights stop flowing, an expired token is the first suspect.

## Run

    gcloud run jobs execute instagram-insights-ingest --region <region> --project goji-bi --wait

Deployed + scheduled (daily) via `.github/workflows/deploy-dashboard.yml`.

## Env vars

| var | default | notes |
|---|---|---|
| `IG_USER_ID` | — | required; IG Business account id |
| `IG_ACCESS_TOKEN` | — | required; from Secret Manager |
| `GRAPH_VERSION` | `v21.0` | bump as Meta deprecates metrics |
| `BQ_DATASET` | `raw_instagram` | |
| `LOOKBACK_DAYS` | `30` | daily-series history per run |

## Notes

- **Reach is de-duplicated** — we fetch it at `days_28` (the headline monthly
  reach) plus a daily series for trend. Never sum daily reach.
- Metric availability shifts across Graph API versions; each metric is fetched in
  its own request, and a `400` ("not available") is logged and skipped so one bad
  metric can't sink the run. Confirm the metric set on first run, bump
  `GRAPH_VERSION` as needed.
