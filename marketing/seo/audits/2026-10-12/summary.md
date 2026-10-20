# SEO / AEO audit — baseline, 2026-10-12/13

First run of the loop in `../../AGENTS.md`. Query set: `../../aeo-queries.json`
(v1, 45 queries). Technical detail: `technical.md`. Raw results: `aeo-*.json`.

## Scoreboard (baseline)

| Engine | Variant | Measured | Goji named | Cited via gojiphysio.com |
|---|---|---|---|---|
| ChatGPT (gpt-6-thinking, Temporary + Unpersonalized) | sg-context | 45 | **20** (17/42 non-brand) | 13 in-answer (+5 map card only) |
| Claude (claude.ai Incognito, Opus 5.5) | sg-context | 45 | **14** | 1 |
| Google AI Overview | uule=Singapore | 35 (CAPTCHA) | **10** of 30 AIOs | 7 |
| Google local pack | uule=Singapore | 35 | **12** of 26 packs (#1 on 9) | n/a |
| Google organic page 1 | uule=Singapore | 35 | **6** | 6 |
| Claude WebSearch tool (reference only, US-located) | none | 45 | 3 (brand only) | 0 |

Not measured: Google `paeds-clubfoot` → `brand-what` (10 queries, CAPTCHA);
`sg-ip` variant (no SG IP this run).

## What the engines say

- **Local + brand are won.** Lentor queries: Goji #1 on every engine. Brand
  queries: #1 on ChatGPT and Claude.
- **The wedge is lost in AI answers despite Maps wins.** Goji is #1 in the
  Google local pack on 7 of 11 wedge queries but in the AI Overview on 3.
  Engines frame Embrace and Calyx as "the dedicated women's health clinics"
  and Goji as "best if you're in the north".
- **Condition queries go to dedicated pages.** Calyx, KKH/SingHealth and
  Physio Down Under win pelvic-floor, incontinence, prolapse, PGP, menopause.
  Goji's condition pages that *are* cited (C-section, perineal tear, DDH,
  torticollis) are answer-first; the rest are not yet picked up.
- **Roundups drive Claude's answers.** Little Steps, Expat Living, Women's
  Weekly, Sassy Mama. Goji is in none of them.
- **Uncontested:** mummy-and-baby, postnatal home visit, C-section, perineal
  tear, blocked ducts, torticollis — Goji already ranks or nobody does.
- **General questions** (cost, referral, first visit) go to Physio & Sole,
  HealthHub and hospitals. Goji has no page shaped for them.

## Accuracy of what engines say about Goji

Correct: address, phone, Mon–Sat hours, all prices. Gaps/odd framing:
ChatGPT "relatively recent opening… shorter public track record"; Claude
"couldn't find pricing" (prices are on the site); home visits credited to
other clinics; ChatGPT links a **raw `wa.me`** for Goji (not on our site —
likely Instagram bio or GBP; untracked clicks).

## Technical (from `technical.md`)

