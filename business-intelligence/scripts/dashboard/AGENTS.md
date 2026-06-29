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
  via `renderTrend(id, current, previous, prevStart, prevEnd)` (green ▲ / red ▼ / grey —).
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
  (see `fetch_marketing_ops`, `fetch_link_clicks`).
- **Cache:** `get_payload()` caches `build_payload()` for `CACHE_TTL` (5 min);
  writes pop the cache. `build_payload()` fans queries out in a thread pool —
  add per-range work to `range_jobs[key]` and mirror it in the results assembly.
- **`date.today()` must use SGT.** All `date.today()` / `datetime.now()` calls in
  the backend use `datetime.now(ZoneInfo("Asia/Singapore")).date()` so the date
  boundaries match the clinic's operating timezone, not the UTC Cloud Run host.
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
- It's the **worklists Plato doesn't track**, not a second calendar: **Leads**
  (inbound funnel) → **Package alerts** (renewals) → **Follow-ups** (win-backs).
  Don't re-add a Today/schedule/call-list mirror of Plato — that was removed
  precisely to avoid two sources of truth.
- **"Won" = the lead became a patient/customer** (their first visit), **not**
  "bought a package". Packages are a separate worklist, never a funnel stage.
- **Lead `contact` PII is stored on purpose** — a pre-patient isn't in Plato to
  hydrate from, so `marts.lead_events` is the *only* exception to the
  patient-worklist rule of "key on id, never persist name/phone". Keep it gated
  (founder+staff, frontdesk) and keep `note` operational, not clinical.

## Marketing tab
- WIP "pending integration" cards are the **seams** where live integrations plug
  in. Convert a WIP card to a live card (value id + `kpi-trend` div + `badge live`)
  and wire it in `renderMarketingMetrics(r)`.
- The manual enquiry log is being **replaced by the front-desk Leads pipeline**
  (`marts.lead_events`) — the single source of truth for inbound inquiries. Don't
  build new enquiry capture here.
- The **acquisition funnel** ("by path") is a Sankey (`chartjs-chart-sankey`,
  **vendored in `static/`**, not a CDN — registered once near the top of the main
  script, guarded). `_build_funnel_paths` builds Source → bio.site → CTA flows
  from `link_click_events` slug splits (the `wa_by_slug` / `book_by_slug` already
  in the payload — no extra query). bio.site is the Instagram link-in-bio hop
  (`bio-*` slugs route Instagram → bio.site → CTA; `ig-*` are direct). First
  visits show as a single stat: a tap can't yet be traced to the booking it leads
  to (no FK from `link_click_events` to `lead_events`/invoices — closing that gap
  needs a click-id passthrough). `renderFunnelSankey` degrades gracefully if the
  plugin or the slug data is missing.
- The **Instagram cards** (reach, profile visits, followers) read
  `marts.fct_instagram` via `fetch_instagram`, fed by the `instagram_insights`
  ingest job (Graph API). **Reach is de-duplicated** → the card shows the
  trailing-28-day total (`period='days_28'`), never a sum of daily reach; profile
  views are range-additive; followers is the latest count + growth delta. Cards
  stay "—" until the job runs (gated on the `IG_USER_ID` repo var — see DEPLOY.md).
  IG metrics are top-of-funnel KPIs, **not** a Sankey column (different scale/grain).
