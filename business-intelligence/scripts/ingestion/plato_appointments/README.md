# Plato appointments ingestion job

Cloud Run **Job** that pulls Plato `/appointment` filtered by session date (`start_date`/`end_date`) and appends each appointment as one row into `goji-bi.raw_plato.appointments_raw`. Triggered every 15 minutes by Cloud Scheduler.

Default window each run: `[today - PAST_DAYS, today + FUTURE_DAYS]` = `[today - 14d, today + 31d]`. The window is intentionally generous on the past side to catch any edit to a recent appointment, and a **full month** on the future side so the founder dashboard's "upcoming sessions (next 7 / 30 days)" card and the front-desk new-patient welcome list have real forward data — not just the coming week. `stg.appointments` dedupes by latest `_loaded_at`, so re-pulls of unchanged rows are tolerated.

Because the whole window is re-pulled every run, a *live* appointment's `_loaded_at` advances each run while a **deleted** one goes stale (the API just stops returning it — the ingestion is append-only with no deletion tombstone). Downstream reads that must exclude deleted "ghosts" (the upcoming-count card, `marts.fct_new_patient_welcome`) filter to rows whose `_loaded_at` is within ~30 min of the newest load. Keep `FUTURE_DAYS` ≥ the furthest forward horizon any such reader needs (currently 30), or appointments beyond the window won't refresh and would look stale.

**Why this exists:** the dashboard's invoice-doctor mismatch alert needs appointment data to cross-reference invoice.doctor against the calendar-color-mapped doctor for the same patient on the same day. Originally the dashboard hit Plato live on every cold cache miss; that pushed the cold load to ~90s and burned the rate-limit budget on user-facing requests. Moving ingestion to a background job lets the dashboard read appointments straight from BQ.

## Why we filter by `start_date`/`end_date`, not `modified_since`

`plato_invoices` filters by `modified_since` and that's correct for invoices — when an invoice is created or edited, that's when it becomes relevant. But for appointments, the data point the dashboard cares about is the *session date* (`starttime`), not when the appointment was last touched. Most appointments are booked weeks before the session and never edited, so `last_edited` is far in the past. `modified_since=last_15min` would miss them. Filtering by `start_date`/`end_date` catches every appointment whose session falls in our window, regardless of when it was booked.

The Plato Swagger spec for both filters lives at:

    https://clinic.platomedical.com/swagger/api.json?basePath=/api/

## Local layout

```
plato_appointments/
|-- main.py              ingestion logic (entrypoint)
|-- requirements.txt
|-- Dockerfile
|-- schema.sql           DDL for raw_plato.appointments_raw (run once)
`-- README.md            this file
```

## One-time setup

### 1. Create the raw table

```bash
bq --project_id=goji-bi --location=asia-southeast1 \
  query --use_legacy_sql=false < scripts/ingestion/plato_appointments/schema.sql
```

Verify:
```bash
bq show --schema --format=prettyjson goji-bi:raw_plato.appointments_raw
```

## Deploy the job

From this directory (`scripts/ingestion/plato_appointments/`):

```bash
gcloud run jobs deploy plato-appointments-ingest \
  --source . \
  --region asia-southeast1 \
  --service-account ingestion-sa@goji-bi.iam.gserviceaccount.com \
  --set-secrets PLATO_API_KEY=plato-api-key:latest \
  --set-env-vars PLATO_DB=gojihealth,PAST_DAYS=14,FUTURE_DAYS=31,BQ_PROJECT=goji-bi,BQ_DATASET=raw_plato,BQ_TABLE=appointments_raw \
  --max-retries 1 \
  --task-timeout 600s \
  --memory 512Mi
```

## Smoke test the deployed job

```bash
gcloud run jobs execute plato-appointments-ingest --region asia-southeast1 --wait
```

Then check the rows landed:

```bash
bq query --use_legacy_sql=false \
  'SELECT COUNT(*) AS row_count, MIN(_loaded_at) AS first_load, MAX(_loaded_at) AS last_load
   FROM `goji-bi.raw_plato.appointments_raw`'
```

## Schedule it

Every 15 minutes, all day, at :07/:22/:37/:52: off the :00/:30 slots so it
never pages Plato at the same time as the invoices job (the key's 20 req/min is
shared with the website booking form):

```bash
gcloud scheduler jobs create http plato-appointments-15min \
  --location asia-southeast1 \
  --schedule "7,22,37,52 * * * *" \
  --time-zone "Asia/Singapore" \
  --uri "https://run.googleapis.com/v2/projects/goji-bi/locations/asia-southeast1/jobs/plato-appointments-ingest:run" \
  --http-method POST \
  --oauth-service-account-email "scheduler-sa@goji-bi.iam.gserviceaccount.com"
```

Force a run on demand:
```bash
gcloud scheduler jobs run plato-appointments-15min --location asia-southeast1
```

## One-time backfill

The 14-day default only covers recent appointments. To pull 90 days of past session dates (covers the dashboard mismatch window with buffer), override `PAST_DAYS` for one execution:

```bash
# Bump task timeout for the long backfill
gcloud run jobs update plato-appointments-ingest --region asia-southeast1 --task-timeout 1800s

# 90 days × ~10 appts/day ≈ 900 rows = ~45 pages * 3s = ~2-3 min wall time.
gcloud run jobs execute plato-appointments-ingest \
  --region asia-southeast1 --wait \
  --update-env-vars PAST_DAYS=90

# Restore the normal timeout
gcloud run jobs update plato-appointments-ingest --region asia-southeast1 --task-timeout 600s
```

## What "good" looks like after a few runs

```sql
-- Most-recent version of each appointment
SELECT
  appointment_id,
  appt_date,
  _source_modified_at,
  _loaded_at
FROM `goji-bi.raw_plato.appointments_raw`
QUALIFY ROW_NUMBER() OVER (PARTITION BY appointment_id ORDER BY _loaded_at DESC) = 1
ORDER BY _source_modified_at DESC
LIMIT 20;
```

```sql
-- Appointment count per day, last 30 days
SELECT
  appt_date,
  COUNT(DISTINCT appointment_id) AS appointments
FROM `goji-bi.raw_plato.appointments_raw`
WHERE appt_date >= CURRENT_DATE() - 30
GROUP BY appt_date
ORDER BY appt_date DESC;
```

## Cost expectation

- 15-min cadence × 24h = 96 runs/day. Typical run: 1 Plato request (1 page), ~5-10s wall time.
- Cloud Run Job: ~$0.34/month.
- Cloud Scheduler: $0.10/month (if past the free 3-job tier).
- BQ storage: ~700-900 appointments backfilled + ~10-30/day incremental. Well inside the 10GB free tier.

## Update / redeploy

After any change to `main.py`, `requirements.txt`, or `Dockerfile`:

```bash
gcloud run jobs deploy plato-appointments-ingest --source . --region asia-southeast1
```
