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
- `POST /api/book` → `{ok, reference}` (409 if the slot was just taken; 429
  `rate_limited` past 2 bookings per phone or email/day, in-memory since we run
  one instance; no per-IP limit, since SG mobile carriers share IPs and Turnstile
  stops scripts; names/notes with markup are
  refused as `validation`. Added after a scanner booked twice on 2026-11-12).
  Before any Plato call it also runs the **bot check** (below); a fail is
  `400 bot_check`, logged as `book_error` with detail `bot_<reason>`
- `POST /api/track` → funnel event (fire-and-forget) → `marts.booking_funnel_events`
  (stages must be in `VALID_STAGES` in `app.py` — unknown stages are dropped;
  keep the website's `FunnelStage` type in `src/lib/booking.ts` in sync)
- `POST /internal/refresh-snapshot` → re-pages the bookable window into the
  availability snapshot (below). Hit by Cloud Scheduler every 5 min; public but
  self-throttled to one Plato crawl per `SNAPSHOT_MIN_INTERVAL` (240s).
- `POST /internal/book` → booking on behalf of the WhatsApp assistant
  (`X-Internal-Token`; see **WhatsApp assistant** below).
- `GET /healthcheck` → liveness only ("is the container up"). Never touches Plato.
- `GET /healthcheck/deep` → **readiness**: derives real availability for the next
  14 days. `200 {"ok":true,...}` = a visitor can book; `503` = they can't, with
  `reason` = `derivation_failed` (Plato/derivation threw), `no_bookable_dates`
  (ran clean, empty calendar) or `snapshot_stale` (the 5-min refresh has
  stopped; clicks are back on live Plato reads). Result cached 60s so probing it can't eat Plato's
  budget. This is what the uptime check watches — plain `/healthcheck` stayed
  green through the 2026-09-01 outage, which is why it exists.

## Bot check on `/api/book`
The limits cap how much a bot can book; the bot check stops it booking at all.
`_bot_reason()` in `app.py`, cheapest first:
- **Honeypot** `company_url`: a hidden field on the form. Filled = script.
- **Fill time** `elapsed_ms` < `BOOK_MIN_FILL_MS` (3000) = script. Client-reported,
  so it only stops naive bots; a missing value is let through (old open tabs).
- **Cloudflare Turnstile** (free): when `TURNSTILE_SECRET` is set, the form's
  token is required and verified with Cloudflare. This is the only layer a direct
  API caller can't fake. If Cloudflare is unreachable the booking goes through
  (an outage there must not close the form; the limits still apply).

**Turning Turnstile on.** The widget's site key is public and lives in
`marketing/website/src/lib/booking.ts`, so the live form shows the widget once
that build ships. The backend only enforces it once `TURNSTILE_SECRET` is
mounted. The order matters: the site goes live with the widget first, or every
booking is refused.
1. `printf '%s' '<secret key>' | gcloud secrets create turnstile-secret --data-file=- --project goji-bi`
   then `gcloud secrets add-iam-policy-binding turnstile-secret --project goji-bi
   --member serviceAccount:dashboard-sa@goji-bi.iam.gserviceaccount.com
   --role roles/secretmanager.secretAccessor`.
2. Once the site with the widget is live, add `,TURNSTILE_SECRET=turnstile-secret:latest`
   to `--set-secrets` in **both** `deploy.sh` and `.github/workflows/deploy-booking.yml`
   and merge. Don't set it by hand on the service: the next deploy's flags drop it.
3. Check the funnel for `book_error` / `bot_captcha_*` the next day.
Widget settings (hostnames, mode) are in the Cloudflare dashboard → Turnstile.
To rotate the secret, add a new version of `turnstile-secret` and redeploy.

## WhatsApp assistant (`/internal/book` + booking-confirmed callback)
The assistant (`goji-wa-agent`, its own Cloud Run service, `scripts/wa_agent/`)
books through `POST /internal/book`, the same `create_booking` as `/api/book`.
- **Auth:** header `X-Internal-Token` must equal `INTERNAL_TOKEN` (Secret Manager
  `wa-agent-internal-token`, shared with the assistant). Unset → `404` (the route
  doesn't exist); wrong/missing → `403`.
- **Body:** `{service, date: "YYYY-MM-DD", time: "HH:MM", format: "clinic"|"home",
  name, phone, email?, clinician_id?, physio_focus?, variant?, address? (home),
  notes?, session_id?, source: "whatsapp", dry_run: bool}`. `source` other than
  `whatsapp` and a non-boolean `dry_run` (e.g. `"false"`) are `400 invalid`.
- **Differs from `/api/book`:** no bot check (honeypot/fill time/Turnstile; the
  token replaces it); **email optional** (owner decision: WhatsApp bookings
  needn't give one; the website still must). No email → Plato gets no address and
  `connect:false` (no portal invite), no customer email; the admin email still
  goes, marked "Booked via WhatsApp assistant". The Plato note says "Booked via
  WhatsApp assistant." The per-contact daily limit is shared with the website.
- **Response:** `200 {ok, reference, clinician_name, service, date, time, dry_run}`;
  errors `{ok:false, error, code}`: `400`, `409 slot_taken`, `429 rate_limited`,
  `502 plato_error`.
- **`dry_run: true`** runs every check, the limit and the locked fresh
  availability re-check (so the clinician is really chosen), then stops before
  the Plato write: `reference` is `DRYRUN-XXXXXX`, no emails, no funnel row, no
  callback, doesn't count toward the limit. Use it to test the flow against the
  live calendar without touching it.
- **Funnel:** real bookings log `confirmed` (detail `whatsapp`) and failures
  `book_error` (detail `whatsapp_<code>`) under a `wa-` session id (hashed
  phone + day, or the body's `session_id`). These have no `page_view`, so the
  dashboard's website funnel should filter `session_id LIKE 'wa-%'` out.
- **Callback:** after every real booking (website or WhatsApp; never a dry run),
  if `WA_AGENT_URL` and `INTERNAL_TOKEN` are set, a background thread POSTs
  `{phone, reference, service, date, time, clinician_name, source: "web"|"whatsapp"}`
  to `{WA_AGENT_URL}/internal/booking-confirmed` with `X-Internal-Token` (5s
  timeout; failures are logged and dropped). The assistant matches the phone to
  a chat and acknowledges the booking there. `WA_AGENT_URL` is the repo variable
  `vars.WA_AGENT_URL`; empty disables it.
- **Rules:** any new booking entry point calls `_notify_wa_agent` after success;
  a dry run must never reach `_create_appointments` (`test_internal_book.py`
  runs one against a Plato stub that fails on any write).

**Setup (once, before this deploys):** the deploy mounts the secret
unconditionally, so a missing secret fails the deploy.
```bash
openssl rand -hex 32 | tr -d '\n' | gcloud secrets create wa-agent-internal-token --data-file=- --project goji-bi
gcloud secrets add-iam-policy-binding wa-agent-internal-token --project goji-bi \
  --member serviceAccount:dashboard-sa@goji-bi.iam.gserviceaccount.com \
  --role roles/secretmanager.secretAccessor
```
Then set the repo variable `WA_AGENT_URL` to the assistant's Cloud Run URL.

## Monitoring
`setup_monitoring.sh` (re-runnable) provisions a Cloud Monitoring uptime check on
`/healthcheck/deep` every 5 min plus an alert policy emailing
`hello@gojiphysio.com` when more than one probe region fails for 5 minutes.
Runbook for what to do when it fires: `DIAGNOSIS.md`.

## Plato's rate limit — the thing that keeps breaking us
Plato caps at **20 requests/min per API key**, clinic-wide across availability,
summaries and booking writes. `plato.py` paces itself with a sliding window
(`PLATO_RATE_PER_MIN`, default 18 — never more in any 60s) instead of discovering
the cap via 429s — one 429 costs 7s of retry backoff and still surfaces as a 502
on the form.
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
  5 min vs 20s). A month is ~25 pages; without this, every focus/clinician
  variant of the same month re-pages it.
- **Month paging is bulk work, and interactive calls come first.** It may only use
  the window minus `PLATO_BULK_RESERVE`, is time-boxed (`PLATO_BULK_BUDGET`) and
  resumable (`503 loading`, the browser retries), so a date click never waits on
  it. A day inside a fresh cached month needs no Plato call at all, but the
  booking re-check always passes `fresh=True`. Any new caller that *writes* off a
  read must do the same.
- **The key is shared, so our limiter is not the whole story.** The ingestion
  jobs (`plato-appointments` every 15 min, `plato-invoices` every 30 min, 08-20
  SGT) page Plato on the same key; every 429 in Sep-Oct 2026 landed at :02-:04
  or :32-:34 while they ran, and running out of budget caused all 40 of the
  form's "couldn't load times" errors in Oct 2026. So `get()` feeds Plato's `x-ratelimit-remaining`
  to the limiter (bulk paging stands down at the reserve), a failed day is
  answered from a cached month up to `PLATO_DAY_STALE_AGE` old, and an
  out-of-budget day returns `503 {"error":"loading","retry_after":N}`, which the
  form waits out (up to 30s) instead of showing an error.
- **Visitors read a snapshot, not Plato.** Every 5 min Cloud Scheduler calls
  `/internal/refresh-snapshot`, which pages today..+60 days (~25 pages, bulk
  share) into memory. Date clicks and month shading read it with no Plato call,
  so the shared key running dry can only make times up to ~5 min stale. The
  booking re-check still reads the day live (`fresh=True`), a day we just booked
  on reads live until the next refresh, and past `PLATO_SNAPSHOT_MAX_AGE` (15
  min) everything falls back to the live path above. The scheduler tick also
  keeps the single instance warm. Schedule (once, off the ingest jobs' minutes):
  ```bash
  gcloud scheduler jobs create http booking-snapshot-refresh \
    --location asia-southeast1 --schedule "3-58/5 * * * *" \
    --time-zone "Asia/Singapore" --http-method POST \
    --uri "https://booking.gojiphysio.com/internal/refresh-snapshot" \
    --attempt-deadline 300s
  ```
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
- `CLINICIAN_AVAILABLE_FROM` (`config.py`): a clinician is not offered for any
  service before their start date — for a new starter whose Plato calendar is
  live early (Camille: 2026-11-01). Delete the entry once the date has passed.
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
- Tests: `cd scripts && python -m pytest booking/ -q` (what CI runs)
- Probe live availability (read-only): `PLATO_API_KEY=… python3 -m booking.probe_availability 2026-07-18 physiotherapy`
- Deploy: `bash deploy.sh` (see the header — needs `plato-api-key`,
  `turnstile-secret`, optional `gmail-app-password`; `WA_AGENT_URL=… bash
  deploy.sh` turns on the WhatsApp assistant's route and callback and then also
  needs `wa-agent-internal-token`, same in CI via the `WA_AGENT_URL` repo
  variable; add `booking_funnel_events` to `deploy_admin.sh` grants first).
