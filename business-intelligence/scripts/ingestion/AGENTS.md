# Ingestion jobs — conventions

Each subdirectory is a Cloud Run **Job** that pulls an external API into BigQuery.
The four `plato_*` jobs are the template — **mirror their structure** for any new
source (Instagram, Search Console, GBP, …).

## Pattern
- Layout: `scripts/ingestion/<source>/{main.py, requirements.txt, Dockerfile,
  schema.sql, README.md, test_extract.py}`.
- `main.py`: same `env()` helper, `logging` setup, and exit codes (0 ok / 1 config
  / 2 BQ / 3 API) as `plato_invoices/main.py`; buffer rows then a single
  `load_table_from_json(..., WRITE_APPEND)`.
- **Data flow:** external API → append-only `raw_<source>.<table>_raw` →
  `sql/stg/<NN>_<source>.sql` (latest-row view, `QUALIFY ROW_NUMBER()…=1`) →
  `sql/marts/<NN>_fct_<source>.sql` (thin fact). Dedupe in `stg`, never in the job.
- **Generic raw shape** (`_loaded_at, …keys…, metric, metric_date, value, payload
  JSON`): the `metric` column means adding metrics later is more rows, not a schema
  change.
- Additive metrics (clicks, impressions, profile views) sum daily downstream — no
  special handling. De-duplicated metrics (e.g. Instagram reach) need a
  period-level fetch. Running **totals** (e.g. `followers_count`) are snapshots:
  store one row per day and read the **latest** in-window (growth = latest−first),
  never SUM. **Weighted averages** (e.g. Search Console `position`) are a fourth
  kind: store the per-row value *and* its weight (impressions) so a window can
  compute `SUM(value*weight)/SUM(weight)` — never `AVG()`. The mart exposes the
  weight column so no caller has to remember this. `marketing_ingest` today pulls reach (dedup), `profile_views`
  (additive), and `followers_count` (total) — reach is fatal-on-failure, the other
  two are best-effort so a metric-name/permission hiccup can't break reach ingest.

## Ops
- **Secrets** live in Secret Manager, mounted to the Job via `--set-secrets`;
  never in code or git. BigQuery auth is ADC (the Job's service account).
  **Prefer no secret at all** where the API accepts the Job's own service
  account (Search Console: add `ingestion-sa@` as a restricted user on the
  property) — nothing to mint, store, or rotate.
- **Sources gate independently.** The deploy step builds `SOURCES` from whatever
  is configured and deploys if *any* source is ready, so a new source can go
  live before an existing one is provisioned (and a missing token can't block
  it). An unconfigured source is left out; its dashboard card stays "—".
- **Gate a source on a repo var, never on `gcloud secrets describe`.** The
  deployer SA has no Secret Manager role, so that probe always returns
  PERMISSION_DENIED whether or not the secret exists. It is a false negative that
  hides while the step no-ops, then drops the source the first time the step
  actually runs. Mounting a secret needs `secretAccessor` on the **runtime** SA,
  not read access for the deployer — so if a secret is truly missing, let the
  deploy fail loudly. (Cost us Instagram ingestion for one cycle, 2026-09-02.)
- **`--set-env-vars` REPLACES the whole env block.** Every deploy must pass every
  var the job needs; a var omitted because its branch didn't run is silently
  deleted from the live job. This is what turns the gating false-negative above
  from "skipped a source" into "wiped `IG_USER_ID`".
- The **ingestion SA** writes `raw_*`; the **dashboard SA** reads `stg`/`marts`
  (one `dataViewer` grant per new `raw_*` dataset, or authorized views).
- Schedule with **Cloud Scheduler** (daily unless the source needs more).
- Wire into `.github/workflows/deploy-dashboard.yml`: add the path, a change-detect
  output, a test step, and a gated `gcloud run jobs deploy` step (copy the
  `plato_patients` block). Tests gate the deploy.
- SQL is idempotent; `deploy_all.sh` auto-globs new `.sql` files.
