# Dashboard

The live Goji operations dashboard — a single Flask service that queries
BigQuery on each request and serves one HTML page behind HTTP Basic Auth.
Runs on Cloud Run; scales to zero.

## Files

- `app.py` — Flask app: BQ queries, the basic-auth decorator, a 5-minute
  in-process cache, the P&L window/XLSX endpoints, and `/refresh`.
- `template.html` — the page markup with a `__DATA_PLACEHOLDER__` that `app.py`
  fills with live data. Three pages: Overview, P&L, Commission.
- `Dockerfile`, `requirements.txt`, `.dockerignore` — Cloud Run build inputs.
- `static/` — brand image served by the page.
- `DEPLOY.md` — redeploy, password rotation, custom-domain DNS, and log tailing.

## Pages

- **Overview** — KPIs, daily/weekly/monthly trends, per-clinician table + chart,
  discount cost + top discounted items, treatment-mix donuts, cohort/LTV table,
  patient demographics, referral analytics, and the invoice-doctor mismatch alert.
- **P&L** — Singapore-style P&L with a revenue/bookings toggle, period selector
  (Last 30D / current cycle / previous cycle / custom), and XLSX export.
- **Commission** — per-clinician commission calculator over real appointment data.

## Run locally

```bash
cd scripts/dashboard
pip3 install -r requirements.txt
DASHBOARD_DEV=1 GCP_PROJECT=goji-bi python3 app.py
```

`DASHBOARD_DEV=1` enables the Flask reloader and persists BQ results to
`.cache/` so restarts don't re-hit BigQuery. You need Application Default
Credentials with BQ read on `goji-bi` (your `gcloud auth application-default
login` account works).

## Deploy / operate

See `DEPLOY.md` for the `gcloud run deploy` command, password rotation,
cache-refresh, log tailing, and the custom-domain DNS step.
