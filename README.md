# Goji Business Intelligence

Business intelligence backend and dashboards for **Goji Health Pte. Ltd.** (Singapore physiotherapy clinic).

The goal: a real-time web dashboard the clinic operator can use to see bookings, recognised revenue, deferred revenue, clinician performance, AR/AP, and the other vitals - editable by drag-and-drop, extensible by prompt.

## Status (2026-05-23)

- [x] Architecture chosen: Plato + Xero + GSuite -> BigQuery -> Looker Studio, with Cloud Run + Cloud Scheduler for ingestion.
- [x] Plato API explored and documented. Bookings vs. recognised revenue model verified against live data.
- [x] Schema designed (`architecture/schema.md`).
- [x] Bookings + recognised revenue + deferred revenue working as a local script.
- [ ] GCP project scaffolded.
- [ ] First ingestion job deployed.
- [ ] BigQuery datasets created and seeded.
- [ ] Looker Studio v1 dashboard.
- [ ] Xero integration.

## Layout

```
.
|-- README.md                  (this file)
|-- architecture/
|   `-- schema.md              The canonical warehouse schema. Read this first.
|-- plato-api-docs/            Local offline snapshot of Plato's developer docs,
|   |-- README.md              indexed and annotated with "Notes for Goji BI"
|   |-- 01-overview.md           sections.
|   |-- 02-api-overview.md
|   |-- ...
|   `-- 13-endpoint-reference.md
`-- scripts/
    |-- plato_probe.py         Hits ~20 endpoints, dumps shapes to probe_output.json.
    |                          One-shot discovery tool.
    `-- plato_week_metrics.py  Last-7-days bookings + recognised revenue + clinician
                               split + deferred revenue snapshot. The closest thing
                               to a working dashboard we have today.
```

## How to run the metrics today

```bash
cd scripts/
pip3 install requests
export PLATO_DB=gojihealth
export PLATO_API_KEY=<your_bearer_token>   # generate in Plato System Setup -> API
python3 plato_week_metrics.py
```

Output is three sections: daily bookings vs recognised totals, a per-clinician breakdown, and a current deferred-revenue snapshot. The same logic will move into BigQuery views once we scaffold the warehouse.

## Key concepts to internalise

**Booking vs. recognised revenue.** The clinic sells multi-session packs. Cash comes in once, revenue is earned across multiple visits. The dashboard must always show both side by side. Schema details: `architecture/schema.md`, section "The booking vs. revenue distinction".

**Plato data quirks confirmed against live data:**

- An "invoice" and a "queue entry" are the same object.
- Session consumption is a new invoice line on a $0 invoice, with `item.others.redeem_from` set to the source pack's invoice id. That line's `redeem_alloc[].value` is the per-session recognised revenue.
- Outstanding packages report includes `pro_rata_left` = Plato's own computation of deferred revenue per pack. We trust this.
- Appointments are keyed to a "calendar", and the calendar's `color` value IS the calendar id. `color -> calendars[].color -> calendars[].doctor -> providers[].given_id`.

## Operational notes

- Plato API key lives in your environment, never in the repo. Use `export` (or a `.envrc`) and rely on `.gitignore` to keep `.env` files out.
- `scripts/probe_output.json` contains real patient names and contact numbers. **Never commit.** `.gitignore` handles this.
- `scripts/plato_swagger.json` is the full live API spec, kept locally so we can browse it without re-fetching. Not PII; gitignore'd anyway because it can be regenerated.

## Next session

We're parking GCP work. When we come back, the path is:
1. Scaffold the `goji-bi` GCP project (BigQuery + Cloud Run + Cloud Scheduler + Secret Manager).
2. Lift `plato_week_metrics.py` logic into a scheduled Cloud Run job writing to `raw.plato_invoice` and friends.
3. Build the first Looker Studio dashboard pointed at `marts.fct_invoice_line` + `fct_service_delivered` + `fct_package_balance`.
