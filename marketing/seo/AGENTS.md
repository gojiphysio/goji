# SEO / AEO loop — conventions

The site is audited and improved by an agent on a schedule, with as little
human intervention as is safe. This file is the contract for that loop.
Strategy, keyword→page map and GEO rules live in `seo-geo-review.md`; copy
rules in `../strategy/03-compliance-guardrails.md`; site rules in
`../website/prototype/AGENTS.md`.

## Never a medical untruth

Hard rule, above every metric: the loop never invents, strengthens or extends
a clinical claim. A tier A edit may only **restate** what the site already
says (copy Cheryl has reviewed): shorter, clearer, better structured. New
facts, numbers, timeframes, outcomes, conditions or services are tier B and
wait for clinical review. When unsure, it is tier B.

## Approval tiers (enforced by `tools/tier_gate.py` in CI)

| Tier | What | Who merges |
|---|---|---|
| **A** | Meta titles/descriptions, H1s, JSON-LD (`src/lib/schema.ts` + page schema), internal links, `llms.txt` sync, image weight/alt, rewording reviewed copy, audit outputs | The loop, after all checks pass |
| **B** | New pages or blog posts, new numeric/time claims, compliance-lint hits, `reviewer`/`lastReviewed` changes | Cheryl reviews, owner merges |
| **C** | `/book` and booking code, CTAs/`links.ts`, prices, NAP/hours (`site.ts`), `_redirects`, `robots.txt`, `astro.config`, layouts (analytics beacon), CI, this file, `tools/` | Owner |

- The loop labels a PR `tier-a` only when it intends to self-merge. The
  `SEO tier gate` check fails a `tier-a` PR whose diff is not tier A, so a
  mislabel can't ship. Merge only when **SEO tier gate, Site checks and
  Cloudflare Pages** are all green (`gh pr checks`), then `gh pr merge --merge`.
- One concern per PR (e.g. "meta descriptions", "llms.txt sync"), so a bad
  change reverts cleanly.
- Never split a B/C change into tier A pieces to get it through.

## Checks

- `tools/check_dist.py` — static checks over the built `dist/`, run on every
  site PR. Rules are a **ratchet**: a rule is WARN while pages still break it,
  and the PR that fixes the last offender promotes it to ERROR in `LEVEL` so it
  can't regress. (Promoting is a `tools/` change, so it is tier C: batch it
  into the next owner-reviewed PR.)
- `tools/live_audit.py` — live site, weekly in CI. Set the `PSI_API_KEY`
  repo secret for Core Web Vitals (the keyless quota 429s).
- `tools/tier_gate.py` + `test_tier_gate.py` — the tier classifier.

## AEO measurement (monthly)

- One canonical query set: `aeo-queries.json`. Add queries; never rename or
  reword one (it breaks the trend).
- Results: `audits/<YYYY-MM-DD>/aeo-<engine>-<variant>.json`, one record per
  query, same fields every run.
- Engines and modes (no memory, no personalisation, or the owner's own Goji
  work biases the answers):
  - **ChatGPT**: logged-in Temporary Chat, header set to **Unpersonalized**,
    Web search on. `?q=` does not auto-send; press Enter.
  - **Claude**: claude.ai **Incognito** chat with web search.
  - **Google**: logged out, `&gl=sg&hl=en&pws=0&uule=w+CAIQICIJU2luZ2Fwb3Jl`.
    CAPTCHAs arrive after ~35 rapid queries: pace 10s+, finish next day if hit.
- Location: ChatGPT/Claude infer it from IP. When the machine is not in SG,
  run variant `sg-context` (prefix rule in `aeo-queries.json`); when it is,
  also run `sg-ip`. Never mix the two series in one trend line.

## Monthly loop (local scheduled task on the owner's Mac)

1. **Measure**: `live_audit.py`, build + `check_dist.py`, the AEO sweep,
   Search Console (`marts.fct_search_console_daily`) for the last 28 days.
2. **Diagnose**: diff against the previous `audits/` run; write
   `audits/<date>/summary.md` (what moved, top gaps, proposed fixes by tier).
3. **Fix**: tier A changes as `tier-a` PRs; tier B/C as normal PRs with the
   evidence in the description.
4. **Ship**: self-merge tier A when all checks pass; leave B/C open.
5. **Record**: update `seo-geo-review.md` §1-2 and capture any new rule here.
