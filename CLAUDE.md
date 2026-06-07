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

## Harness engineering

We engineer the *harness* (context + constraints + feedback loops + tooling)
around the agent, not just the code. (See OpenAI's "Harness engineering.")

- **If it's not in-context, it doesn't exist.** Durable decisions, plans,
  rationale, and learnings live in **versioned repo artifacts** — the scoped
  `CLAUDE.md` files, `scripts/dashboard/DEPLOY.md` (deploy/ops truth), and
  `ROADMAP.md` — not in chat. Commit the rule/decision in the same PR that
  relied on it.
- **Agent-legible structure.** The `CLAUDE.md` hierarchy is the system map;
  keep it current. Mirror established patterns (the `plato_*` ingestion shape,
  `stg/`→`marts/` layering, per-route auth) so new work is predictable.
- **Feedback loops gate changes.** Tests run green before merge (CI gates
  deploy); the PR checklist (`.github/pull_request_template.md`) is the
  golden-principles check. When something was error-prone, improve the harness
  (a doc, a constraint, a test) so it's easy next time.
