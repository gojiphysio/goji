# SEO / AEO audit — 2026-11-16

First run on tidepool with Claude in Chrome connected, and the first with
Search Console data. SG IP, `AS56300 MyRepublic Ltd.` (a home ISP, not a VPN),
so the `sg-ip` series applies.

**Measured:** ChatGPT (logged out, sg-ip, 47/47), Claude (Incognito, sg-ip,
47/47), Search Console (28 days to 15 Nov), `live/` (live_audit.py),
`dist.json` (build + check_dist.py on `main` @ 52db966).

**Not measured:**
- **Google browser checks: skipped by owner decision (2026-11-16).** Google
  organic now comes from Search Console (`aeo-google-gsc.json`). AI Overviews
  and the Maps pack are not measured.
- **ChatGPT logged-in series: not run.** The Chrome profile is logged out
  (shows "Log in"), so only the logged-out series ran. Its Personalization
  settings could not be checked.

Files: `aeo-chatgpt-sg-ip-loggedout.json`, `aeo-claude-ai-sg-ip.json`,
`aeo-google-gsc.json`, `search-console/` (`daily.json`, `terms.json`,
`meta.json`), `live/`, `dist.json`. The 7 `blog-*` queries were not run on
the engines (as on 11 Nov), so engine series stay at 47 ids.

## Scoreboard (shared ids only)

"45" = the ids shared with 12 Oct (excludes the two private-Pilates queries
added on 26 Oct), as in earlier runs.

| Engine | Metric | Previous | 16 Nov |
|---|---|---|---|
| ChatGPT (logged out, sg-ip) | Goji named | 12/45 · 14/47 (11 Nov) | **13/45 · 14/47** |
| ChatGPT | gojiphysio.com cited | 14/47 | **13/47** |
| Claude (Incognito, sg-ip) | Goji named | 15/45 · 15/47 (26 Oct) | **14/45 · 15/47** |
| Claude | gojiphysio.com cited | 0 | **0** |
| Google organic (Search Console) | AEO queries with impressions | — | **11/54** (43 not ranking) |
| Search Console | 28d clicks · impressions | 166 · 4,150 | **238 · 13,300** |

## What moved

