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
blocks) minus their real `GET /appointment` bookings, we emit free **30-min**
starts where `[t, t+duration]` is clear. Rules layered on top (`config.py`):
- Cheryl 09:00–17:00 Mon–Fri; Kristy/Claire follow their calendars.
- Clinic-wide `-all-` blocks apply to everyone.
- Lead time follows Plato's `min_days` (1 day ahead — no same-day).
- **Booking window capped at `MAX_ADVANCE_DAYS` (60 days)** — enforced both in
  availability and as an explicit `too_far` guard in `create_booking`; the site
  calendar can't select past it either.
- Home visits: **Cheryl only**, ±30-min travel padding.

### Recurring + multi-day blocks (`recurrence.py`) — do not remove
**Plato does NOT expand recurrences.** `GET /appointment?start_date&end_date`
filters by each row's stored `starttime`, and a recurring series is a **single
row dated at its first occurrence** carrying a `recur` rule (verified against live
data — no per-instance rows exist). So a naive single-day query is blind to any
recurring block/appointment (or multi-day block) that *began on an earlier date*,
and would offer a slot that's actually taken — the clinic hit exactly this (a
website booking landed inside a weekly Wednesday block).

So availability uses **two** appointment fetches:
1. **Per-day** (`appointments`, 20s TTL) — fresh same-day bookings, for conflict
   detection of the common case.
2. **Broad look-back sweep** (`appointments_broad`, `[today-RECUR_LOOKBACK_DAYS,
   today+MAX_ADVANCE_DAYS]`) — from it we expand `recur` rules onto the queried
   day (`recurrence.recurs_on`, weekly cadence + `interval`/`until`/`ex`) and add
   multi-day blocks that span it. It's many pages and slow-changing, so it's
   cached `BROAD_TTL_S` (15m) and served **stale-while-revalidate** (only a cold
   instance blocks; `plato.warm_broad` primes it at startup).

`recur` shape: `{"days":["WE"],"freq":2,"interval":1,"until":YYYYMMDD,"ex":[...]}`.
Only weekly cadence is modelled (100% of live rules); the bias is to over-block
rather than under-block, since a missed block is a double-booking.

## How booking works (`booking.py`)
Plato does **not** reject conflicts, so `create_booking` re-derives availability
for the exact slot inside a **per-clinician lock**, then `POST /appointment`
(`connect:true` fires Plato's own customer confirmation). Home visit = 3
appointments (travel/visit/travel), all-or-nothing. Then `mailer.py` sends two
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
  - **CI runs these on every push to `main` and a failure blocks the deploy** —
    a red booking test means nothing ships. Keep the suite green.
  - **Any test that uses a fixed date MUST pass an explicit `now=`** to
    `derive_availability` / `create_booking`. Otherwise `now` defaults to the real
    calendar date, and once real time passes the hardcoded test date it reads as
    a past booking and returns no slots — the test "time-bombs" (green in CI today,
    red weeks later, and it takes the deploy down with it). Pin `now` to the day
    before the test date (see `NOW` in both test files).
- Probe live availability (read-only): `PLATO_API_KEY=… python3 -m booking.probe_availability 2026-07-18 physiotherapy`
- Deploy: `bash deploy.sh` (see the header — needs `plato-api-key`, optional
  `gmail-app-password`; add `booking_funnel_events` to `deploy_admin.sh` grants first).
