# Goji

Monorepo for **Goji Health Pte. Ltd.** — a women's and family physiotherapy +
fitness clinic in Singapore ([gojiphysio.com](https://gojiphysio.com)).

Each Goji project lives in its own top-level directory. New projects get a new
top-level directory alongside these.

## Projects

| Directory | What it is |
|---|---|
| [`business-intelligence/`](business-intelligence/) | Data pipeline + live analytics dashboard. Ingests Plato clinic data into BigQuery and serves a Cloud Run dashboard at [dashboard.gojiphysio.com](https://dashboard.gojiphysio.com). |
| [`marketing/`](marketing/) | 90-day top-of-funnel marketing campaign: strategy, content engine, partnerships, and design system. Markdown docs. |

## Deploying

Each project is deployed independently — there is no monorepo-wide CI. The
business-intelligence services deploy via manual `gcloud run deploy --source=.`
from their respective subdirectories. See
[`business-intelligence/scripts/dashboard/DEPLOY.md`](business-intelligence/scripts/dashboard/DEPLOY.md)
for the dashboard and each `business-intelligence/scripts/ingestion/*/README.md`
for the ingestion jobs.

> Note: the Google Cloud **project** is named `goji-bi` and is unchanged by this
> repo's layout. References to `goji-bi` in scripts/config are the GCP project
> ID, not this GitHub repo.
