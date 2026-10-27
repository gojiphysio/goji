# Plato invoices ingestion job

Cloud Run **Job** that pulls Plato `/invoice` (last `LOOKBACK_DAYS`, default 2) and appends each invoice as one row into `goji-bi.raw_plato.invoices_raw`. Triggered every 30 minutes by Cloud Scheduler.

The 2-day window covers a scheduler outage plus anyone editing a yesterday invoice. Re-pulls of unchanged invoices are tolerated because `stg.invoices` keeps the latest version per `invoice_id`.

## Local layout

```
plato_invoices/
|-- main.py              ingestion logic (entrypoint)
|-- requirements.txt
|-- Dockerfile
|-- .dockerignore
|-- schema.sql           DDL for raw_plato.invoices_raw (run once)
`-- README.md            this file
```

## One-time setup

Assumes Phase 1-7 of `architecture/gcp_setup.md` are done: project `goji-bi` exists, billing linked, APIs enabled, `ingestion-sa` created, `plato-api-key` in Secret Manager.

### 1. Create the raw table

```bash
bq --project_id=goji-bi --location=asia-southeast1 \
  query --use_legacy_sql=false < scripts/ingestion/plato_invoices/schema.sql
```

Verify:
```bash
bq show --schema --format=prettyjson goji-bi:raw_plato.invoices_raw
```

### 2. Create the scheduler service account

Cloud Scheduler calls the Cloud Run Jobs admin API. That call needs its own identity with `run.invoker`. We deliberately do **not** reuse `ingestion-sa` for invocation.

```bash
gcloud iam service-accounts create scheduler-sa \
  --display-name="Cloud Scheduler invoker for Cloud Run Jobs"

gcloud projects add-iam-policy-binding goji-bi \
  --member="serviceAccount:scheduler-sa@goji-bi.iam.gserviceaccount.com" \
  --role="roles/run.invoker"
```

## Deploy the job

From this directory (`scripts/ingestion/plato_invoices/`):

```bash
gcloud run jobs deploy plato-invoices-ingest \
  --source . \
  --region asia-southeast1 \
  --service-account ingestion-sa@goji-bi.iam.gserviceaccount.com \
  --set-secrets PLATO_API_KEY=plato-api-key:latest \
  --set-env-vars PLATO_DB=gojihealth,LOOKBACK_DAYS=2,BQ_PROJECT=goji-bi,BQ_DATASET=raw_plato,BQ_TABLE=invoices_raw \
  --max-retries 1 \
  --task-timeout 600s \
  --memory 512Mi
```

First deploy will use Cloud Build to bake the image and push it to Artifact Registry automatically (gcloud creates the `cloud-run-source-deploy` repo on first run).

## Smoke test the deployed job

```bash
gcloud run jobs execute plato-invoices-ingest --region asia-southeast1 --wait
```

`--wait` blocks until completion and prints exit code. Then check the rows landed:

```bash
bq query --use_legacy_sql=false \
  'SELECT COUNT(*) AS row_count, MIN(_loaded_at) AS first_load, MAX(_loaded_at) AS last_load
   FROM `goji-bi.raw_plato.invoices_raw`'
```

Logs (most recent execution):
```bash
gcloud run jobs executions list --job plato-invoices-ingest --region asia-southeast1 --limit 1
gcloud logging read 'resource.type="cloud_run_job" resource.labels.job_name="plato-invoices-ingest"' \
  --limit 50 --format="value(timestamp, jsonPayload.message, textPayload)"
```

## Schedule it

Every 30 minutes during Singapore business hours (8am-8pm) at :12 and :42, off
the :00/:30 slots so it never pages Plato at the same time as the appointments
job (the key's 20 req/min is shared with the website booking form). These runs
only fetch the last `RECENT_DAYS` (14) of invoices, 1-2 pages:

```bash
gcloud scheduler jobs create http plato-invoices-30min \
  --location asia-southeast1 \
  --schedule "12,42 8-20 * * *" \
  --time-zone "Asia/Singapore" \
  --uri "https://run.googleapis.com/v2/projects/goji-bi/locations/asia-southeast1/jobs/plato-invoices-ingest:run" \
  --http-method POST \
  --oauth-service-account-email "scheduler-sa@goji-bi.iam.gserviceaccount.com"
