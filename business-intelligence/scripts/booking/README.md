# goji-booking

The website's direct-to-Plato booking backend (Cloud Run, `booking.gojiphysio.com`).
Powers the `/book` page on the site: real 30-min availability + appointment
creation, with the Plato key held server-side.

## Why this exists
Plato's own online-booking form is generic and hourly-only. This service lets the
on-brand website form create appointments directly, at 30-min granularity, with
the clinic's real rules — see the plan/validation notes in the repo.

## Endpoints (public, CORS-limited to www.gojiphysio.com)
- `GET /api/availability?service=&date=&clinician=&home=` → `{times, by_clinician, clinicians}`
- `GET /api/availability-summary?service=&month=YYYY-MM&clinician=&focus=&home=` →
  `{available: [dates]}` — which dates in the month have any slot (the website
  calendar's shading + first-free-date auto-pick). One Plato appointments fetch
  covers the month; cached ~5 min (`AVAIL_SUMMARY_CACHE_TTL`).
- `POST /api/book` → `{ok, reference}` (409 if the slot was just taken)
- `POST /api/track` → funnel event (fire-and-forget) → `marts.booking_funnel_events`
  (stages must be in `VALID_STAGES` in `app.py` — unknown stages are dropped;
  keep the website's `FunnelStage` type in `src/lib/booking.ts` in sync)
- `GET /healthcheck` → liveness only ("is the container up"). Never touches Plato.
- `GET /healthcheck/deep` → **readiness**: derives real availability for the next
  14 days. `200 {"ok":true,...}` = a visitor can book; `503` = they can't, with
  `reason` = `derivation_failed` (Plato/derivation threw) or `no_bookable_dates`
  (ran clean, empty calendar). Result cached 60s so probing it can't eat Plato's
  budget. This is what the uptime check watches — plain `/healthcheck` stayed
  green through the 2026-09-01 outage, which is why it exists.

## Monitoring
`setup_monitoring.sh` (re-runnable) provisions a Cloud Monitoring uptime check on
`/healthcheck/deep` every 5 min plus an alert policy emailing
`hello@gojiphysio.com` when more than one probe region fails for 5 minutes.
Runbook for what to do when it fires: `DIAGNOSIS.md`.

## Plato's rate limit — the thing that keeps breaking us
Plato caps at **20 requests/min per API key**, clinic-wide across availability,
summaries and booking writes. `plato.py` paces itself with a token bucket
(`PLATO_RATE_PER_MIN`, default 18, burst 20) instead of discovering the cap via
429s — one 429 costs 7s of retry backoff and still surfaces as a 502 on the form.
Three rules follow from that budget:
- **Never hand a Plato response straight to code that assumes a shape, and never
  cache one you haven't validated.** On 2026-09-01 Plato changed
  `onlineapptbooking/list` from returning the config object to returning a list
  of them, unannounced, and took `/book` down for ~9 hours.
  `_normalise_booking_config()` now accepts both shapes (preferring the `active`
  entry), only something carrying `calendars` is cached, and a failed refresh
  serves the last known-good copy. See `DIAGNOSIS.md`.
- **Fetch the config before the appointments.** The config is one cached call;
  appointments are paginated. Failing after the crawl wastes the budget on a
  request that was never going to succeed.
- **Range fetches cache far longer than single days** (`PLATO_APPTS_RANGE_TTL`,
  5 min vs 20s). A month is 10+ pages; without this, every focus/clinician
  variant of the same month re-pages it.
- **`--max-instances=1` is load-bearing** for the limiter, not just the booking
  locks. Raising it multiplies our request rate by the instance count.

## How availability works (`availability.py`)
Derived, NOT taken from Plato's hourly `onlineapptbooking/slots` (locked to 60m).
For each clinician's `onlineapptbooking/list` rule (hours, days off, restricted
blocks) minus their real `GET /appointment` bookings (paginated), we emit free
**30-min** starts where `[t, t+duration]` is clear. The single-day appointment
fetch retrieves all recurring entries that Plato returns (we do not expand
recurrence rules locally; a future Plato API improvement could pre-expand these).
Rules layered on top (`config.py`):
- Cheryl 09:00–17:00 Mon–Fri; Kristy/Claire follow their calendars.
- Clinic-wide `-all-` blocks apply to everyone.
- Lead time follows Plato's `min_days` (1 day ahead — no same-day).
- **Booking window capped at `MAX_ADVANCE_DAYS` (60 days)** — enforced both in
  availability and as an explicit `too_far` guard in `create_booking`; the site
  calendar can't select past it either.
- Home visits: **Cheryl only**, ±30-min travel padding.
- **One shared reformer** (Camille's Private Pilates, Claire's Clinical Pilates).
  Plato has no resource model, so while any appointment, on any calendar, carries
  Space Requirement `code_Left` = `REFORMER_CODE` (`YS06`, "Reformer needed";
  collected under `REFORMER_KEY` in `availability.py`), the `REFORMER_CLINICIANS`
  (Camille, Claire) are not offered online for **any** service (pilates, physio,
  S&C): any of their sessions could need it. Cheryl and Kristy are unaffected.
  Online Clinical/Private Pilates bookings are stamped with the tag so they block
  the other. Bookings made straight in Plato are not checked on entry but do
  block online slots once tagged. `QWGT` ("Reformer 1/2 session") is ignored.

## How booking works (`booking.py`)
Plato does **not** reject conflicts, so `create_booking` re-derives availability
for the exact slot inside a **per-clinician lock**, then `POST /appointment`
(`connect:true` fires Plato's own customer confirmation). Home visit = 3
appointments (travel/visit/travel), all-or-nothing.

When the patient picks **"Earliest available"** (no explicit clinician — the
default for a new patient), auto-assignment walks `FIRST_AVAILABLE_PRIORITY` in
`config.py` (**Kristy → Claire → Cheryl**) and takes the first clinician who is
free at that slot and offers the chosen sub-type. Availability still decides who
*can* take it; the order only breaks ties — and it keeps Cheryl's diary open for
the work only she covers (scoliosis, home visits). Then `mailer.py` sends two
best-effort emails — the clinic heads-up (hello@) **and** our own on-brand
confirmation to the customer (so it's guaranteed even if Plato's template isn't
sending) — and a `confirmed` funnel event is logged.

> Both emails need the `gmail-app-password` secret (`GMAIL_APP_PASSWORD`); without
> it `mailer.py` logs and skips. The customer still gets Plato's confirmation via
> `connect:true`. If that duplicates our email in practice, drop one after a live
> test (either set `connect:false` or remove `send_customer_booking_email`).

## Config to keep in sync
`config.py` mirrors the website's `src/lib/services.ts` + `clinicians.ts`
(calendar `color`s, doctor codes, service→calendar/type). Source of truth is
Plato's `onlineapptbooking/list`.

## Run / test / deploy
- Tests: `cd scripts && python3 -m booking.test_booking && python3 -m booking.test_availability`
- Probe live availability (read-only): `PLATO_API_KEY=… python3 -m booking.probe_availability 2026-07-18 physiotherapy`
- Deploy: `bash deploy.sh` (see the header — needs `plato-api-key`, optional
  `gmail-app-password`; add `booking_funnel_events` to `deploy_admin.sh` grants first).
