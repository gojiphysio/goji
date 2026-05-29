# Dashboard deploy notes

Live: <https://dashboard.gojiphysio.com>
Cloud Run URL: <https://goji-dashboard-277737358846.asia-southeast1.run.app>

Single Cloud Run service, gated by HTTP Basic Auth, queries BigQuery on each
page load with a 5-minute in-process cache.

## Architecture

- **Cloud Run service** `goji-dashboard` in `asia-southeast1`.
- Runs as `dashboard-sa@goji-bi.iam.gserviceaccount.com` (read-only on BQ).
- Reads `DASHBOARD_USER` / `DASHBOARD_PASS` from Secret Manager at boot
  (`dashboard-user`, `dashboard-pass`).
- Container: `python:3.12-slim` + Flask + gunicorn + google-cloud-bigquery.
- One revision keeps 0..3 instances; concurrency 20; memory 512Mi.

## Files

- `app.py` — Flask app, BQ queries, basic-auth decorator, cache.
- `template.html` — page markup. Contains `__DATA_PLACEHOLDER__`.
- `Dockerfile`, `requirements.txt`, `.dockerignore` — Cloud Run build inputs.

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
      --set-secrets=DASHBOARD_USER=dashboard-user:latest,DASHBOARD_PASS=dashboard-pass:latest \
      --set-env-vars=GCP_PROJECT=goji-bi,CACHE_TTL_SECONDS=300 \
      --quiet

The dashboard's invoice-doctor mismatch alert is fed by `marts.fct_invoice_doctor_mismatches`,
a SQL view over `stg.appointments` (populated by the `plato-appointments-ingest`
Cloud Run Job every 15 minutes). The dashboard service does not call Plato
directly, so it no longer needs `PLATO_API_KEY`.

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

Three pages, all live from BQ:

- **Overview** — KPIs, daily/weekly/monthly trends, per-clinician table,
  discount summary, treatment-mix donuts, cohort table, deferred revenue,
  patient demographics, referral analytics, and the invoice-doctor mismatch alert.
- **P&L** — Singapore-style P&L with revenue/bookings toggle, period selector,
  and XLSX export.
- **Commission** — per-clinician commission calculator over real appointment data.

## Cost

- Cloud Run: scales to zero. With a few visits a day, well under $1/month.
- BQ: each page load is ~10 cheap queries (~few MB scanned each). Cached
  for 5 minutes so reloads don't multiply that. Should be free-tier-shaped.
- Secret Manager: 6 secret access calls per cold start. Free tier covers it.
