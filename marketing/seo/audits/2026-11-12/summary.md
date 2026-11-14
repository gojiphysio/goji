# SEO / AEO audit — 2026-11-12

**No AEO engine and no Search Console data this run.** This was the first
unattended run on tidepool (Mac mini, headless). The reasons:

- **Google: skipped.** The IP is SG, `AS56300 MyRepublic Ltd.` (a home ISP, not
  a VPN), so the `sg-ip` series applied and Google was in scope. The only
  browser available was headless Chrome with a fresh signed-out profile
  (no gstack, no Playwright, Claude in Chrome not connected). On query 1
  Google returned its `/sorry/` CAPTCHA page, as AGENTS.md predicts for
  headless.
- **ChatGPT (logged-out series): skipped.** chatgpt.com returned a Cloudflare
  "Just a moment" challenge to headless Chrome on the first load. The
  logged-in series also needs a signed-in profile, which this machine doesn't
  have.
- **Claude (Incognito): skipped.** It needs a signed-in claude.ai profile,
  and agents never sign in.
- **Search Console: n/a.** `gcloud` and `bq` are not installed on tidepool.

Measured: `live/` (live_audit.py) and `dist.json` (build + check_dist.py on
`main` @ 69f3bb5). No `aeo-*.json` this run.

## Scoreboard (shared ids only)

| Engine | Metric | 11 Nov | 12 Nov |
|---|---|---|---|
| ChatGPT (logged out, sg-ip) | Goji named | 12/45 · 14/47 | **not measured**: Cloudflare challenge (headless) |
| ChatGPT | gojiphysio.com cited | 14/47 | **not measured** |
| Claude (Incognito) | Goji named | not measured | **not measured**: no signed-in profile |
| Google AIO / Maps pack / organic | — | not measured | **not measured**: CAPTCHA on query 1 (headless) |
| Search Console | 28d vs prior 28d | not measured | **n/a**: no `gcloud`/`bq` on this machine |

## What moved (technical)

- **Fixed and live:** `/team/` no longer 404s (#223), and the postpartum title
  is no longer flagged (#222). Live audit: 83 sitemap URLs, 84 link targets,
  **0 errors** (11 Nov: 1).
- **AI/search crawlers:** 40/40 bot × page fetches returned 200 with no
  Cloudflare challenge (GPTBot, OAI-SearchBot, ChatGPT-User, PerplexityBot,
  ClaudeBot, Claude-SearchBot, Googlebot, Bingbot, Meta ×2). `llms.txt`
  served.
- **Build check:** 0 errors, 1 WARN (11 Nov: 2): the Zaobao press title is
  82 chars. Fixed in #226 (tier A); with that merged, `check_dist` has 0
  warnings.
- **Still open:** the sweatboxyoga link (on `/blog/prenatal-classes-singapore/`)
  gives 502 to the audit's UA. With a browser UA, both that URL and the
  sweatboxyoga homepage return 200 today, so it looks like a bot block, not a
  dead link. Leave it. `PSI_API_KEY` is still unset, so Core Web Vitals were
  not measured.

## Top gaps

1. **No engine data on tidepool.** This run can only measure engines if a
   browser that passes Google's and Cloudflare's checks is available: gstack's
   headed browser, or Claude in Chrome with a separate signed-out profile for
   Google. Without one, every run on this machine records nothing for AEO.
2. **The home-visit price mix-up (S$330 vs S$380) has a likely source.** In
   `public/llms.txt:33`, one sentence reads "...$260 in-clinic or $380 as a
   home visit; the Mummy & Baby assessment is $330 in-clinic or $450 as a home
   visit". The two prices also appear together in `src/lib/services.ts`,
   `src/pages/services/index.astro`, `src/pages/womens-health-physiotherapy-singapore.astro`
   and the blog posts `postnatal-physio-home-visit` and
   `medisave-insurance-for-physiotherapy`. ChatGPT may be attaching $330 to
   "home visit" from that sentence. This is not verified until ChatGPT is
   measured again.
3. No Search Console trend at all since the loop started.

## Next, by tier

**Owner / operator:**
1. **Make the engines measurable on tidepool:** install gstack (headed
   browser, signed-out profile for Google), or connect Claude in Chrome. Sign
   claude.ai and ChatGPT in by hand, with ChatGPT's Memory, "Reference record
   history" and "Connector search" off.
2. **Search Console:** install the Google Cloud SDK on tidepool, then run
   `gcloud auth login` as hello@gojiphysio.com.
3. **Git push on tidepool** has no credential helper. This run pushed with
   `-c credential.helper='!gh auth git-credential'`. Run `gh auth setup-git`
   once to make that permanent.
4. Set the `PSI_API_KEY` repo secret.
5. Carried over: GBP categories + review asks, Instagram/LinkedIn website
   link, old Squarespace takedown, roundup outreach.

**B/C — Cheryl + Charles (prices are tier C):** in `llms.txt` and the cost
paragraphs listed above, separate the home-visit price from the Mummy & Baby
price. For example, put them in two sentences, and write "home visit
(physiotherapy): $380" so that $330 never sits next to "home visit". No
price changes.

**C — Charles:**
- Ratchet: once #226 merges, `title_length` has no offenders. Promote it to
  ERROR in `check_dist.py` `LEVEL`.
- New method rule for `AGENTS.md` (proposed here; the loop doesn't edit it):
  *"Headless with no gstack or Claude in Chrome: Google (CAPTCHA) and
  logged-out ChatGPT (Cloudflare challenge) both fail on request 1; record
  them as skipped, don't retry. Check ipinfo `org`: a home ISP in SG is not a
  VPN."* Also carried from 11 Nov: logged-out ChatGPT `?q=` no longer
  auto-sends, and Web search sits under "+".
- Also: the "Monthly loop" heading in AGENTS.md says monthly, but the loop now
  runs weekly. One of the two should change.
- Still open: sitemap `lastmod`.

**A — loop:** #226 (Zaobao press title): all checks green (SEO tier gate,
Site checks `dist`, Cloudflare Pages), but auto mode refused `gh pr merge`.
It is left **open for the owner to merge**. This audit PR is open for the same reason.
