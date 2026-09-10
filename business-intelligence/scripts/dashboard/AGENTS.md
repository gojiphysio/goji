# Dashboard — conventions

Flask app (`app.py`) serving one page (`template.html`) from BigQuery, on Cloud
Run. One image, three subdomains via `APP_MODE`: founder dashboard
(`dashboard`), front-desk portal (`frontdesk`), and the public click-to-WhatsApp
redirector (`links` → `go.gojiphysio.com/<slug>`, redirects only, no UI/auth).
See `DEPLOY.md`.

## Design philosophy
- **Glanceable headline metrics.** Each card answers a question at a glance or in
  a team discussion — a number + trend. **No big tables, no per-post drilldowns;**
  deep exploration belongs in the source platform (Instagram, Search Console, GBP).

## UI
- **Reuse the trend ticker.** New metric cards show change vs the previous period
  via `renderTrend(id, current, previous, prevStart, prevEnd, opts)` (green ▲ / red ▼ / grey —).
  For a **lower-is-better** metric (cost per booking) pass
  `{ lowerIsBetter: true }`: it flips only the colour, never the arrow or the
  percentage, so the number stays truthful. Don't negate the inputs to fake it —
  that colours correctly but prints the percentage with the wrong sign.
  Back it with `ranges[key].prev_kpis.<metric>`, `ranges[key].prev_start`, and
  `ranges[key].prev_end` from `build_payload()`. The tooltip shows "vs D–D Mon".
