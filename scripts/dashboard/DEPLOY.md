# Dashboard deploy notes

Live: <https://goji-dashboard-277737358846.asia-southeast1.run.app>
Custom domain (pending DNS): <https://dashboard.gojiphysio.com>

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
- `template.html` — shared with `generate.py`. Contains `__DATA_PLACEHOLDER__`.
- `Dockerfile`, `requirements.txt`, `.dockerignore` — Cloud Run build inputs.
- `generate.py` — local one-shot generator (uses `bq` CLI), unchanged.

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
      --set-secrets=DASHBOARD_USER=dashboard-user:latest,DASHBOARD_PASS=dashboard-pass:latest,PLATO_API_KEY=plato-api-key:latest \
      --set-env-vars=GCP_PROJECT=goji-bi,CACHE_TTL_SECONDS=300 \
      --quiet

The dashboard cross-references invoice.doctor against the same-day appointment
calendar via Plato's API on each cache miss (every 5 min by default). Without
`PLATO_API_KEY` the "Provider attribution alerts" section degrades to a
"not configured" notice — the rest of the dashboard still works.
`dashboard-sa` needs `secretmanager.secretAccessor` on the `plato-api-key`
secret; grant once with:

    gcloud secrets add-iam-policy-binding plato-api-key --project=goji-bi \
      --member=serviceAccount:dashboard-sa@goji-bi.iam.gserviceaccount.com \
      --role=roles/secretmanager.secretAccessor

## Force a cache refresh without redeploying

    curl -X POST -u "$USER:$PASS" https://dashboard.gojiphysio.com/refresh

## Tail logs

    gcloud logging tail 'resource.type=cloud_run_revision AND resource.labels.service_name=goji-dashboard' --project=goji-bi

## Custom domain — finish the DNS step

The domain mapping is already created in Cloud Run. To finish:

1. Find where DNS for `gojiphysio.com` is managed. The nameservers are
   `ns-cloud-a*.googledomains.com`, so it's either Google Domains
   (now Squarespace) or Cloud DNS.

2. Add this record on the `gojiphysio.com` zone:

       host:  dashboard
       type:  CNAME
       value: ghs.googlehosted.com.
       ttl:   300

3. Once DNS propagates, Google auto-provisions a TLS cert (takes 5-30 min).
   Verify:

       dig +short dashboard.gojiphysio.com    # should return CNAME
       curl -I https://dashboard.gojiphysio.com/   # should be 401 (auth required)

   Status of cert provisioning:

       gcloud beta run domain-mappings describe \
         --domain=dashboard.gojiphysio.com \
         --region=asia-southeast1 --project=goji-bi

## What this dashboard shows

Same content as `generate.py`'s output (the v2 layout) but live from BQ:
KPIs, daily/weekly/monthly trends, per-clinician table, discount summary,
treatment-mix donuts, cohort table, deferred revenue.

**Not yet ported** to the live server: the v3 design (P&L tab, Commission
calculator, true-discount-cost tile with per-SKU breakdown). Those still
live as a static mockup in `mockups/dashboard_v3_sandbox.html` with
hand-pasted numbers — a follow-up port should add the new tile shapes to
`app.py` and replace `template.html` with the v3 markup.

## Cost

- Cloud Run: scales to zero. With a few visits a day, well under $1/month.
- BQ: each page load is ~10 cheap queries (~few MB scanned each). Cached
  for 5 minutes so reloads don't multiply that. Should be free-tier-shaped.
- Secret Manager: 6 secret access calls per cold start. Free tier covers it.
