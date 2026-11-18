# SEO / AEO audit — 2026-11-04

First full run in November (scheduled loop). The machine was on a Singapore IP
(NordVPN), so this tick skipped Google, which challenges VPN IPs.
Query set `../../aeo-queries.json` now has 54 queries; the 7 `blog-*` ids are new.

Files: `live/` (live audit), `dist.json` (build check). **No `aeo-*.json` this
run** (see below).

## Scoreboard

| Engine | Metric | 26 Oct | 4 Nov |
|---|---|---|---|
| Claude (Incognito, sg-ip / sg-context) | Goji named | 15/45 | **not measured**: claude.ai signed out in the browser pane |
| ChatGPT | Goji named | 11/45 (logged out) | **not measured**: login expired |
| Google AIO / Maps pack / organic | — | 8/35 · 8/35 · 3/35 | **not measured**: VPN IP, Google skipped |
| Search Console | 28d vs prior 28d | — | **not measured**: `bq` reauth needed (non-interactive) |

Agents never sign in, so nothing was measured on any engine.
AEO trend data resumes at the next tick once the owner signs ChatGPT and
claude.ai back in to the browser pane. Before the ChatGPT logged-in series
resumes, check that Memory, Reference record history and Connector search are
off.

## Technical (live audit + build check)

- Live: 83 sitemap URLs, 85 link targets. **1 error:** blog bylines "By the
  Goji team" linked to `/team/`, which 404s (no team index page). Fixed in
  #223. Warnings: one external link 502 (sweatboxyoga prenatal page, on
  `/blog/prenatal-classes-singapore/`); `PSI_API_KEY` still unset.
- Build: 0 errors, 2 warnings (title length). The postpartum service title
  went from 67 to 59 chars in #222. The Zaobao press title is 82 chars; the
  press collection has no `seoTitle` field, so shortening it means a schema
  change (`config.ts`, outside the tier A allowlist) or a headline change.
  Left for the owner.
- Fixed since 26 Oct: the 18 slash-less `/conditions/` links are gone
  (`internal_link_slash` is now ERROR level and passes).

## What moved

No engine was measured, so there is no AEO or SERP movement to report. The 26 Oct
gaps stand: Maps #1 lost (9→1), Claude sources Goji from Instagram mirrors
rather than gojiphysio.com, and Goji scores zero on the general and condition questions.

## Next, by tier

**Owner / operator:**
1. Sign ChatGPT and claude.ai back in to the Claude browser pane (off-VPN for
   Google SSO); check ChatGPT personalisation is off.
2. `gcloud auth login` as hello@gojiphysio.com so the loop can read Search Console.
3. Carried over from 26 Oct: GBP categories and review asks, Instagram/LinkedIn website link,
   old Squarespace site takedown, roundup outreach.

**A — loop:** #222 (postpartum title), #223 (`/team/` 404). Checks are
green, but auto mode refused the self-merge ("merge without review"), so both
are left for Charles.

**B/C:** Zaobao press title needs a `seoTitle` on press (`config.ts`) or a
shorter headline; replace or drop the dead sweatboxyoga link; `PSI_API_KEY`;
sitemap `lastmod`.