**ChatGPT (logged out), net flat at 14/47:**
- Newly named (3): pelvic floor physio (#4, correct S$260/S$380), physio
  during pregnancy (#3), mummy and baby assessment (#1, cites the target page).
- Lost (3): postnatal physio, menopause, private reformer Pilates.
- Positions: women's physio #2→#3, women's health physiotherapist #3→#2,
  pelvic pain #3→#4. Private Pilates Lentor, both Lentor queries and all
  brand queries still #1.
- **Price facts, still wrong in 3 answers:** "Home visit: $330"
  (local-wh-lentor; site: $380), and the Mummy & Baby home visit given as
  S$380 (wedge-mummy-baby, wedge-home-visit; site: $450). The physiotherapy
  home visit was quoted correctly at S$380 in 2 answers. Fixed at source in
  #233 (merged). All other prices (review $230, paeds from $160, Pilates
  $149/$160, S&C $180), staff names, address and hours matched the site.
- `?q=` auto-sent while logged out this run (11 Nov it did not), and search
  ran without picking the "+" menu item.

**Claude (Incognito), 15/47 (same total, different queries):**
- Newly named (3): pelvic floor physiotherapy (#4), pelvic pain (#6), private
  Pilates Lentor (#1).
- Lost (3): best postnatal physio, prenatal physio, prolapse. All three
  answers ran web search only (no places search) and listed what Sassy Mama,
  Little Steps, Women's Weekly and Expat Living list.
- Up: women's physio #6→#3, women's health physiotherapist #5→#3, pelvic floor
  near me #6→#3, postnatal #6→#3 ("the pick if you're up north").
- **Pattern:** when Claude uses places search, Goji is named on every
  women's-health query except the Katong tracking query. When it uses web
  search only, Goji is named on none of 21 non-brand queries. Its web results never return gojiphysio.com: on
  the brand queries it cited an Instagram mirror, Luma, a company-registry
  page and a LinkedIn profile, and said "I couldn't find published pricing or
  opening hours". The site publishes both.
- The web search toggle is no longer in the "+" menu; search ran by default.
  Connectors were enabled in the composer; none were invoked on any query.

**Search Console (19 Oct-15 Nov vs 21 Sep-18 Oct; the last 2-3 days are
incomplete):**
- Clicks 166 → 238 (+43%). Impressions 4,150 → 13,300 (3.2x). CTR 4.0% →
  1.8% and average position 8.2 → 22.7 because the new impressions are long
  tail at low positions (841 distinct queries vs 323).
- Brand: "goji physio" 126 impressions, 65 clicks, position 1.0; "goji
  women's and family physiotherapy" position 1.9.
- Top page by impressions is `/blog/prenatal-classes-singapore/` (1,999,
  position 15.2, 8 clicks). Searchers say "antenatal" as often as "prenatal"
  (see #234).
- AEO set vs Search Console: 11/54 queries had impressions. Ranking: brand
  (1.0, 1.9), women's physio singapore (1.1, 28 impressions, 0 clicks),
  postpartum checklist blog (3.8), prenatal physiotherapy (7.2), diastasis
  recti (9.0), postnatal pilates (10.0), prenatal classes blog (10.5),
  fracture (15.9), pelvic floor physiotherapy (27.8), paediatric (80.5). The
  other 43, including "physiotherapy lentor", are **not ranking**: no recorded
  impressions. (Search Console omits very rare queries, so "not ranking"
  means none recorded.)

**Technical:**
- Live audit: 83 sitemap URLs, 84 link targets, **0 errors**, 3 warnings.
  40/40 AI/search-bot fetches returned 200 with no challenge.
- Core Web Vitals were measured this run (lab): `/` 0.85 (LCP 2.6s, TBT
  451ms); `/services/pelvic-floor-physiotherapy/` **0.76, LCP 5.3s**. Other
  sampled pages 0.92-0.99.
- Build check: 0 errors, **0 warnings** (12 Nov: 1, fixed by #226).
- Still open: the sweatboxyoga link 502s to the audit UA only (left as is,
  see 12 Nov).

## Top gaps

1. **Claude's web search cannot see gojiphysio.com.** Every web-only answer
   (21 non-brand queries) omits Goji, and brand answers say the site has no
   prices or hours. Places data carries Goji where it is used. Third-party
   roundups decide the web-only answers.
2. **Roundup and directory presence.** Both engines lean on Sassy Mama, Little
   Steps, Women's Weekly, Expat Living, Honeykids, HelloPhysio, WhatClinic,
   Fresha and ClassPass. Goji is in none of the pages cited.
3. **ChatGPT pairs prices across services.** The llms.txt source is fixed
   (#233). The same two prices still share a sentence on
   `/womens-health-physiotherapy-singapore/` (FAQ and body), `services.ts` and
   two blog posts.
4. **Postnatal, prenatal, condition and paediatric queries:** Goji is absent
   on both engines for diastasis (ChatGPT), prolapse, C-section, perineal,
   mastitis, menopause, Schroth, scoliosis, torticollis, DDH, clubfoot and
   back pain. Competitors are cited from dedicated condition pages.
5. **Pelvic floor service page LCP 5.3s** (lab).

## Next, by tier

**A — loop:**
- #233 `llms.txt`: one line per home-visit price. All checks green,
  **merged**.
- This audit PR (`tier-a`).

**B/C — owner (normal PRs, evidence in the description):**
- #234 Prenatal classes post: SEO title "Prenatal and Antenatal Classes in
  Singapore". Only the meta title changes, but `src/content/blog/*.md` is
  outside the tier A allow-list, so the gate counts it as tier C. Open for
  the owner.
- Same price split on `/womens-health-physiotherapy-singapore/` (FAQ line
  124 and body ~328), `src/lib/services.ts` and the two blog posts
  (`postnatal-physio-home-visit`, `medisave-insurance-for-physiotherapy`),
  so $330 and "home visit" never share a sentence. No price changes.

**Owner / operator:**
1. **Check whether gojiphysio.com is in the web index Claude searches.**
   Search "goji physio" on a few engines Claude might use (e.g.
   search.brave.com) and, if missing, submit the site where that engine
   allows it. The loop cannot tell which index Claude uses.
2. **Pitch the roundups the engines cite** (status:
   `../partnerships/roundup-outreach.md`): Sassy Mama's pelvic-floor experts
   list, Little Steps' physiotherapy and pregnancy-physio pages, Women's
   Weekly, Expat Living, Honeykids' kids-physio list. Add WhatClinic and
   Fresha listings.
3. **ChatGPT logged-in series:** sign ChatGPT in to the Chrome profile by hand
   (Memory, "Reference record history" and "Connector search" off) if the
   logged-in trend should resume. Otherwise the logged-out series continues.
4. `gh auth setup-git` on tidepool (pushes still use the
   `credential.helper` override).
5. Carried over: GBP categories + review asks, Instagram/LinkedIn website
   link, old Squarespace takedown.

**C — Charles (AGENTS.md method rules, proposed here; the loop doesn't edit
it):**
- *Google on tidepool:* "No Google browser checks (owner decision
  2026-11-16). Google organic comes from Search Console `terms.json`:
  position, clicks and impressions per AEO query, written to
  `aeo-google-gsc.json`. Queries with no impressions are 'not ranking'. AI
  Overviews and the Maps pack are not measured."
- *Claude UI:* "claude.ai no longer has a web search toggle in '+'; search
  runs by default. Record whether each answer used places search, web search
  or neither."
- *ChatGPT logged out:* "`?q=` auto-sends again (16 Nov); check for the 'Log
  in' button before every send. Long answers need about 30s, and the page
  sometimes hangs and leaves the query unsent; reload and send again."
- *Tier gate:* "Run `tier_gate.py` after committing. Before the commit it
  compares an empty diff and always says tier A."
- Carried over: "Monthly loop" heading vs the weekly cadence; sitemap
  `lastmod`; promote `title_length` to ERROR in `check_dist.py` (no
  offenders since #226).
