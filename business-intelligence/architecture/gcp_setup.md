# GCP Setup Runbook

One-time setup of the `goji-bi` GCP project that hosts the warehouse (BigQuery), ingestion jobs (Cloud Run + Scheduler), and secrets (Secret Manager). Run on your local Mac, authenticated as `hello@gojiphysio.com`.

## Prerequisites

- `gcloud` CLI installed and authenticated as `hello@gojiphysio.com`.
- Billing account `015B7E-11A7E1-397B4D` exists, is OPEN, and `hello@gojiphysio.com` has **Billing Account User** on it.
- Region: everything lives in `asia-southeast1` (Singapore). Don't mix regions; egress will start costing money the moment you do.

Shell variables used throughout. Set these once at the top of your session:

```bash
export PROJECT_ID=goji-bi
export BILLING_ACCOUNT=015B7E-11A7E1-397B4D
export REGION=asia-southeast1
export SA_NAME=ingestion-sa
export SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
```

If `goji-bi` is taken globally, fall back to `goji-bi-sg` or `gojihealth-bi` and update `PROJECT_ID` accordingly.

---

## Phase 1: confirm identity and billing

```bash
gcloud auth list                              # hello@gojiphysio.com should be ACTIVE
gcloud config get-value account               # sanity check
gcloud organizations list                     # capture ORG_ID if non-empty
gcloud billing accounts list                  # 015B7E-11A7E1-397B4D should show OPEN=True
```

If `organizations list` returns a row, note the ID (used in Phase 2 to create the project under the org). Empty is fine too, the project just lives standalone.

## Phase 2: create the project

Without an org:
```bash
gcloud projects create "$PROJECT_ID" --name="Goji BI"
```

Under an org (replace `ORG_ID`):
```bash
gcloud projects create "$PROJECT_ID" --name="Goji BI" --organization=ORG_ID
```

## Phase 3: link billing and set default project

```bash
gcloud billing projects link "$PROJECT_ID" --billing-account="$BILLING_ACCOUNT"
gcloud config set project "$PROJECT_ID"
gcloud billing projects describe "$PROJECT_ID"   # expect billingEnabled: true
```

(Note: `gcloud billing projects describe` is GA. The older `gcloud beta billing ...` form requires `gcloud components install beta`.)

## Phase 4: enable APIs

```bash
gcloud services enable \
  bigquery.googleapis.com \
  bigquerystorage.googleapis.com \
  run.googleapis.com \
  cloudscheduler.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  iam.googleapis.com \
  cloudresourcemanager.googleapis.com \
  logging.googleapis.com
```

Stack rationale: BigQuery (warehouse) + Cloud Run (ingestion jobs) + Scheduler (cron) + Artifact Registry (Docker images) + Secret Manager (Plato + Xero tokens) + Cloud Build (deploy from source) + Logging (debug ingestion runs).

## Phase 5: create BigQuery datasets

All in `asia-southeast1` so they can be joined without cross-region surcharges.

```bash
bq --location="$REGION" mk -d --description "Raw landed data from Plato"   "${PROJECT_ID}:raw_plato"
bq --location="$REGION" mk -d --description "Raw landed data from Xero"    "${PROJECT_ID}:raw_xero"
bq --location="$REGION" mk -d --description "Raw landed data from GSuite" "${PROJECT_ID}:raw_gsuite"
bq --location="$REGION" mk -d --description "Cleaned/typed staging layer" "${PROJECT_ID}:stg"
bq --location="$REGION" mk -d --description "Star-schema marts (dashboard reads from here)" "${PROJECT_ID}:marts"
```

Verify:
```bash
bq ls --project_id="$PROJECT_ID"
```

Should list: `raw_plato`, `raw_xero`, `raw_gsuite`, `stg`, `marts`.

## Phase 6: ingestion service account + least-privilege roles

One service account that every Cloud Run ingestion job runs as. We will not generate a JSON key for it; Cloud Run uses the SA directly.

```bash
gcloud iam service-accounts create "$SA_NAME" \
  --display-name="Goji ingestion (Plato/Xero -> BigQuery)"

for ROLE in \
  roles/bigquery.dataEditor \
  roles/bigquery.jobUser \
  roles/secretmanager.secretAccessor \
  roles/run.invoker \
  roles/logging.logWriter
do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="$ROLE"
done
```

Why these five:
- `bigquery.dataEditor` writes rows into raw_*/stg/marts.
- `bigquery.jobUser` runs the load/query jobs.
- `secretmanager.secretAccessor` reads API tokens at runtime.
- `run.invoker` lets Cloud Scheduler call Cloud Run jobs as this SA.
- `logging.logWriter` writes structured logs so we can debug failed runs.

## Phase 7: store the Plato bearer token in Secret Manager

```bash
# If PLATO_API_KEY is already in your shell:
printf "%s" "$PLATO_API_KEY" | gcloud secrets create plato-api-key \
  --data-file=- --replication-policy=automatic

# Or, interactive paste:
# gcloud secrets create plato-api-key --replication-policy=automatic
# gcloud secrets versions add plato-api-key --data-file=- < <(printf "%s" "PASTE_TOKEN_HERE")
```

Grant the ingestion SA access to just this secret (in addition to the project-level role above, this scopes it explicitly):

```bash
gcloud secrets add-iam-policy-binding plato-api-key \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/secretmanager.secretAccessor"
```

Verify:
```bash
gcloud secrets list
gcloud secrets versions list plato-api-key
```

---

## Done state

After all seven phases:

- Project `goji-bi` exists, billing-enabled against `015B7E-11A7E1-397B4D`.
- 10 APIs enabled (BigQuery, Cloud Run, Scheduler, Build, Artifact Registry, Secret Manager, IAM, Resource Manager, Logging, BQ Storage).
- 5 BigQuery datasets in `asia-southeast1`: `raw_plato`, `raw_xero`, `raw_gsuite`, `stg`, `marts`.
- 1 ingestion service account with 5 least-privilege roles.
- 1 secret (`plato-api-key`) accessible by that SA.

## Next step (separate session)

Write the first Cloud Run job: Plato `/invoices` paginated dump into `raw_plato.invoices_raw`, scheduled hourly by Cloud Scheduler. Will live in `scripts/ingestion/plato_invoices/` and be deployed with `gcloud run deploy --source .` using the ingestion SA.
