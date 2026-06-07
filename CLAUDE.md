# Goji — repo guide for agents

Monorepo for Goji Health (physiotherapy clinic). Two main areas:

- `business-intelligence/` — the BI/ops platform. Most work happens in
  `scripts/dashboard/` (Flask + vanilla-JS + Chart.js, on Cloud Run, reads
  BigQuery), `scripts/ingestion/` (Cloud Run Jobs that load external data into
  BigQuery), and `scripts/sql/` (`stg/` views + `marts/` facts).
- `marketing/` — the 90-day campaign strategy, content, and guardrails (docs).

**Nested `CLAUDE.md` files carry the detail** — read the one for the directory
you're working in (`scripts/dashboard/`, `scripts/ingestion/`, `marketing/`).
`DEPLOY.md` and `ROADMAP.md` in `scripts/dashboard/` are the deploy/roadmap source.

## Working agreements (repo-wide)

- **Free / DIY first.** Prefer free first-party APIs (Meta Graph, Google Search
  Console, Google Business Profile) and small DIY pieces over paid vendors. Only
  reach for a paid service when the free path genuinely can't do the job, and
  flag it explicitly.
- **Every customer CTA is a trackable WhatsApp link.** WhatsApp is the primary
  CTA — customers message before booking. Route every outbound CTA (site, IG,
  GBP, ads, email, QR) through the dashboard's `GET /r/<slug>` redirect so the
  click is logged and attributable. Don't publish a raw `wa.me` link.
- **Branch & PR.** Develop on a feature branch and open a PR to `main`. **Never
  push directly to `main`** — deploys run from `main` via GitHub Actions.
- **SQL is idempotent.** Every `.sql` is `CREATE OR REPLACE` (views) or
  `CREATE TABLE IF NOT EXISTS` (tables); `deploy_all.sh` re-runs them safely.
- **Least privilege.** The dashboard service account is read-only on BigQuery
  except table-level `dataEditor` grants on the append-only event tables.
- **Capture rules as you learn them.** When a build surfaces a new rule of
  thumb, add it to the nearest `CLAUDE.md` in the same PR.
