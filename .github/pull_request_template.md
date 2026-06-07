## What & why

<!-- One or two lines: what this changes and why. -->

## Convention checklist

<!-- See AGENTS.md (root + the nested one for the area you touched). -->

- [ ] **Mobile-checked** — any new table scrolls (doesn't overflow); grid items
      holding tables have `min-width:0`; base CSS sits before `@media` blocks.
- [ ] **Glanceable** — dashboard additions are headline metrics with trends, not
      deep tables/drilldowns.
- [ ] **Trackable WhatsApp link** — customer CTAs route through `/r/<slug>`, not a
      raw `wa.me`/booking URL.
- [ ] **Free / DIY first** — no paid vendor introduced without calling it out.
- [ ] **No secrets committed** — credentials live in Secret Manager / env, not git.
- [ ] **SQL idempotent** — `CREATE OR REPLACE` / `CREATE TABLE IF NOT EXISTS`; new
      writable tables added to the `dataEditor` grant loops.
- [ ] **Tests pass** — dashboard + ingestion tests run green.
- [ ] **Rules captured** — any new rule of thumb added to the nearest `AGENTS.md`.
