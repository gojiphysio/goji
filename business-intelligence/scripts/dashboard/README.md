# Dashboard

The live Goji dashboards — a single Flask service that queries BigQuery on each
request and serves HTML pages behind HTTP Basic Auth. Runs on Cloud Run; scales
to zero. Two role-gated audiences: **founders** (financials) and **front-desk
staff** (patient ops only).

## Files

- `app.py` — Flask app: BQ queries, role-based basic-auth, a 5-minute
  in-process cache, the P&L window/XLSX endpoints, the admin retention
  endpoints, and `/refresh`.
- `template.html` — the founder dashboard markup with a `__DATA_PLACEHOLDER__`
  that `app.py` fills with live data. Three pages: Overview, P&L, Commission.
- `admin.html` — the staff admin page: the patient retention worklist.
- `tests/` — pytest unit tests for the role boundary, the actionability rule,
  and Plato name/phone extraction.
- `Dockerfile`, `requirements.txt`, `.dockerignore` — Cloud Run build inputs.
- `static/` — brand image served by the page.
- `DEPLOY.md` — redeploy, password rotation, custom-domain DNS, and log tailing.

## Pages

Founder dashboard (`/`):

- **Overview** — KPIs, daily/weekly/monthly trends, per-clinician table + chart,
  discount cost + top discounted items, treatment-mix donuts, cohort/LTV table,
  patient demographics, referral analytics, and the invoice-doctor mismatch alert.
- **P&L** — Singapore-style P&L with a revenue/bookings toggle, period selector
  (Last 30D / current cycle / previous cycle / custom), and XLSX export.
- **Commission** — per-clinician commission calculator over real appointment data.

Staff admin (`/admin`, no financials):

- **Retention worklist** — patients tiered by time since last visit
  (green ≤1wk / yellow >1wk / orange >2wk / red >4wk), with the front desk's
  contacted/snooze/dismiss actions. Patients with a future appointment booked
  are excluded. Name + phone are hydrated live from Plato and never stored.

## Run locally

```bash
cd scripts/dashboard
pip3 install -r requirements.txt
DASHBOARD_DEV=1 GCP_PROJECT=goji-bi \
  DASHBOARD_USER=founder DASHBOARD_PASS=pw \
  STAFF_USER=frontdesk STAFF_PASS=pw \
  PLATO_API_KEY=... PLATO_DB=gojihealth \
  python3 app.py
```

`DASHBOARD_DEV=1` enables the Flask reloader and persists BQ results to
`.cache/` so restarts don't re-hit BigQuery. You need Application Default
Credentials with BQ read on `goji-bi` (your `gcloud auth application-default
login` account works). `PLATO_API_KEY` is optional locally — without it the
worklist shows PII-safe initials instead of full name + phone.

## Test

```bash
cd scripts/dashboard
python3 -m pytest tests/ -q
```

## Deploy / operate

See `DEPLOY.md` for the `gcloud run deploy` command, password rotation,
cache-refresh, log tailing, and the custom-domain DNS step.
