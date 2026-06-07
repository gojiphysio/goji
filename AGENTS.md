# Goji — repo guide for agents

Monorepo for Goji Health (physiotherapy clinic). Two main areas:

- `business-intelligence/` — the BI/ops platform. Most work happens in
  `scripts/dashboard/` (Flask + vanilla-JS + Chart.js, on Cloud Run, reads
  BigQuery), `scripts/ingestion/` (Cloud Run Jobs that load external data into
  BigQuery), and `scripts/sql/` (`stg/` views + `marts/` facts).
- `marketing/` — the 90-day campaign strategy, content, and guardrails (docs).

**Nested `AGENTS.md` files carry the detail** — read the one for the directory
you're working in (`scripts/dashboard/`, `scripts/ingestion/`, `marketing/`).
`DEPLOY.md` and `ROADMAP.md` in `scripts/dashboard/` are the deploy/roadmap source.

> Instruction files use **`AGENTS.md`** as the source of truth (portable across
> coding agents). A sibling **`CLAUDE.md`** at each scope is a one-line
> `@AGENTS.md` import so Claude Code auto-loads the same content — edit the
> `AGENTS.md`, never the stub.

## Working agreements (repo-wide)

- **Free / DIY first.** Prefer free first-party APIs (Meta Graph, Google Search
  Console, Google Business Profile) and small DIY pieces over paid vendors. Only
  reach for a paid service when the free path genuinely can't do the job, and
  flag it explicitly.
- **Every customer CTA is a trackable WhatsApp link.** WhatsApp is the primary
  CTA — customers message before booking. Route every outbound CTA (site, IG,
  GBP, ads, email, QR) through the public redirector `go.gojiphysio.com/<slug>`
  (the `goji-links` service) so the click is logged and attributable. Don't
  publish a raw `wa.me` link, and don't use the internal `dashboard.*` domain.
- **Branch & PR.** Develop on a feature branch and open a PR to `main`. **Never
  push directly to `main`** — deploys run from `main` via GitHub Actions.
- **SQL is idempotent.** Every `.sql` is `CREATE OR REPLACE` (views) or
  `CREATE TABLE IF NOT EXISTS` (tables); `deploy_all.sh` re-runs them safely.
- **Least privilege.** The dashboard service account is read-only on BigQuery
  except table-level `dataEditor` grants on the append-only event tables.
- **Capture rules as you learn them.** When a build surfaces a new rule of
  thumb, add it to the nearest `AGENTS.md` in the same PR.

## Harness engineering

We engineer the *harness* (context + constraints + feedback loops + tooling)
around the agent, not just the code. (See OpenAI's "Harness engineering.")

- **If it's not in-context, it doesn't exist.** Durable decisions, plans,
  rationale, and learnings live in **versioned repo artifacts** — the scoped
  `AGENTS.md` files, `scripts/dashboard/DEPLOY.md` (deploy/ops truth), and
  `ROADMAP.md` — not in chat. Commit the rule/decision in the same PR that
  relied on it.
- **These files are a map, not an encyclopedia.** Keep each `AGENTS.md` short
  and pointed (progressive disclosure): the entry point sends you to the deeper
  source of truth (`DEPLOY.md`, `ROADMAP.md`, `marketing/strategy/*`). Don't let
  them bloat into a stale manual.
- **Enforce invariants, not implementations.** Mirror the established patterns
  (the `plato_*` ingestion shape, `stg/`→`marts/` layering, per-route auth,
  graceful-degradation `fetch_*`) so new work is predictable; leave the *how*
  free. Tests run green before merge (CI gates deploy) and the PR checklist
  (`.github/pull_request_template.md`) is the golden-principles check.
- **When something is error-prone, fix the harness** — a doc, a constraint, a
  test — so it's easy next time, rather than just patching the one-off.
