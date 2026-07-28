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
- `POST /api/book` → `{ok, reference}` (409 if the slot was just taken)
- `POST /api/track` → funnel event (fire-and-forget) → `marts.booking_funnel_events`
- `GET /healthcheck`

## How availability works (`availability.py`)
Derived, NOT taken from Plato's hourly `onlineapptbooking/slots` (locked to 60m).
For each clinician's `onlineapptbooking/list` rule (hours, days off, restricted
blocks) minus their real `GET /appointment` bookings (paginated; single-day query
expands recurring), we emit free **30-min** starts where `[t, t+duration]` is
clear. Rules layered on top (`config.py`):
- Cheryl 09:00–17:00 Mon–Fri; Kristy/Claire follow their calendars.
- Clinic-wide `-all-` blocks apply to everyone.
- Lead time follows Plato's `min_days` (1 day ahead — no same-day).
- **Booking window capped at `MAX_ADVANCE_DAYS` (60 days)** — enforced both in
  availability and as an explicit `too_far` guard in `create_booking`; the site
  calendar can't select past it either.
- Home visits: **Cheryl only**, ±30-min travel padding.

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
