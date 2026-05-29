# Plato Medical API Docs - Local Snapshot

Captured: 2026-05-23
Source: https://clinic.platomedical.com/developers/1.0/overview

This folder is a local, offline snapshot of the Plato Developer Platform documentation, kept here so we can reference it while building Goji's BI pipeline without re-fetching each time. Each file ends with a "Notes for Goji BI" section interpreting how the topic maps to our build.

## Index

| # | File | Topic |
|---|---|---|
| 01 | [01-overview.md](01-overview.md) | Developer platform overview |
| 02 | [02-api-overview.md](02-api-overview.md) | REST API basics, HTTP verbs, sample requests |
| 03 | [03-authentication.md](03-authentication.md) | Bearer-token auth, API key generation |
| 04 | [04-pagination.md](04-pagination.md) | `current_page` pagination pattern |
| 05 | [05-rate-limiting.md](05-rate-limiting.md) | Rate limits, headers, `modified_since`, best practices |
| 06 | [06-webhooks.md](06-webhooks.md) | Event types, registration flow, retry/failure behaviour |
| 07 | [07-appointments.md](07-appointments.md) | Appointment <-> calendar mapping, available slots |
| 08 | [08-platopay.md](08-platopay.md) | Payment links, card-on-file, charging |
| 09 | [09-invoice-queue.md](09-invoice-queue.md) | Invoice/queue workflow (queue entry == invoice) |
| 10 | [10-apps.md](10-apps.md) | Apps on Plato - private vs public |
| 11 | [11-apps-manifest.md](11-apps-manifest.md) | manifest.json schema, permissions, locations |
| 12 | [12-apps-auth.md](12-apps-auth.md) | App auth via short-lived context token |
| 13 | [13-endpoint-reference.md](13-endpoint-reference.md) | Full Swagger endpoint list (all resources) |

## Live references (re-fetch if you suspect docs have changed)

- Developer portal: https://clinic.platomedical.com/developers/1.0/overview
- Swagger UI: https://clinic.platomedical.com/api/api/documentation
- Swagger JSON spec: https://clinic.platomedical.com/swagger/api.json?basePath=/api/

## TL;DR for the BI build

- **Base URL pattern:** `https://clinic.platomedical.com/api/{db}/{resource}`. Goji's `{db}` will be assigned when the account is provisioned.
- **Auth:** bearer token from admin user (System Setup -> General Settings -> API). Store in GCP Secret Manager.
- **Rate limit:** 20 req/min default, 20 records per page. Use `modified_since` for incremental sync. Watch `x-ratelimit-remaining` header.
- **Pagination:** `current_page` query param. Loop till empty result set.
- **Webhooks:** 5 max per database, must respond 200 in <=3s, must be idempotent, auto-removed after 5 failures in 24h. Available events cover patient, appointment, invoice (incl. finalize), inventory, corporate.
- **Quirk to remember:** in Plato, **queue entry == invoice**. Same object, two viewpoints. And the appointment's `color` field IS the calendar/clinician ID.

## Phase 1 endpoints to wire up first

In rough priority order:

1. `GET /{db}/systemsetup` (resolves codes used everywhere - run once at start of each sync)
2. `GET /{db}/appointment` + `appointment/codes` + `appointment/calendars`
3. `GET /{db}/invoice` + `GET /{db}/payment`
4. `GET /{db}/patient` (PII-handled)
5. `GET /{db}/inventory` (= service/item catalogue)
6. `GET /{db}/queue/status/list` + `GET /{db}/queue`

Phase 2 brings in corporate, contact, adjustment, expense, reports.
