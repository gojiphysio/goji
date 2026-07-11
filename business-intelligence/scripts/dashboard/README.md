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
  that `app.py` fills with live data. Four pages: Overview, P&L, Commission,
  Marketing.
- `admin.html` — the staff admin page: today's schedule, the reminder-call
  list, package alerts, and the patient retention worklist.
- `tests/` — pytest unit tests for the role boundary and the actionability rule.
- `Dockerfile`, `requirements.txt`, `.dockerignore` — Cloud Run build inputs.
- `static/` — brand image served by the page.
- `DEPLOY.md` — redeploy, password rotation, custom-domain DNS, and log tailing.

## Pages

Founder dashboard (`dashboard.gojiphysio.com`, `/`):

- **Overview** — KPIs, daily/weekly/monthly trends, per-clinician table + chart,
  discount cost + top discounted items, treatment-mix donuts, cohort/LTV table,
  patient demographics, referral analytics, and the invoice-doctor mismatch alert.
- **P&L** — Singapore-style P&L with a revenue/bookings toggle, period selector
  (Last 30D / current cycle / previous cycle / custom), and XLSX export.
- **Commission** — per-clinician commission calculator over real appointment data.
- **Marketing** — marketing-lens view: north-star KPIs and acquisition live from
  BQ; channel leading indicators (Instagram, GBP, website, paid) as WIP
  placeholders pending integrations; delivery-lane mix + ICP/clinical-focus; and
  a referral-source breakdown (Plato attribution is coarse).

Front Desk portal (`frontdesk.gojiphysio.com`, served at `/`, no financials;
the legacy `/admin` path redirects to `/`) — three tabs, the worklists Plato
doesn't track (Today's schedule / call list were removed: they mirrored Plato's
own calendar, which the team uses directly):

- **Leads** — inbound WhatsApp/Instagram/etc. inquiries tracked through the
  acquisition funnel (`inquiry → qualified → booked → won`, or `lost` + reason),
  with a capture form and a funnel summary (inquiries, open, won, lost, close
  rate). "Won" = the lead became a patient/customer (first visit), **not**
  "bought a package". Writes `marts.lead_events` — the single source of truth for
  inbound inquiries.
- **Package alerts** — patients with ≤2 prepaid sessions left
  (`marts.fct_package_balance`), most urgent (0) first, for renewal calls.
- **Follow-ups** — patients tiered by time since last visit
  (green ≤1wk / yellow >1wk / orange >2wk / red >4wk), with the front desk's
  contacted/snooze/dismiss actions and a Dismissed tab. Patients with a future
  appointment booked are excluded; a header line shows patients active in the
  last 12 months.

Name + phone everywhere come from BigQuery (`marts.dim_patient_contact`,
written by `plato-patients-ingest`) and are shown to the front desk only —
never stored on the financial dashboard.

## Run locally

```bash
cd scripts/dashboard
pip3 install -r requirements.txt
DASHBOARD_DEV=1 GCP_PROJECT=goji-bi \
  DASHBOARD_USER=founder DASHBOARD_PASS=pw \
  STAFF_USER=frontdesk STAFF_PASS=pw \
  python3 app.py
```

`DASHBOARD_DEV=1` enables the Flask reloader and persists BQ results to
`.cache/` so restarts don't re-hit BigQuery. You need Application Default
Credentials with BQ read on `goji-bi` (your `gcloud auth application-default
login` account works). Names/phones come from `marts.dim_patient_contact`; if
that table is empty (ingest job hasn't run), the worklist shows PII-safe
initials instead.

## Test

```bash
cd scripts/dashboard
python3 -m pytest tests/ -q
```

## Deploy / operate

See `DEPLOY.md` for the `gcloud run deploy` command, password rotation,
cache-refresh, log tailing, and the custom-domain DNS step.
