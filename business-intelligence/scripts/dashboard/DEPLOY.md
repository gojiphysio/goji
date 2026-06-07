# Dashboard deploy notes

Live:

- Founders / finance: <https://dashboard.gojiphysio.com>  (`APP_MODE=dashboard`)
- Whole team / front desk: <https://frontdesk.gojiphysio.com>  (`APP_MODE=frontdesk`)

Cloud Run URL: <https://goji-dashboard-277737358846.asia-southeast1.run.app>

Both subdomains run the **same container image** (`app.py`), gated by HTTP Basic
Auth, querying BigQuery on each page load with a 5-minute in-process cache. The
only difference is the `APP_MODE` env var, which selects the routes and audience.

## Two subdomains, one codebase

- **`dashboard.*`** (`APP_MODE=dashboard`, default) — the financial dashboard
  (`/`, `/api/data`, P&L, commission) **and** the admin section. Founder-only in
  practice (don't mount staff secrets here if you want it strictly founders).
- **`frontdesk.*`** (`APP_MODE=frontdesk`) — the patient ops portal only. `/`
  redirects to `/admin`; every founder-only financial route returns **404**, so
  no financial data is reachable here even with a founder credential. Used by
  reception **and** clinicians (Plato covers clinician schedule/performance, so
  there is no separate clinician portal).

## Roles

- **Founders** (`DASHBOARD_USER`/`DASHBOARD_PASS`) — skeleton key: full access on
  `dashboard.*`, and on `frontdesk.*` they land on the ops view.
- **Staff** — one or more credential pairs, all mapping to the `staff` role:
  - legacy single pair `STAFF_USER`/`STAFF_PASS` (the shared `frontdesk` login)
  - per-person extras `STAFF_1_USER`/`STAFF_1_PASS`, `STAFF_2_USER`/`STAFF_2_PASS`,
    … (username format `firstnamelastname`, e.g. `claireng`). Add as many as
    there are team members.
  A staff credential returns 401/404 on every financial route. Role gating lives
  in `resolve_role(...)` / `require_roles(...)` in `app.py`.

## Stand up the front desk subdomain

One command from Cloud Shell creates the `goji-frontdesk` service + domain mapping:

    bash business-intelligence/scripts/dashboard/deploy_frontdesk.sh

It reuses the existing secrets. To give people their own logins, mint per-person
secrets and pass them in (see the comments at the top of the script):

    STAFF_SECRETS="STAFF_1_USER=staff-claireng-user:latest,STAFF_1_PASS=staff-claireng-pass:latest" \
      bash business-intelligence/scripts/dashboard/deploy_frontdesk.sh

## Architecture

- **Cloud Run service** `goji-dashboard` in `asia-southeast1`.
- Runs as `dashboard-sa@goji-bi.iam.gserviceaccount.com` — read-only on BQ,
  **plus write on the single follow-up table** (see below).
- Reads `DASHBOARD_USER`/`DASHBOARD_PASS` and `STAFF_USER`/`STAFF_PASS` from
  Secret Manager at boot (`dashboard-user`, `dashboard-pass`, `dashboard-staff-user`,
  `dashboard-staff-pass`).
- The dashboard does **not** call Plato. The admin worklist reads patient name +
  phone from `marts.dim_patient_contact`, written nightly by the
  `plato-patients-ingest` job (the one place that holds patient PII; the
  financial dashboard never reads it).
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

Grant the dashboard SA write on **only** the two append-only event tables (so
it can append "contacted/snoozed/dismissed" follow-up events and appointment
confirmations; everything else stays read-only):

    for t in patient_followup_events appt_confirmation_events; do
      bq add-iam-policy-binding \
        --member="serviceAccount:dashboard-sa@goji-bi.iam.gserviceaccount.com" \
        --role="roles/bigquery.dataEditor" \
        "goji-bi:marts.$t"
    done

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
      --set-secrets=DASHBOARD_USER=dashboard-user:latest,DASHBOARD_PASS=dashboard-pass:latest,STAFF_USER=dashboard-staff-user:latest,STAFF_PASS=dashboard-staff-pass:latest \
      --set-env-vars=GCP_PROJECT=goji-bi,CACHE_TTL_SECONDS=300,APP_MODE=dashboard \
      --quiet

Then redeploy the front desk service from the same code:

    bash business-intelligence/scripts/dashboard/deploy_frontdesk.sh

The dashboard does not call Plato. The invoice-doctor mismatch alert reads
`marts.fct_invoice_doctor_mismatches` (a view over `stg.appointments`,
populated by `plato-appointments-ingest`), and the staff worklist reads patient
name + phone from `marts.dim_patient_contact` (populated by
`plato-patients-ingest`). Both come from BigQuery, so no `PLATO_API_KEY` is
mounted here.

## If a front-desk action can't save (HTTP 500 on dismiss/contacted/snooze/confirm)

The dashboard SA must have **write** access to the relevant append-only table:
`marts.patient_followup_events` (retention worklist) and
`marts.appt_confirmation_events` (call-list confirmations). `deploy_admin.sh`
grants and verifies both, but if you ever see a save error, grant them directly:

    for t in patient_followup_events appt_confirmation_events; do
      bq add-iam-policy-binding \
        --member="serviceAccount:dashboard-sa@goji-bi.iam.gserviceaccount.com" \
        --role="roles/bigquery.dataEditor" \
        "goji-bi:marts.$t"
    done

(or in the Console: BigQuery → goji-bi → marts → <table> → Share → add the SA
as **BigQuery Data Editor**).

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
  **contacted / snooze / dismiss**; name + phone come from BigQuery
  (`dim_patient_contact`), plus a count of patients active in the last 12 months.

## Cost

- Cloud Run: scales to zero. With a few visits a day, well under $1/month.
- BQ: each page load is ~10 cheap queries (~few MB scanned each). Cached
  for 5 minutes so reloads don't multiply that. Should be free-tier-shaped.
- Secret Manager: 6 secret access calls per cold start. Free tier covers it.
