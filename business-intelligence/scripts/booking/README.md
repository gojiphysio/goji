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

### Recurring + multi-day blocks (`recurrence.py`) — and why the sweep is background-only
The Plato **calendar is the source of truth**: if an event exists on it, that time
is unavailable. Two kinds of event are invisible to the plain single-day
`GET /appointment` query, because it filters by each row's stored `starttime`:
- **Recurring** blocks/appointments — Plato stores a series as ONE row dated at
  its FIRST occurrence with a `recur` rule, and does NOT expand future instances
  (e.g. Kristy off **alternate** Wednesdays — a biweekly block).
- **Multi-day** blocks that began before the queried day.

> Recurring unavailability **cannot** be expressed as an `onlineapptbooking`
> `restricted_block` when it's biweekly/irregular (those are every-week only), so
> the calendar event is the only source — hence this expansion is required.

So availability overlays a **broad look-back sweep** (`appointments_broad`,
`[today-RECUR_LOOKBACK_DAYS, today+MAX_ADVANCE_DAYS]`): it expands `recur` rules
onto the queried day (`recurrence.recurs_on`) and adds multi-day spanners, on top
of the fresh per-day fetch.

**This sweep is many pages, and Plato's limit is ~20 req/min. Running it on the
request path once took the booking form down** (it 429'd and starved the per-day
fetches). So it is engineered to be impossible to repeat:
- **Background only.** `appointments_broad` NEVER fetches on the caller's thread —
  it returns the cached rows, or an **empty list on a cold instance**, and kicks
  off a single background refresh. The interactive path never blocks on it.
- **Gently paced.** The refresher pages with `BROAD_PAGE_SLEEP_S` (~5s) so it
  stays well under the rate limit and leaves budget for per-day fetches.
- **Best-effort.** The overlay is wrapped so any failure is swallowed — it can
  only ever ADD blocks, never break availability. Cached `BROAD_TTL_S` (30m);
  `warm_broad` primes it at startup.

`recur` shape: `{"days":["WE"],"freq":2,"interval":2,"until":YYYYMMDD,"ex":[...]}`
(weekly cadence, `interval` = every N weeks). Bias: over-block, never under-block.

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
- Probe live availability (read-only): `PLATO_API_KEY=… python3 -m booking.probe_availability 2026-07-18 physiotherapy`
- Deploy: `bash deploy.sh` (see the header — needs `plato-api-key`, optional
  `gmail-app-password`; add `booking_funnel_events` to `deploy_admin.sh` grants first).
