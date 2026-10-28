# SEO / AEO loop — conventions

The site is audited and improved by an agent on a schedule, with as little
human intervention as is safe. This file is the contract for that loop.
Strategy, keyword→page map and GEO rules live in `seo-geo-review.md`; copy
rules in `../strategy/03-compliance-guardrails.md`; site rules in
`../website/AGENTS.md`.

## Never a medical untruth

Hard rule, above every metric: the loop never invents, strengthens or extends
a clinical claim. A tier A edit may only **restate** what the site already
says (copy Cheryl has reviewed): shorter, clearer, better structured. New
facts, numbers, timeframes, outcomes, conditions or services are tier B: the
loop never self-merges them, and each must be sourced per
`../content-engine/blog-brief.md`. When unsure, it is tier B.

## Approval tiers (enforced by `tools/tier_gate.py` in CI)

| Tier | What | Who merges |
|---|---|---|
| **A** | Meta titles/descriptions, H1s, JSON-LD (`src/lib/schema.ts` + page schema), internal links, `llms.txt` sync, image weight/alt, rewording reviewed copy, audit outputs | The loop, after all checks pass |
| **B** | New pages or blog posts, new numeric/time claims, compliance-lint hits, `reviewer`/`lastReviewed` changes | Owner merges; a physio reviews after it ships (decision 2026-10-28; queue in `blog-plan.md`) |
| **C** | `/book` and booking code, CTAs/`links.ts`, prices, NAP/hours (`site.ts`), `_redirects`, `robots.txt`, `astro.config`, layouts (analytics beacon), CI, this file, `tools/` | Owner |

- The loop labels a PR `tier-a` only when it intends to self-merge. The
  `SEO tier gate` check fails a `tier-a` PR whose diff is not tier A, so a
  mislabel can't ship. Merge only when **SEO tier gate, Site checks and
  Cloudflare Pages** are all green (`gh pr checks`), then `gh pr merge --merge`.
  In auto permission mode the merge can be refused as "merge without
  review"; then leave the PR open and say so in the report rather than retry.
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
  - **ChatGPT**: logged-in Temporary Chat with the Web search chip, and the
    owner's memory/chat-history referencing switched off in Settings (the
    in-chat "Unpersonalized" toggle was removed in Oct 2026). `?q=` does not
    auto-send when logged in; press Enter. **Logged out it auto-sends**, so
    check for a "Log in" button first. Check the chip on every send; broken
    loads drop it. Chat does not consume the weekly "usage remaining" quota
    (verified 2026-10-20: 5% before and after 45 queries); still stop if it
    falls, so the owner keeps their quota.
  - **Claude**: claude.ai **Incognito** chat with web search, a new chat per
    query.
  - **Google**: logged out, `&gl=sg&hl=en&pws=0&uule=w+CAIQICIJU2luZ2Fwb3Jl`,
    from the normal (non-VPN) IP. CAPTCHAs arrive after ~35 rapid queries:
    pace 15s+, finish next day if hit. A VPN IP is challenged on query 1.
  - A login expired? The owner signs in; agents never do. Google SSO fails on
    a VPN IP, so sign in off the VPN, then reconnect (sessions survive).
  - **Signing in to ChatGPT/Claude with Google signs the browser pane into
    Google**, which breaks the logged-out Google run (seen 2026-10-26). Run
    Google in gstack's headed browser instead (`$B connect`: a separate,
    signed-out Chromium profile). Headless gstack gets Google's "unusual
    traffic" page on query 1. When two agents share that browser, pin each
    to its own tab with `BROWSE_TAB=<n>` on every command; `newtab` steals
    the active tab.
  - Check ChatGPT's Settings → Personalization before every run: Memory,
    "Reference record history" and "Connector search" all off. Memory came
    back on between runs once (2026-10-26). If it's on and the owner isn't
    around, run **logged out** as a separate series
    (`aeo-chatgpt-sg-ip-loggedout.json`), never mixed with the logged-in
    trend.
- Location: ChatGPT/Claude infer it from IP. When the machine is not in SG,
  run variant `sg-context` (prefix rule in `aeo-queries.json`); when it is,
  also run `sg-ip`. Never mix the two series in one trend line. A Singapore
  IP comes from the owner's NordVPN (Singapore server, connected by hand)
  with **Tailscale off**: the two VPNs fight over DNS/routes and NordVPN
  passes no traffic while Tailscale is up.

## Monthly loop (local scheduled task on the owner's Mac)

1. **Measure**: `live_audit.py`, build + `check_dist.py`, the AEO sweep,
   Search Console (`marts.fct_search_console_daily`) for the last 28 days.
2. **Diagnose**: diff against the previous `audits/` run; write
   `audits/<date>/summary.md` (what moved, top gaps, proposed fixes by tier).
3. **Fix**: tier A changes as `tier-a` PRs; tier B/C as normal PRs with the
   evidence in the description.
4. **Ship**: self-merge tier A when all checks pass; leave B/C open.
5. **Record**: update `seo-geo-review.md` §1-2 and capture any new rule here.
