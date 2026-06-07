# Dashboard — conventions

Flask app (`app.py`) serving one page (`template.html`) from BigQuery, on Cloud
Run. Founder dashboard (`APP_MODE=dashboard`) and front-desk portal
(`APP_MODE=frontdesk`) are the same code on two subdomains. See `DEPLOY.md`.

## Design philosophy
- **Glanceable headline metrics.** Each card answers a question at a glance or in
  a team discussion — a number + trend. **No big tables, no per-post drilldowns;**
  deep exploration belongs in the source platform (Instagram, Search Console, GBP).

## UI
- **Reuse the trend ticker.** New metric cards show change vs the previous period
  via `renderTrend(id, current, previous, label)` (green ▲ / red ▼ / grey —).
  Back it with a `ranges[key].<metric>` + `ranges[key].<metric>_prev` pair from
  `build_payload()`.
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
  Founder routes are founder-only and 404 on the frontdesk subdomain.
- **Graceful degradation.** Every `fetch_*` wraps its query in try/except and
  returns a safe empty value, so a not-yet-deployed table never breaks the page
  (see `fetch_marketing_ops`, `fetch_link_clicks`).
- **Cache:** `get_payload()` caches `build_payload()` for `CACHE_TTL` (5 min);
  writes pop the cache. `build_payload()` fans queries out in a thread pool —
  add per-range work to `range_jobs[key]` and mirror it in the results assembly.
- **Writes are append-only event logs** with table-level `dataEditor` grants
  (`record_*` → parameterised DML). **High-frequency / public** writes (e.g. link
  clicks) use the **streaming API** (`insert_rows_json`), not DML — DML is capped
  at 1,500 statements/table/day. New writable table → add it to the grant loops in
  `deploy_admin.sh`, `DEPLOY.md`, and `.github/workflows/deploy-dashboard.yml`.

## Marketing tab
- WIP "pending integration" cards are the **seams** where live integrations plug
  in. Convert a WIP card to a live card (value id + `kpi-trend` div + `badge live`)
  and wire it in `renderMarketingMetrics(r)`.
