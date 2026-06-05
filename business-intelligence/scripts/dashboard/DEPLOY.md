# Dashboard deploy notes

Live: <https://dashboard.gojiphysio.com>
Cloud Run URL: <https://goji-dashboard-277737358846.asia-southeast1.run.app>

Single Cloud Run service, gated by HTTP Basic Auth, queries BigQuery on each
page load with a 5-minute in-process cache.

## Two audiences, one service

- **Founders** (`DASHBOARD_USER`/`DASHBOARD_PASS`) — full access: the financial
  dashboard (`/`, `/api/data`, P&L, commission) **and** the admin section.
- **Front-desk staff** (`STAFF_USER`/`STAFF_PASS`) — the **admin section only**
  (`/admin`, `/api/admin/*`): the patient retention worklist. A staff
  credential returns 401 on every financial route, so it can never reach
  financial data. Role gating lives in `require_roles(...)` in `app.py`.

## Architecture

- **Cloud Run service** `goji-dashboard` in `asia-southeast1`.
- Runs as `dashboard-sa@goji-bi.iam.gserviceaccount.com` — read-only on BQ,
  **plus write on the single follow-up table** (see below).
- Reads `DASHBOARD_USER`/`DASHBOARD_PASS` and `STAFF_USER`/`STAFF_PASS` from
  Secret Manager at boot (`dashboard-user`, `dashboard-pass`, `dashboard-staff-user`,
  `dashboard-staff-pass`).
- `PLATO_API_KEY` (secret `plato-api-key`) is mounted so the admin worklist can
  hydrate patient name + phone **live** from Plato. These are never written to
  BQ — the warehouse stays PII-free. Without the key, the worklist degrades to
  the PII-safe initials from `dim_patient`.
- Container: `python:3.12-slim` + Flask + gunicorn + google-cloud-bigquery.
- One revision keeps 0..3 instances; concurrency 20; memory 512Mi.

## Files

- `app.py` — Flask app, BQ queries, role-based basic-auth, cache.
- `template.html` — founder dashboard markup. Contains `__DATA_PLACEHOLDER__`.
- `admin.html` — staff admin (retention worklist) markup.
- `Dockerfile`, `requirements.txt`, `.dockerignore` — Cloud Run build inputs.

## One-time setup for the admin section

Create the staff secrets:

    python3 -c "import secrets; print(secrets.token_urlsafe(18))" | \
      gcloud secrets create dashboard-staff-pass --data-file=- --project=goji-bi
    printf "frontdesk" | \
      gcloud secrets create dashboard-staff-user --data-file=- --project=goji-bi

Deploy the follow-up state objects (idempotent; the events table is
`CREATE TABLE IF NOT EXISTS`, so it won't clobber data on re-run):

    cd ../sql && ./deploy_all.sh

Grant the dashboard SA write on **only** the follow-up table (so it can append
"contacted/snoozed/dismissed" events; everything else stays read-only):

    bq add-iam-policy-binding \
      --member="serviceAccount:dashboard-sa@goji-bi.iam.gserviceaccount.com" \
      --role="roles/bigquery.dataEditor" \
      goji-bi:marts.patient_followup_events

## Read the password

    gcloud secrets versions access latest --secret=dashboard-pass --project=goji-bi
    gcloud secrets versions access latest --secret=dashboard-user --project=goji-bi

## Rotate the password

    NEW_PASS=$(python3 -c "import secrets; print(secrets.token_urlsafe(18))")
    printf "%s" "$NEW_PASS" | gcloud secrets versions add dashboard-pass --data-file=- --project=goji-bi
    gcloud run services update goji-dashboard --region=asia-southeast1 --project=goji-bi \
      --update-secrets=DASHBOARD_PASS=dashboard-pass:latest
    echo "New password: $NEW_PASS"

(Cloud Run resolves `:latest` at boot; the update bounces a new revision.)

## Redeploy after a code change

    cd scripts/dashboard
    gcloud run deploy goji-dashboard \
      --project=goji-bi --region=asia-southeast1 --source=. \
      --service-account=dashboard-sa@goji-bi.iam.gserviceaccount.com \
      --set-secrets=DASHBOARD_USER=dashboard-user:latest,DASHBOARD_PASS=dashboard-pass:latest,STAFF_USER=dashboard-staff-user:latest,STAFF_PASS=dashboard-staff-pass:latest,PLATO_API_KEY=plato-api-key:latest \
      --set-env-vars=GCP_PROJECT=goji-bi,CACHE_TTL_SECONDS=300,PLATO_DB=gojihealth \
      --quiet

The invoice-doctor mismatch alert is fed by `marts.fct_invoice_doctor_mismatches`,
a SQL view over `stg.appointments` (populated by the `plato-appointments-ingest`
Cloud Run Job every 15 minutes) — the financial dashboard reads it from BQ, not
Plato. `PLATO_API_KEY` is back on the service for one reason only: the staff
admin worklist hydrates patient name + phone live from Plato at render time
(never persisted).

## Force a cache refresh without redeploying

    curl -X POST -u "$USER:$PASS" https://dashboard.gojiphysio.com/refresh

## Tail logs

    gcloud logging tail 'resource.type=cloud_run_revision AND resource.labels.service_name=goji-dashboard' --project=goji-bi

## Custom domain

`dashboard.gojiphysio.com` is live: a `dashboard` CNAME → `ghs.googlehosted.com.`
on the `gojiphysio.com` zone, with Google's auto-provisioned TLS cert. The
domain mapping lives in Cloud Run.

Verify / inspect:

    dig +short dashboard.gojiphysio.com         # CNAME → ghs.googlehosted.com.
    curl -I https://dashboard.gojiphysio.com/   # 401 (auth required)
    gcloud beta run domain-mappings describe \
      --domain=dashboard.gojiphysio.com \
      --region=asia-southeast1 --project=goji-bi

## What this dashboard shows

Founder dashboard — three pages, all live from BQ:

- **Overview** — KPIs, daily/weekly/monthly trends, per-clinician table,
  discount summary, treatment-mix donuts, cohort table, deferred revenue,
  patient demographics, referral analytics, and the invoice-doctor mismatch alert.
- **P&L** — Singapore-style P&L with revenue/bookings toggle, period selector,
  and XLSX export.
- **Commission** — per-clinician commission calculator over real appointment data.

Staff admin (`/admin`) — patient ops, no financials:

- **Retention worklist** — patients tiered by time since last visit
  (green ≤1wk / yellow >1wk / orange >2wk / red >4wk), excluding anyone with a
  future appointment booked or marked dismissed/snoozed. Front desk can mark
  **contacted / snooze / dismiss**; name + phone are hydrated live from Plato.

## Cost

- Cloud Run: scales to zero. With a few visits a day, well under $1/month.
- BQ: each page load is ~10 cheap queries (~few MB scanned each). Cached
  for 5 minutes so reloads don't multiply that. Should be free-tier-shaped.
- Secret Manager: 6 secret access calls per cold start. Free tier covers it.
