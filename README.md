# Goji Business Intelligence

Business intelligence backend and live dashboard for **Goji Health Pte. Ltd.**
(Singapore physiotherapy clinic).

A real-time web dashboard the clinic operator uses to see bookings, recognised
revenue, deferred revenue, clinician performance, discounts, treatment mix,
patient demographics, and a working P&L — all sourced from Plato and served
from our own warehouse.

## Architecture

```
Plato API
   │  (Cloud Run Jobs, scheduled by Cloud Scheduler)
   ▼
raw_plato.*        ← append-only landings, one row per API object version
   │  (BigQuery views)
   ▼
stg.*              ← typed, deduped, source-shaped
   │
   ▼
marts.*            ← star schema / reporting facts
   │  (queried live per request, 5-min in-process cache)
   ▼
Cloud Run Flask dashboard  ← HTTP Basic Auth
   https://dashboard.gojiphysio.com
```

Everything runs in GCP project `goji-bi`, region `asia-southeast1`. The
dashboard scales to zero and costs well under a few dollars a month.

## What's live today

**Ingestion** — four Cloud Run Jobs land Plato data into `raw_plato.*`:

| Job | Source | Cadence | Notes |
|---|---|---|---|
| `plato-invoices-ingest` | `/invoice` | nightly | filtered by `modified_since` |
| `plato-appointments-ingest` | `/appointment` | every 15 min | filtered by session date window `[-14d, +7d]` |
| `plato-patients-ingest` | `/patient` | nightly | PII-safe (`initial_lastname` only) |
| `plato-contact-ingest` | `/contact` | nightly | referral-source resolution |

**Dashboard** — single Flask service (`scripts/dashboard/app.py`), three pages:

- **Overview** — KPIs (bookings, recognised, active patients, deferred),
  daily/weekly/monthly trends, per-clinician table + chart, discount cost +
  top discounted items, treatment-mix donuts, cohort/LTV table, patient
  demographics, and referral analytics.
- **P&L** — Singapore-style profit & loss with a revenue/bookings toggle,
  selectable period (Last 30D / current cycle / previous cycle / custom), and
  XLSX export.
- **Commission** — per-clinician commission calculator over real appointment
  data, with patient initials.

**Data-quality alert** — the Overview surfaces invoice-doctor mismatches
(invoices whose `doctor` disagrees with the same-day appointment calendar's
clinician), fed by the `marts.fct_invoice_doctor_mismatches` view. See the
cross-reference + correction tooling in `scripts/cross_reference_invoice_doctor.py`
and `scripts/fix_invoice_doctor.py`.

## Layout

```
.
├── README.md                  (this file)
├── architecture/
│   ├── schema.md              Canonical warehouse schema. Read this first.
│   ├── objectives.md          The original six dashboard questions + metric defs.
│   └── gcp_setup.md           GCP project bring-up notes.
├── gcp-setup.sh               Idempotent GCP scaffolding script.
├── plato-api-docs/            Offline snapshot of Plato's developer docs,
│                              annotated with "Notes for Goji BI".
├── claude setup/              Operator-facing guides (dashboard access, glossary).
├── design/                    Brand template + logo assets.
└── scripts/
    ├── dashboard/             The live Cloud Run service (app.py, template.html,
    │                          Dockerfile). DEPLOY.md has redeploy/rotate steps.
    ├── ingestion/             One folder per Cloud Run ingestion Job.
    ├── sql/                   stg + marts BigQuery views (deploy_all.sh).
    ├── cross_reference_invoice_doctor.py  Invoice-doctor mismatch detection.
    ├── fix_invoice_doctor.py              Correction script for mismatches.
    ├── build_clinician_revenue_template.py  XLSX commission template generator.
    ├── data/                  inventory.xlsx — item → category source.
    └── archive/               One-shot probe/discovery scripts (reference only).
```

## Running things

**Deploy a dashboard change** — see `scripts/dashboard/DEPLOY.md` (redeploy,
password rotation, custom-domain DNS, log tailing).

**Deploy a SQL view change:**

```bash
cd scripts/sql && ./deploy_all.sh
```

**Deploy / schedule an ingestion job** — each `scripts/ingestion/*/README.md`
has the `gcloud run jobs deploy` and `gcloud scheduler` commands for that job.

## Key concepts to internalise

**Booking vs. recognised revenue.** The clinic sells multi-session packs. Cash
comes in once; revenue is earned across multiple visits. The dashboard always
shows both side by side. Details: `architecture/schema.md`, section "The booking
vs. revenue distinction".

**Plato data quirks confirmed against live data:**

- An "invoice" and a "queue entry" are the same object.
- Session consumption is a new line on a $0 invoice, with
  `item.others.redeem_from` set to the source pack's invoice id. That line's
  `redeem_alloc[].value` is the per-session recognised revenue.
- The outstanding-packages report includes `pro_rata_left` = Plato's own
  deferred-revenue computation per pack. We trust this.
- Appointments are keyed to a "calendar", and the calendar's `color` value IS
  the calendar id: `color → calendars[].color → calendars[].doctor → providers[].given_id`.
- Provider codes: `PCL` = Cheryl Long (director), `PKN` = Kristy Ng, `PCN` = Claire Ng.

## Operational notes

- The Plato API key lives in Secret Manager (`plato-api-key`), never in the
  repo. The dashboard service no longer needs it — it reads everything from BQ.
- `scripts/probe_output.json` / `probe2_output.json` and `plato_swagger.json`
  contain real patient PII and are gitignored. **Never commit.**
- The dashboard runs read-only as `dashboard-sa@`; ingestion runs as
  `ingestion-sa@`; Cloud Scheduler triggers as `scheduler-sa@`.

## Future objectives

The original six v1 questions (`architecture/objectives.md`) are answered. The
next horizon:

1. **Xero integration → a true P&L.** Today's P&L tab is revenue- and
   commission-driven; real costs (payroll, rent, supplies, payment fees) and
   AR/AP live in Xero. Pull Xero into `raw_xero.*` and join to revenue for a
   real operating-profit picture.
2. **Operational call list (the deferred Q6).** Unconfirmed upcoming
   appointments worth chasing — a PII-bearing operational view for confirmation
   calls. Data and code mappings are ready (`objectives.md` §6); needs a page.
3. **Cancellation / no-show tracking.** Plato hard-deletes cancellations, so
   this needs a Cloud Run HTTPS receiver for the `appointment:delete` webhook.
   Unblocks no-show rate and chair-utilisation metrics.
4. **Package liability aging + expiry.** Surface packs nearing expiry and a
   breakage forecast, so deferred revenue can be aged and chased.
5. **Push a daily morning brief.** Reuse Cloud Scheduler to email/Slack a
   one-page summary so the operator doesn't have to log in to see the vitals.
6. **Generalise the data-quality alerting.** The invoice-doctor mismatch view
   is one integrity check; add others (e.g. $0 non-redemption invoices, missing
   clinician codes, orphaned redemptions) behind the same alert surface.
7. **Deeper retention/cohort analysis.** As history accumulates, the retention
   curve and churn definitions in `objectives.md` §5 become meaningful — revisit
   once there's enough longitudinal data.
