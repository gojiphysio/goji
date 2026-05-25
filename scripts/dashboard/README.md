# Dashboard generator

Single-file dashboard builder. Reads BigQuery, bakes live data into the HTML template, writes a self-contained file you can open or email.

## Files

- `generate.py` - Python script that queries BQ for four preset date ranges (7d / 30d / 90d / All) and renders the dashboard.
- `template.html` - The HTML template. Includes a date range selector, localStorage persistence, and JS that swaps data per range.
- `README.md` - This file.

Output goes to `../../mockups/dashboard_v2.html`.

## Prerequisites

- `bq` CLI installed (you already have it from the GCP setup).
- Authenticated as a Google account with BigQuery read on `goji-bi` (your account works).
- Python 3.9+ (any default macOS Python works, no pip installs needed).

## Run

From this directory:

    python3 generate.py

You'll see progress per range, then a final `Wrote ...` line. Open the output with:

    open ../../mockups/dashboard_v2.html

## What's live vs sample

Live, pulled from BQ each run:

- KPIs (bookings, recognised, active patients, deferred)
- Per-clinician table + chart
- Discount cost + top discounted items
- Treatment-type mix donuts (categories resolved from Plato `given_id` prefix)
- Cohort / LTV table

Sample, illustrative until the source data is ingested:

- Patient demographics (age, gender, condition tags) - needs `/patient` ingestion
- Retention curve - needs longer history
- Upcoming unconfirmed appointments - needs `/appointment` ingestion

## When to re-run

Whenever you want a fresh snapshot. The new ingestion job updates BQ every 30 minutes, so once a day is plenty for a "morning brief" dashboard. Re-running generates new data for all four ranges.

## How the date selector works

Each range is queried separately and its results are embedded in the file. The selector buttons swap which embedded dataset the page displays - no server, no further BQ queries. The selection persists in `localStorage` under the key `goji_dashboard_range`, so reopening the page restores the previous choice.

## Next steps when ready

When always-live data matters more than self-contained file portability, this generator's queries lift directly into Flask handlers, and the template becomes a Jinja template. The Cloud Run + IAP path is sketched out in the chat history but not yet built.
