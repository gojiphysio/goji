# Plato patients ingestion job

Cloud Run **Job** that pulls Plato `/patient`, derives a PII-safe
`initial_lastname` (e.g. `"C. Wong"`) **in memory**, and writes only the
derived value into `goji-bi.marts.dim_patient`. The raw name never lands in
BigQuery.

## PII boundary

This is the **only** code path in the BI stack that handles a full patient
name. The boundary is enforced in `main.py::main`:

1. Pull `/patient` paginated.
2. For each row, read `name`, compute `initial_lastname(name)`, discard the
   original.
3. Build a `rows[]` containing only `{patient_id, initial_lastname,
   _updated_at}` — never the full name.
4. Single BQ `WRITE_TRUNCATE` load.

If you ever need a richer derivation (age band, postcode sector, etc.) add
it as a separate column with the same pattern: derive in `main.py`, only
the derived scalar lands.

## One-time setup

### 1. Create the marts table

```bash
bq --project_id=goji-bi --location=asia-southeast1 \
  query --use_legacy_sql=false < scripts/ingestion/plato_patients/schema.sql
```

Verify:
```bash
bq show --schema --format=prettyjson goji-bi:marts.dim_patient
```

### 2. Deploy the job

(`scheduler-sa` and `ingestion-sa` already exist from the invoices job.)

From this directory:

```bash
gcloud run jobs deploy plato-patients-ingest \
  --source . \
  --region asia-southeast1 \
  --service-account ingestion-sa@goji-bi.iam.gserviceaccount.com \
  --set-secrets PLATO_API_KEY=plato-api-key:latest \
  --set-env-vars PLATO_DB=gojihealth,BQ_PROJECT=goji-bi,BQ_DATASET=marts,BQ_TABLE=dim_patient \
  --max-retries 1 \
  --task-timeout 1800s \
  --memory 512Mi
```

The longer timeout reflects that the full `/patient` list is paginated with
a 3s per-page sleep — depending on patient count this may take a few
minutes on the first run.

### 3. Seed it

```bash
gcloud run jobs execute plato-patients-ingest --region asia-southeast1 --wait
```

Then sanity-check (counts and a sample of derived labels for spot-check):

```bash
bq query --use_legacy_sql=false \
  'SELECT COUNT(*) AS n,
          COUNTIF(initial_lastname IS NULL) AS unnamed,
          MAX(_updated_at) AS last_refresh
   FROM `goji-bi.marts.dim_patient`'
```

### 4. Schedule (daily is plenty)

Patient names change rarely. Daily at 06:00 Singapore time:

```bash
gcloud scheduler jobs create http plato-patients-daily \
  --location asia-southeast1 \
  --schedule "0 6 * * *" \
  --time-zone "Asia/Singapore" \
  --uri "https://run.googleapis.com/v2/projects/goji-bi/locations/asia-southeast1/jobs/plato-patients-ingest:run" \
  --http-method POST \
  --oauth-service-account-email "scheduler-sa@goji-bi.iam.gserviceaccount.com"
```

## Redeploy after a code change

```bash
gcloud run jobs deploy plato-patients-ingest --source . --region asia-southeast1
```

## Derivation rules (`initial_lastname`)

- `None` / empty / whitespace-only → `NULL`
- One token (e.g. `"Madonna"`)     → `"Madonna"` unchanged
- Two+ tokens (e.g. `"Charles Wong"`) → `"C. Wong"`

Caveat: Singapore Chinese names where the surname appears first (`"Wong Chee
Hwa"`) will yield `"W. Hwa"`. If we want to handle that properly we can
either (a) add an optional `family_name_first: bool` flag on the patient
record and respect it, or (b) maintain a manual override mapping. Defer
both until we see real ambiguity in the data.
