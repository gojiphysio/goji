# Goji Dashboard - Login Details

A live operations dashboard with bookings, recognised revenue, clinician
breakdowns, treatment mix, cohorts, and deferred revenue. Refreshes from
BigQuery every 5 minutes.

## URL

While DNS is still propagating:
<https://goji-dashboard-277737358846.asia-southeast1.run.app>

Once DNS is wired up (1-30 min after adding the CNAME):
<https://dashboard.gojiphysio.com>

## Login

The browser will pop up a small login box the first time. Most browsers
remember it after that.

- **User:** `goji`
- **Password:** ask Charles, or run `gcloud secrets versions access latest --secret=dashboard-pass --project=goji-bi`

## What's on the page

- Top KPIs: bookings, recognised revenue, active patients, visits.
- Range selector: 7 days / 30 days / 90 days / all time.
- Per-clinician table.
- Discount cost summary.
- Treatment-mix donut.
- Cohort table (LTV, repeat visits).
- Deferred revenue snapshot.

## When numbers look stale

- Ingestion runs from Plato into BQ every 30 minutes.
- The dashboard caches each page for 5 minutes.
- So worst case it's 35 minutes behind reality. If you need fresher
  data than that, hit refresh in the browser after the 5-minute window.

## When something looks wrong

Tell Charles. Likely it's either:
- A data quirk (Plato classifies sessions in subtle ways - we sometimes
  discover edge cases when real numbers hit the dashboard for the first time).
- A bug in the query logic (still v1 of this thing).
- The ingestion fell behind (rare).