- Fixed during this audit: hub `/womens-health-physiotherapy-singapore` was
  404 since 2026-08-07 (#132).
- Open: 22 meta descriptions >160 chars; homepage has no `<h1>`; 44 internal
  link targets 308 to the trailing-slash URL; clinic JSON-LD lacks `@id`,
  `logo`, `geo`; `llms.txt` misses 15 pages; 4 services lack FAQPage; heavy
  images (260 KB logo on every page, ~530 KB clinician photos); no sitemap
  `lastmod`; apex https → http://www hop; Core Web Vitals unmeasured (no PSI key).
- Clean: all sitemap URLs 200 with self-canonicals, JSON-LD parses, every AI
  and search crawler gets 200.

## Fix plan by tier

**A — loop ships (one PR per concern):**
1. Meta descriptions ≤160 on 22 pages (restating the reviewed lede).
2. Homepage `<h1>`.
3. Clinic JSON-LD: `@id`, `logo`, `geo`; reference it by `@id` from Service/Person.
4. `llms.txt` sync (15 missing pages), with prices and home-visit coverage stated plainly.
5. Internal links: condition → owning service page; service ↔ hub; trailing slashes in hrefs.
6. Image weight: logo and clinician photos to WebP at display size.

**B — Cheryl reviews:** FAQs for Clinical Pilates, MSK, paediatric, S&C;
answer-first ledes on pelvic-floor/incontinence/prolapse/PGP/menopause condition
pages; question-shaped pages for cost, referral and first visit (first-visit
draft already in review); publish the three blog drafts.

**C / operator:** sitemap `lastmod` (astro.config); `PSI_API_KEY` secret;
pitch Little Steps / Expat Living / Sassy Mama roundups; find and replace the
raw `wa.me` link (Instagram bio / GBP) with `go.gojiphysio.com/ig-wa` / `gbp-wa`;
Bing Places; apex redirect hop (DNS, accepted in July).

## Follow-up, 2026-10-19/20: real-Singapore IP + Google Business Profile check

New series `sg-ip` (verbatim queries from a NordVPN Singapore IP, memory off),
plus the 10 Google queries the CAPTCHA blocked and a recheck of the 26 Google
queries that showed a Maps pack. Chris updated the Business Profile ~15 Oct.
Files: `aeo-chatgpt-sg-ip.json`, `aeo-claude-ai-sg-ip.json`,
`aeo-google-2026-10-19.json`.

| Engine | sg-context (12 Oct) | sg-ip (20 Oct) | Cited via gojiphysio.com |
|---|---|---|---|
| ChatGPT | 20/45 | 17/45 | 13 (2nd most-cited domain after KKH) |
| Claude | 14/45 | 13/45 | 0 |

By cluster (named, sg-context → sg-ip): ChatGPT wedge 8→4, conditions 3→5;
Claude wedge 3→5, conditions 3→2, paeds 1→0. Brand and local unchanged.
Different method, so this is a second series, not a trend.

**Google (US IP + uule Singapore, same method as 12 Oct):**
- Brand queries (first measurement): Goji #1 organic on all 3; "what is goji
  physio" gets an AI Overview built entirely from gojiphysio.com, with correct prices.
- Maps pack, 26 queries: none improved; Goji dropped on 9 (e.g. women's physio
  1→3, women's health physio 1→out, home visit 1→out, pelvic pain 1→out) and
  held #1 only on Lentor MRT. AI Overview mentions 7→2. Embrace now leads most
  women's-health packs; Calyx and Spine and Pelvis Clinic newly appear.
- One week after a profile edit is too soon to call. Packs move day to day, and
  large profile edits can briefly dip rankings while Google re-reviews them.
  Recheck in the November run before acting on it.
- Profile as Google shows it: 5.0 from 24 reviews, category "Physical therapy
  clinic", new "Identifies as women-owned" attribute.

**Framing:** Claude now groups Goji with "dedicated women's health clinics"
(diastasis, incontinence) and dropped last week's "also handles general and
sports cases" caveat, but still describes it by location ("best if you're in
the north") and never credits home visits, Mummy & Baby or paediatrics. On
brand queries Claude still builds from an Instagram mirror and a staff
LinkedIn ("couldn't find pricing… book via Instagram"), although Brave ranks
gojiphysio.com #1 for "goji physio". No wrong facts about Goji from ChatGPT.

**Implications:**
- Keep up non-incentivised review asks (24 reviews today); next run, record competitors' review counts to see whether volume explains the pack order.
- Put the website and tracked WhatsApp link first in the Instagram bio and on LinkedIn: that is what Claude reads for brand questions.
- Check the Business Profile's primary/secondary categories against Embrace's and Calyx's.
- The roundup outreach in the ops doc matters more than before: Google's AI Overviews now build "top clinics" lists from Homage, Sassy Mama and Singapore Motherhood.
