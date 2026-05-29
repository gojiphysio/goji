# Plato contact ingestion job

Cloud Run **Job** that pulls Plato `/contact`, derives a PII-safe shape, and
writes the result into `goji-bi.marts.dim_referral_source`.

Plato's `/contact` endpoint is a small registry of external referral channels
(GPs, specialist clinics, gyms, "Walk-in", online-booking sources). The
`referred_by` field on each patient holds a contact `_id` — **not** a
patient_id, despite the field name. This job is what makes the link
joinable.

## What we keep / what we drop

Kept (and surfaced in BQ):

- `contact_id`     — Plato `_id`
- `name`           — organisation/channel name ("UFIT", "Trinity Women's")
- `person`         — named contact at the channel ("Dr Samantha Yeo") or
                     intake-channel marker ("Online Booking - Instagram")
- `category`       — Plato's free-text label ("OBGYN", "GP", "Spine")
- `source_type`    — derived bucket (`medical` / `partner` / `walk_in` /
                     `online` / `word_of_mouth` / `other`)
- `display_label`  — what the dashboard table renders
- `created_on`     — date the contact record was first created

Dropped at ingest (read once, never persisted):

- `email`, `telephone`, `handphone`, `fax`, `address`, `url`, `notes`

These are professional contact details for partner clinics. They are not used
by any tile and increase the blast radius if BQ access ever leaks; keep the
list tight.

## Derivation rules (`classify_source_type`)

Top to bottom, first match wins:

1. `category` contains `gp` / `obgyn` / `spine` / `ortho` / `paediatr` /
   `lactation` / `physician` / `specialist` / `surgery` / `clinic` →
   **medical**.
2. `name` is "Walk-in" → **walk_in**.
3. `person` contains "Online Booking" → **online**.
4. `name` is "Goji Physio" → **word_of_mouth** (in-house clinician network).
5. Otherwise, if `name` is set → **partner**.
6. Fallback → **other**.

Extend this function (not the dashboard SQL) when new contact patterns appear.

## One-time setup

### 1. Create the marts table

```bash
bq --project_id=goji-bi --location=asia-southeast1 \
  query --use_legacy_sql=false < scripts/ingestion/plato_contact/schema.sql
```

### 2. Deploy the job

From this directory:

```bash
gcloud run jobs deploy plato-contact-ingest \
  --source . \
  --region asia-southeast1 \
  --service-account ingestion-sa@goji-bi.iam.gserviceaccount.com \
  --set-secrets PLATO_API_KEY=plato-api-key:latest \
  --set-env-vars PLATO_DB=gojihealth,BQ_PROJECT=goji-bi,BQ_DATASET=marts,BQ_TABLE=dim_referral_source \
  --max-retries 1 \
  --task-timeout 600s \
  --memory 512Mi
```

The contact list is tiny (under 50 rows in practice) so the timeout is short.

### 3. Seed it

```bash
gcloud run jobs execute plato-contact-ingest --region asia-southeast1 --wait
```

### 4. Schedule (daily)

```bash
gcloud scheduler jobs create http plato-contact-daily \
  --location asia-southeast1 \
  --schedule "5 21 * * *" \
  --time-zone "Asia/Singapore" \
  --uri "https://run.googleapis.com/v2/projects/goji-bi/locations/asia-southeast1/jobs/plato-contact-ingest:run" \
  --http-method POST \
  --oauth-service-account-email "scheduler-sa@goji-bi.iam.gserviceaccount.com"
```

21:05 SGT — five minutes after `plato-patients-daily` (21:00) so the
referral-source dimension is fresh by the time the Patient referrals tile
on the dashboard joins against it.
