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
- Additive metrics (clicks, impressions, followers) sum daily downstream — no
  special handling. Only de-duplicated metrics (e.g. Instagram reach) need a
  period-level fetch.

## Ops
- **Secrets** live in Secret Manager, mounted to the Job via `--set-secrets`;
  never in code or git. BigQuery auth is ADC (the Job's service account).
- The **ingestion SA** writes `raw_*`; the **dashboard SA** reads `stg`/`marts`
  (one `dataViewer` grant per new `raw_*` dataset, or authorized views).
- Schedule with **Cloud Scheduler** (daily unless the source needs more).
- Wire into `.github/workflows/deploy-dashboard.yml`: add the path, a change-detect
  output, a test step, and a gated `gcloud run jobs deploy` step (copy the
  `plato_patients` block). Tests gate the deploy.
- SQL is idempotent; `deploy_all.sh` auto-globs new `.sql` files.