- **Mobile rules** (learned the hard way):
  - Tables must scroll, not overflow: `display:block; width:max-content;
    overflow-x:auto` on the table, **and `min-width:0` on any grid/flex item that
    holds a table** (grid items default to `min-width:auto` and won't shrink).
  - **Base CSS must come before `@media` blocks** — equal-specificity rules later
    in source win, so base after a media query silently overrides it.
  - The page-nav pill is `inline-flex` so it hugs its tabs.

## Backend
- **Auth is per-route** via `@require_roles(...)`; there's no global guard. A
  route with **no decorator is public** (e.g. `/healthcheck`, `/r/<slug>`).
  Founder routes are founder-only and 404 on the frontdesk subdomain; **every**
  gated route 404s in `links` mode (that surface is public redirects only, with
  the slug served at the root `/<slug>`).
- **Graceful degradation.** Every `fetch_*` wraps its query in try/except and
  returns a safe empty value, so a not-yet-deployed table never breaks the page
  (see `fetch_link_clicks`, `fetch_leads`).
- **Cache:** `get_payload()` caches `build_payload()` for `CACHE_TTL` (5 min);
  writes pop the cache. `build_payload()` fans queries out in a thread pool —
  add per-range work to `range_jobs[key]` and mirror it in the results assembly.
- **Reporting periods are calendar months** — 1st → last day, derived dynamically so
  28/29/30/31-day months and leap years are handled. Month end is *first of next
  month minus one day* in Python and `new Date(y, m + 1, 0)` in JS. Three helpers
  implement it independently and **must stay in agreement**: `_fiscal_period()` /
  `_prior_fiscal_start()` (projection chart, `app.py`), `payCycleRange()` /
  `prevPayCycleRange()` (P&L selector), and `currentPayCycle()` (commission
  calculator). The `cycle` / `payCycle` names are historical — the dashboard used
  to run a 26th→25th pay cycle; the period is now the plain calendar month.
- **`date.today()` must use SGT.** All `date.today()` / `datetime.now()` calls in
  the backend use `datetime.now(ZoneInfo("Asia/Singapore")).date()` so the date
  boundaries match the clinic's operating timezone, not the UTC Cloud Run host.
- **Appointment times are clinic wall-clock stored as UTC (invariant for anything
  rendering a time from `stg.appointments`).** `start_at` / `end_at` are
  `PARSE_TIMESTAMP`'d as if UTC, but Plato stores naive SGT wall-clock. So to
  display the time, format at **`'UTC'`** — that reads the wall clock back out.
  Converting to `Asia/Singapore` shifts everything by 8 hours. `admin.html`
  compensates client-side (`- 8`); `marts/47_fct_appointment_reminders.sql`
  formats at `'UTC'`; `reminders/test_reminders.py` pins it. Note this is the
  opposite of the `date.today()` rule above — *dates* are clinic-local
  (`appt_date` already is, so key windows on it), *times* are naive.
- **Session grain.** `fct_service_delivered` Part A fans out by `qty` (physical
  session count), not `len(redeem_alloc)`. When a redemption spans two packages
  (cross-package transition), `redeem_alloc` has 2 entries for 1 visit — using
  `qty` keeps the count correct.
- **Writes are append-only event logs** with table-level `dataEditor` grants
  (`record_*` → parameterised DML). **High-frequency / public** writes (e.g. link
  clicks) use the **streaming API** (`insert_rows_json`), not DML — DML is capped
  at 1,500 statements/table/day. New writable table → add it to the grant loops in
  `deploy_admin.sh`, `DEPLOY.md`, and `.github/workflows/deploy-dashboard.yml`.

## Front desk portal (`frontdesk.*`)
- It's the **worklists Plato doesn't track**, not a second calendar. Tabs read
  along the patient's arc: **Welcome** (new patients coming in) → **Follow-ups**
  (win-backs) → **Package alerts** (renewals). A **count** or a first-timer
  **worklist** is fine; don't re-add a Today/schedule/call-list mirror of Plato —
  that was removed precisely to avoid two sources of truth. (The **Leads** tab
  was retired from the UI; its routes + `marts.lead_events` stay so it can be
  revived — see the retired-Leads note below.)
- **Welcome list = upcoming first visits** (`marts.fct_new_patient_welcome`,
  keyed on `appointment_id`; contacted/skipped state in
  `new_patient_welcome_events`). "New" = no prior delivered service **and** no
  prior appointment (linked patients), or no Plato profile yet with the same
  phone/email unseen before (profile-less website/walk-in bookings). Contact is
  hydrated live: **inline `handphone`/`email`/`title` from the appointment
  payload** for profile-less bookings, else `dim_patient_contact` — never stored
  in the mart. Staff→patient outreach uses a direct `wa.me/<patient number>`
  link, **not** the go.gojiphysio.com redirector (that's for tracking *inbound*
  customer taps, not messaging one patient).
- **Ghost appointments (invariant for anything reading `stg.appointments`
  forward).** The `plato_appointments` ingestion is append-only with no deletion
  detection, so a deleted Plato appointment lingers as its last-known version.
  The whole `[today-PAST, today+FUTURE]` window is re-pulled each run, so a live
  appointment's `_loaded_at` advances while a deleted one goes stale — filter to
  `_loaded_at >= MAX(_loaded_at) - 30min` to drop ghosts. `FUTURE_DAYS=31` so a
  month of forward bookings is covered and refreshed (needed by the upcoming
  count + welcome list). Keep `FUTURE_DAYS` ≥ the furthest forward horizon any
  reader needs.
- **Upcoming-sessions count grain = distinct clinician slot.** A group / 2:1
  class is two `appointment_id` rows sharing the same `(calendar_color,
  start_at, end_at)`; count `COUNT(DISTINCT that tuple)` so it's one session
  (calendar occupancy), not two. The patient-session qualifier (shared by
  `fetch_upcoming_sessions` and `fct_new_patient_welcome`): not cancelled/void/
  no-show AND (`patient_id` OR inline `handphone`/`email` OR real
  `treatment_type`). `treatment_type` alone is not a qualifier (~45% Untyped).
- **Retired Leads (revivable).** **"Won" = the lead became a patient/customer**
  (their first visit), **not** "bought a package"; packages are a separate
  worklist, never a funnel stage. **Lead `contact` PII is stored on purpose** —
  a pre-patient isn't in Plato to hydrate from, so `marts.lead_events` is the
  *only* exception to the patient-worklist rule of "key on id, never persist
  name/phone" (the welcome list's profile-less bookings hydrate from the
  appointment payload, which is Plato, so they don't persist either). Keep it
  gated (founder+staff, frontdesk) and keep `note` operational, not clinical.

## Outbound patient email
- **Two senders, one transport.** `scripts/booking/mailer.py` (booking
  confirmations, triggered by a booking) and `scripts/reminders/` (the daily
  48-hour reminder Cloud Run Job). Both send over Gmail SMTP as
  `hello@gojiphysio.com` with `gmail-app-password` from Secret Manager. Add a
  third sender the same way rather than introducing an ESP.
- **Anything that mails patients on a schedule ships with `DRY_RUN=true`** and a
  digest to `hello@`, and is flipped by hand only once the manual process it
  replaces has stopped. The reminder job replaced a button someone clicked in
  Plato daily; going live without stopping that would have double-mailed every
  patient.
- **Sends are ledgered append-only and checked before sending**
  (`marts.appointment_reminder_events`). That is what makes the job safe to
  re-run after a partial failure — never rely on the job completing once.
- **Every outbound CTA routes through `go.gojiphysio.com/<slug>`** with its own
  slug, so the channel is attributable (`reminder-wa` for reminder emails). Never
  paste a raw `wa.me` link into an email body.

## Marketing tab
- **Hierarchy = decision order.** The tab reads top-down: (1) **North stars** —
  active + new patients on one range-bucketed chart (`renderNorthStarChart`, from
  `trends.active_patients` + `trends.new_patients`; Revenue is deliberately *off*
  this tab); (2) **Top-of-funnel channels** — reach/intent per source, with
  Instagram promoted to a grouped card (reach + profile visits + follower growth);
  (3) the **acquisition Sankey** (channel-level); (4) **on-site path & booking
  drop-off** (the golden flow); then the base/ICP/referral lenses. Keep new work
  in the band that matches its altitude — don't scatter a north-star number into
  the channel grid.
- WIP "pending integration" cards are the **seams** where live integrations plug
  in. Convert a WIP card to a live card (value id + `kpi-trend` div + `badge live`)
  and wire it in `renderMarketingMetrics(r)`.
- **Per-page attribution comes free from the beacon.** The landing beacon records
  `location.pathname` on **every** event (session_start *and* page_view — see
  `BaseLayout.astro`), so `web_session_events.landing_path` is the page per
  pageview, not just the session's first landing. `fetch_web_pages` /
  `_WEB_PAGE_CASE_SQL` bucket it into Home / Booking / Conditions / … — that's the
  per-page split, no new site tracking needed. Keep the buckets in sync with the
  site's route tree.
- **Golden flow = on-site path + booking drop-off + CTA session passthrough.**
  `fetch_onsite_flow` classifies booking-page sessions as booked / bailed-to-
  WhatsApp / dropped by joining `link_click_events.session_id` →
  `booking_funnel_events.session_id`. A WhatsApp tap can't use the `?cid`
  passthrough (external wa.me) and cross-origin `Referer` is trimmed to the
  origin, so on-site `web-*` CTA links are decorated client-side with
  `?sid=<booking session>&p=<path>` (inline script in `BaseLayout.astro`); the
  redirect logs them onto `link_click_events.session_id`/`page`. Off-site channels
  (ig/gbp/ads/qr) never carry these — they're NULL.
- **Cost per booking is the paid headline** (`_paid_performance`), and it is
  assembled in Python: `fetch_google_ads` reads the US-multi-region transfer
  while `fetch_paid_funnel` reads `marts`, and the two **cannot be joined in one
  query**. A session counts as paid when its *first* `web_session_events` row
  carries a `gclid` — keying off any row would count sessions that merely passed
  through a tagged landing, since a session spans pages. When bookings are zero
  the metric is **None, not the spend**: "$607 per booking" and "$607, none
  booked" are different claims, so the card shows "—" plus the at-risk spend in
  the subtext. `cost_per_funnel_entry` is the leading indicator — at SGD 20/day
  bookings are too sparse to move week to week.
- **Google Ads table choice must stay deterministic.** `fetch_google_ads` picks
  `ads_CampaignBasicStats_*` by an explicit preference order. The old loose
  regex + `tables[0]` with no `ORDER BY` silently landed on
  `p_ads_HourlyAccountStats` (account-grain impressions disagree with the
  campaign roll-up: 21,202 vs 12,851 for Aug 2026) and was one row-order change
  away from a `*ConversionStats` table, which has no cost/click columns at all
  and would degrade the card to zeros without an error.
- **Instagram is more than reach.** The `marketing_ingest` job now pulls
  `profile_views` (additive → SUM) and `followers_count` (running total → read
  latest, growth = latest−first) alongside reach; `fetch_instagram_engagement`
  reads `marts.fct_instagram_profile_views` / `fct_instagram_followers`. Reach is
  fatal-on-failure; the two newer pulls are best-effort (skip, don't break reach).
- Inbound inquiries live in the **front-desk Leads pipeline** (`marts.lead_events`),
  the single source of truth. Don't add enquiry capture or other static "operating
  tool" widgets here — the old 90-day-plan tools (rhythm checklist, content
  calendar, partnership pipeline, manual enquiry log) and their
  `marts.marketing_ops_events` backing were removed once the plan lapsed. Keep the
  tab a **read-only marketing lens** on the warehouse.
- The **acquisition funnel** ("by path") is a 4-column Sankey (`chartjs-chart-sankey`,
  **vendored in `static/`**, not a CDN — registered once near the top of the main
  script, guarded): **Discovery → Owned surface → CTA → Booked**. Web is the
  *surface*, not the top of funnel. `_build_funnel_paths` joins the three
  first-party streams (each edge its own honest measure; units shift across
  columns): **Discovery → Website** = landings by channel from the beacon
  (`fetch_web_channels` / `web_session_events`, classified by utm/gclid/referer);
  **Surface → CTA** = go-link taps (`link_click_events` slug splits; `web-*` under
  Website, `bio-*` under bio.site + an Instagram→bio.site edge, `gbp/ads/qr/ig`
  bypass the site straight to a CTA); **CTA → Booked** = confirmed native bookings
  (`booking_funnel.booked`) and won WhatsApp leads (`lead_wins`). The click-id
  passthrough (`/r/<slug>?cid=` for `-book` slugs → beacon `go_click_id`) closes
  the old "no FK from `link_click_events`" gap for the on-site journey.
  `renderFunnelSankey` degrades gracefully if the plugin or any stream is missing.
  The Sankey stays **channel-level and tidy**: discovery channels below
  `FUNNEL_DISCOVERY_MIN` arrival sessions fold into "Other" (except Direct) so it
  doesn't sprout hairline bands — the granular story lives in the on-site-path viz.
- The **booking funnel card** (`fetch_booking_funnel` / `renderBookingFunnel`)
  shows stage drop-off **plus a "Stuck" line**: `availability_empty` (date with no
  slots), `availability_error` (the times fetch failed in the browser),
  `validation_error` (bad phone/email), and `book_error` by reason code —
  the silent dead-ends the progress bars can't show. The caption carries a
  `clinician_changed` behaviour note (sessions that touched the clinician
  picker). Funnel-event details vary by stage (date_picked = the date), so the
  funnel query collapses `detail` for everything except `book_error` — raw
  (stage, detail) grouping would over-count sessions. A stage that's zero
  mid-funnel while later stages have data renders as "not instrumented yet"
  (hidden), not a 100% drop. It now lives in the **on-site
  path & booking drop-off** section next to `renderWebPages` (per-page bars) and
  `renderOnsiteFlow` (booked / bailed-to-WhatsApp / dropped), so the whole golden
  flow reads in one place.