```

Plato ignores `modified_since` on `/invoice`, so a payment added to an invoice
older than 14 days is only picked up by a nightly full sweep:

```bash
gcloud scheduler jobs create http plato-invoices-full-nightly \
  --location asia-southeast1 \
  --schedule "30 21 * * *" \
  --time-zone "Asia/Singapore" \
  --uri "https://run.googleapis.com/v2/projects/goji-bi/locations/asia-southeast1/jobs/plato-invoices-ingest:run" \
  --http-method POST \
  --headers "Content-Type=application/json" \
  --message-body '{"overrides":{"containerOverrides":[{"env":[{"name":"RECENT_DAYS","value":"0"}]}]}}' \
  --oauth-service-account-email "scheduler-sa@goji-bi.iam.gserviceaccount.com"
```

Force a run on demand:
```bash
gcloud scheduler jobs run plato-invoices-30min --location asia-southeast1
```

## One-time backfill

The job's 7-day default only covers the last week. To pull historical invoices, execute once with a large lookback. This overrides the env var for that execution only:

```bash
gcloud run jobs execute plato-invoices-ingest \
  --region asia-southeast1 \
  --wait \
  --update-env-vars RECENT_DAYS=0
```

`RECENT_DAYS=0` pages every invoice Plato has (the same thing the nightly sweep does). Plato pagination + 3s per-page sleep means a full backfill may take several minutes. The job's `--task-timeout` is 600s; bump it temporarily if needed:

```bash
gcloud run jobs update plato-invoices-ingest --region asia-southeast1 --task-timeout 1800s
# ... run backfill ...
gcloud run jobs update plato-invoices-ingest --region asia-southeast1 --task-timeout 600s
```

## What "good" looks like after a few runs

```sql
-- Most-recent version of each invoice (this is what stg.invoices will encode)
SELECT
  invoice_id,
  invoice_date,
  _source_modified_at,
  _loaded_at
FROM `goji-bi.raw_plato.invoices_raw`
QUALIFY ROW_NUMBER() OVER (PARTITION BY invoice_id ORDER BY _loaded_at DESC) = 1
ORDER BY _source_modified_at DESC
LIMIT 20;
```

```sql
-- Sanity-check booking vs recognised by day, straight off raw
SELECT
  invoice_date,
  COUNT(*) AS invoice_versions,
  COUNT(DISTINCT invoice_id) AS unique_invoices
FROM `goji-bi.raw_plato.invoices_raw`
WHERE invoice_date >= CURRENT_DATE() - 14
GROUP BY invoice_date
ORDER BY invoice_date DESC;
```

## Cost expectation

Volume math at Goji's scale (assume ~50 invoices/day of real activity once busy):

- Each run pulls every invoice modified in the last 2 days, so ~100 invoices per run.
- 30-min cadence × 15 active hours = 30 runs/day = ~3,000 row-appends/day.
- The vast majority are duplicates of the same invoice across runs. `stg.invoices` collapses them to one row per `invoice_id` for downstream queries.
- Annualised: ~1M rows/year in the raw table at ~5 KB each = ~5 GB. Still inside the 10 GB BigQuery free tier.

Each run is ~10s wall-clock and well under 100 MB memory. Expected total cost: a few cents per month, dominated by Cloud Build minutes on each redeploy. If the raw table ever starts approaching the free-tier limit, add a weekly MERGE-dedupe job rather than reducing the lookback further.

## Update / redeploy

After any change to `main.py`, `requirements.txt`, or `Dockerfile`:

```bash
gcloud run jobs deploy plato-invoices-ingest --source . --region asia-southeast1
```

(Same command as initial deploy; gcloud knows to update in place.)
