# SEO + GEO review — gojiphysio.com

**Audited: 2026-07-13** (live Astro site on Cloudflare Pages). §1–2 are a
point-in-time audit — refresh monthly. §3–4 (keyword→page map, GEO
conventions) are the durable core — update them when pages or priorities
change, not on a schedule.

Related docs: compliance rules `../strategy/03-compliance-guardrails.md`
(governs ALL copy below), ads spec `../ads/google-ads-campaign-plan.md`,
GBP task list `../strategy/05-30-day-campaigns.md` (Campaign 2), Discovery
Rank Sweep `../strategy/05-30-day-campaigns.md` (Campaign 5).

> Research caveat: SERP observations below came from US-based web search on
> 2026-07-13. Singapore-localized rankings and the Maps local pack are not
> visible from there — treat positions as indicative and verify in Google
> Search Console + a Singapore device.

## 1. Prioritized actions

**P0 — do now**

| Action | Owner | Where |
|---|---|---|
| ~~**Fix inner-page indexation.**~~ **DONE (2026-07-14)** — GSC **Domain property `gojiphysio.com`** verified (auto, via Google Cloud DNS zone ownership); all inner pages 200 with correct self-canonicals, no `noindex`; `sitemap-index.xml` submitted (full URL required for a Domain property; may briefly show "Couldn't fetch" — transient, site is fetchable incl. as Googlebot) and Request-Indexing done on the 5 money pages. Root cause was discovery lag post-Squarespace-cutover, not a code fault. Watch the Pages report over the next 1–2 weeks. | ✓ operator | search.google.com/search-console |
| ~~Verify apex→www 301~~ **DONE (2026-07-14)** — `gojiphysio.com` 301s to www and lands on the Cloudflare Pages site with a valid cert. Note: the redirect is issued by **Squarespace** (apex A-records still point there), *not* a Cloudflare rule — DNS is on **Google Cloud DNS** (`ns-cloud-*.googledomains.com`), `www` CNAMEs to `goji-bgb.pages.dev`. Minor flaw: apex hops through `http://www` before Cloudflare upgrades to https (extra insecure hop; accepted, not worth a DNS migration). | ✓ verified | — |
| ~~Claim/complete **Google Business Profile**~~ **DONE (2026-07-14)** — listing set to "Goji Women's and Family Physiotherapy" from the fields banked in `gbp-listing.md` (NAP, categories, hours, compliant description, services, `gbp-book`/`gbp-wa` tracked links). **Ongoing (Campaign 2 Week-2):** 10+ real photos, seed Q&A, 2–3 posts/wk, non-incentivised review asks. | ✓ operator | GBP UI; `gbp-listing.md` |
| ~~Ship condition-page bylines + FAQPage schema, pelvic-floor service page, /physiotherapy-lentor, bio-URL 301s~~ **VERIFIED in branch (2026-07-14)** — all present, builds clean; built HTML emits MedicalWebPage+FAQPage+BreadcrumbList + visible "Clinically reviewed by" byline on conditions; `/physiotherapy-lentor` live; bio 301s in `public/_redirects`. **Not live until this PR deploys** (currently 404 in prod). | Repo | this PR |
| ~~Pelvic-floor service page HELD~~ **UN-HELD (2026-07-16)** — Kristy's reviewed copy applied, `draft: false`, hero photo added, back in build/sitemap/llms.txt, `relatedService` links restored. Ads AG1 unblocked. | ✓ done | `src/content/services/*` |
| Launch the non-brand Search campaign once conversion gates pass. All four ad-group pages (incl. pelvic-floor) are now live; import CSVs cover AG1–AG4. | Operator (Ads UI) | ../ads/google-ads-campaign-plan.md |
| ~~3 new service pages~~ **BUILT (2026-07-16)** — Paediatric Physiotherapy, Clinical Pilates ($180), Strength & Conditioning ($180). Paediatric price **confirmed $260/$330** (= "Initial Physiotherapy Consult $260" + "$70 home add-on" on the price card). **Remaining nice-to-have:** hero photos + FAQs for these 3 (text hero, no FAQPage yet). | Repo | `src/content/services/*` |
| **Services reorg (2026-07-16)** — categories are now: Pregnancy & Postpartum · General Health (pelvic floor, MSK, Schroth ×2) · Children · Holistic Care (Pilates, S&C). Mummy & Baby home price corrected $380→**$400** (price card = $330 + $70 add-on). | ✓ done | `config.ts`, `services/index.astro` |
| **MSK / General Physiotherapy page LIVE (2026-07-16)** — `/services/musculoskeletal-physiotherapy` set `draft: false` at operator's instruction + added to llms.txt. Copy was Claude-drafted (compliance floor cleared); **Cheryl's clinical-accuracy review still outstanding — do retroactively.** Targets AG4 MSK terms (back/neck/shoulder physio). | Repo + Cheryl (retro review) | `src/content/services/musculoskeletal-physiotherapy.md` |

**P1 — next 30 days**

| Action | Owner |
|---|---|
| **Blog** (Astro content collection) — the single biggest GEO content lever we lack. Competitors winning AI answers (Embrace, PhysioMatters) all publish. Start with question-phrased posts from the Discovery Rank prompt set ("Is leaking after birth normal?"). | Repo + Cheryl |
| Pitch the three roundups that own our SERPs: Sassy Mama pelvic-floor experts, Homage women's physio, Little Steps Asia pregnancy physio (see §4 citations table) | Operator |
| Bing Places + Apple Business Connect listings (free; Bing feeds ChatGPT answers) | Operator |
| GSC ingestion job → `marts.gsc_search_performance` (see §6) | Repo |
| Discovery Rank Sweep first baseline run (strategy/05 Campaign 5) | Operator + repo |
| Fix/annex the sgpdirectory.com auto-generated ACRA listing and the Lentor Modern mall listing — confirm NAP matches exactly | Operator |

**P2 — later**

- Per-page OG images; real photography alt-text sweep once photos land.
- Neighbourhood pages beyond Lentor only if search demand shows up in GSC
  (pattern proven by BMJ/Health2U `/ang-mo-kio/` pages) — same honesty rule:
  no fake presence claims.
- Review-velocity program once GBP is live (compliant: ask, never
  incentivize — strategy/03).
- Founder-name SERP: Cheryl's old employer profiles (UFIT, Rapid Physiocare)
  outrank her Goji bio. Ask for removal/update where stale; her Goji bio +
  LinkedIn should own her name.

## 2. Current-state audit (2026-07-13)

**Strong already** — canonical URLs on every page; `@astrojs/sitemap` +
robots.txt; site-wide MedicalClinic/LocalBusiness JSON-LD with NAP, hours,
geo, services; llms.txt; Squarespace 301 map; every CTA a tracked go-link;
first-party attribution beacon (`web_session_events` catches utm/gclid);
homepage FAQPage; condition pages already written in answer-block style
(plain-language, question-phrased H2s, FAQ sections).

**Found and fixed in this PR** — condition pages lacked bylines, dates and
FAQPage schema (now extracted from the body FAQ section at build time);
service FAQPage support existed but no service defined FAQs (now all 6 do);
no page existed for the #1 wedge head term (now
`/services/pelvic-floor-physiotherapy`); no local landing page (now
`/physiotherapy-lentor`); old Squarespace bio URLs `/cheryl-long` etc.
404'd (now 301s); Person schema was thin (now carries credentials,
specialties, sameAs); meta descriptions ran long (now ≤160 chars).

**Open gaps** — inner-page indexation (P0 above); GBP status unverified
from here; no blog; no GSC/GBP measurement (§6); no third-party citations
beyond two auto-generated listings (§4).

**Brand SERP (both names)** — Goji is #1 for "goji physio", "goji
physiotherapy singapore" and "goji women's and family physiotherapy".
Below position 1 is noise (a US "Goji Fitness", goji-berry products, Go
Physio UK/US variants, an employee LinkedIn at #2 on the formal name). No
competitor brand-bidding observed. Healthy — defend, don't spend (see ads
plan §brand-defense).

### Dual-name ownership rules

We own BOTH names. Canonical entity name everywhere structured:
**"Goji Women's and Family Physiotherapy"** — GBP business name, schema
`name`, llms.txt, every directory/citation. Everyday shorthand in titles
and copy: **"Goji Physio" / "Goji Physiotherapy"** — carried as schema
`alternateName` (both variants, emitted site-wide and on Person `worksFor`).
Every brand monitoring surface (SERP checks, ads brand negatives, Discovery
Rank prompts) covers: goji physio, goji physiotherapy, goji women's and
family physiotherapy, goji women's physio, goji physio lentor. NAP must be
byte-identical across site, GBP, and every citation.

### Competitor benchmark

| | Embrace Physiotherapy (Katong) | Physio Down Under (River Valley) |
|---|---|---|
| Position | #1 "women's physio singapore" (2 of top 3 with two pages) | Top-10 on wedge terms with homepage alone |
| Why they win | Deep keyword-targeted pages (`/services/womens-health-physiotherapy-singapore/`, `/what-we-treat/` hub + condition children), active blog, individual clinician pages, 5.0-rated GBP, PDF patient guide | Domain age (est. 2018, "Singapore's first dedicated pelvic health clinic"), citations (Expat Living feature, Fresha, Core Collective), niche authority |
| What we copy | Condition/service page depth (we now match), blog cadence, clinician-page E-E-A-T | Citation breadth, category-defining positioning line |
| What we don't | Their typo'd `/our-aproach/` slug; testimonial-led copy (our Lane A forbids) | Flat structure, indexed junk pages |

Also recurring across our SERPs: PSC Women & Children (strongest overall),
PhysioMatters, City Osteo, Health2Mama, Reiwa, Calyx, Milestone. Every
money keyword is won by a **dedicated page** or a **roundup** — never a
homepage-only generalist. That is the whole strategy in one sentence.

## 3. Keyword universe → page map (durable core)

Priority = where ranking #1 is both valuable and achievable. All pages
exist unless marked *(P1/P2)*.

**Local (highest conviction — win first)**

| Keyword | Target page | Status |
|---|---|---|
| physiotherapy lentor / physio lentor | /physiotherapy-lentor | **Already #1** (US-search caveat) — page hardens it |
| physio near me (searcher in Lentor/TEL corridor) | GBP listing + /physiotherapy-lentor | Blocked on GBP claim (P0) |
| physio ang mo kio / upper thomson / bishan | /physiotherapy-lentor (nearby section) | Dedicated pages only if GSC shows demand (P2) |

**Wedge, Singapore-wide (the fight)**

| Keyword | Target page |
|---|---|
| pelvic floor physiotherapy singapore, pelvic floor physio | /services/pelvic-floor-physiotherapy |
| women's physio singapore, women's health physio | / (homepage) + /services/pelvic-floor-physiotherapy |
| postnatal / postpartum physio singapore | /services/postpartum-physiotherapy |
| prenatal / pregnancy physiotherapy singapore | /services/prenatal-physiotherapy |
| mummy and baby assessment | /services/mummy-baby-assessment |

**Condition long-tail (11 pages, each owns its cluster + question variants)**

| Cluster | Target page |
|---|---|
| diastasis recti physiotherapy singapore, "how to fix abdominal separation" | /conditions/diastasis-recti |
| urinary incontinence physio, "is leaking after birth normal" | /conditions/urinary-incontinence |
| pelvic organ prolapse physio, "heaviness after birth" | /conditions/pelvic-organ-prolapse |
| c-section recovery physio, scar massage | /conditions/caesarean-recovery |
| pelvic girdle pain pregnancy, mummy's wrist | /conditions/pelvic-girdle-pain |
| (…same pattern for the remaining 6 condition pages) | /conditions/* |

**Scoliosis (uncontested niche)** — schroth therapy singapore, scoliosis
physio child → /services/schroth-scoliosis-children|adults.

**Quiet pillar (65+)** — menopause physio, osteoporosis exercise singapore
→ /conditions/menopause now; blog posts P1.

**Branded** — both names + variants → homepage. Organic-owned; ads
monitor-only.

Rule: one page per cluster, never two pages competing for one keyword; new
content targets a cluster in this map or adds a row in the same PR.

### Katong (downgraded to secondary, content-only — decision 2026-07-13)

Katong was a strategy-doc target because it is Embrace's catchment. Without
a physical presence there the local pack is unwinnable and a "Katong" page
would violate the honesty rule (only claim presence at Lentor). Katong
searchers are reached via: Singapore-wide wedge rankings above, the honest
island-wide home-visits line (site + llms.txt state East Coast coverage —
confirmed true), and SG-wide ads. Katong prompt variants stay in the
Discovery Rank sweep as a tracking signal only. `strategy/01` updated to
record this.

## 4. GEO (AI answer engine) strategy

What we saw in AI-flavoured SERPs: engines quote clinics with (a) dedicated,
typed, question-shaped pages, (b) named clinicians (PDU's "Monica/Rachel",
PhysioMatters' physios surface by name in AI summaries), and (c) third-party
corroboration (roundups, directories). Goji is already the machine-quoted
answer for "physiotherapy lentor" — the homepage is readable enough for
engines to lift NAP, services and billing. Extend that to the wedge:

1. **Entity consistency** — dual-name rules in §2; NAP byte-identical
   everywhere; llms.txt is the canonical machine brief (update it in the
   same PR as any page/service/price change — convention now in the website
   AGENTS.md).
2. **Schema conventions (required per page type)** — conditions:
   MedicalWebPage + author/reviewedBy Person + dates + BreadcrumbList +
   FAQPage (auto-extracted from the body's `## Frequently asked questions`
   / `### question` section — keep that exact format); services: Service +
   Offer + BreadcrumbList + FAQPage from frontmatter `faqs`; team: Person
   with hasCredential/knowsAbout/sameAs; site-wide: MedicalClinic +
   LocalBusiness with both alternateNames.
3. **E-E-A-T bylines** — every condition page shows "Clinically reviewed by
   Cheryl Long, Clinical Director · Last reviewed <date>" linking to her
   bio. Named clinicians are what AI answers cite. Bump `lastReviewed` when
   content is re-reviewed, not cosmetically.
4. **Answer-block content pattern** — short plain answer high on the page,
   question-phrased H2/H3s, FAQ section, no marketing filler before the
   answer. Condition pages already do this; the blog must too.
5. **Citations plan** (ranked by SERP evidence, all pitched with the formal
   name + identical NAP):

| Target | Why | Cost |
|---|---|---|
| Google Business Profile | The local entity anchor; feeds Maps + AI answers | Free |
| Sassy Mama pelvic-floor experts roundup | Ranks top-3 on "pelvic floor physiotherapy singapore" | Editorial pitch |
| Homage women's physio roundup | #2 on "women's physio singapore" | Editorial pitch |
| Little Steps Asia pregnancy physio roundup | Ranks on both pre/postnatal SERPs | Editorial/partner |
| Bing Places / Apple Business Connect | Feed ChatGPT & Apple Maps answers | Free |
| Fresha listing | Competitors' Fresha pages rank; free (booking commission — publish our own /book as primary) | Free |
| SPA clinic directory (physiotherapy.org.sg) | Authoritative professional citation | Via membership |
| sgpdirectory ACRA page + Lentor Modern mall page | Already exist — verify NAP accuracy | Free |
| theAsianparent / Expat Living / Honeycombers | Editorial features à la PDU's Expat Living piece | Pitch |

6. **Compliant review velocity** — steady, non-incentivised GBP review asks
   once GBP is live (mechanics in channel-playbooks.md; hard rules in
   strategy/03).
7. **Measurement** — Discovery Rank Score (strategy/05 Campaign 5) is the
   GEO north star; instrumentation sketch in §6.

## 5. "Rank #1" framing (compliance note)

Ranking #1 is an internal goal — fine in strategy docs, never in
patient-facing or ad copy ("best/leading/No.1" are hard NOs under the AHPC
floor, strategy/03). Bidding on a query containing "best" is targeting,
not claiming — allowed; the ad shown must not echo the superlative.

## 6. Measurement follow-ups (not in this PR)

- **GSC ingestion** — free API; mirror the `marketing_ingest` Cloud Run Job
  pattern (`business-intelligence/scripts/ingestion/`): daily pull of
  query/page/clicks/impressions/position → `raw_marketing.gsc_raw` →
  stg → `marts.gsc_search_performance(date, query, page, clicks,
  impressions, position)`. Powers a Marketing-tab SEO card + the weekly
  loop in §7.
- **Discovery Rank Sweep** — `marts.discovery_rank_snapshots(date, engine,
  prompt, appeared_top5, position, evidence_url)`; prompt set = strategy/05
  Campaign 5 list + brand variants (§2); weekly manual sweep first
  (free/DIY), automate later.
- **Ads keyword/search-term tables** — already planned as dashboard ROADMAP
  Phase 5; the campaign plan's `utm_term={keyword}` suffix meanwhile lands
  the matched keyword in `web_session_events` for free.

## 7. Cadence & ownership

- **Weekly (operator + Claude):** Ads search-term report → negatives + new
  keywords + additions to §3 map; GSC new-query scan (once ingested); GBP
  post published.
- **Monthly:** refresh §1–2 audit; Discovery Rank sweep trend; review
  citation pipeline.
- **Every content PR:** compliance pass (strategy/03), schema conventions
  (§4.2), llms.txt updated, keyword map row added/confirmed.
- Claude drafts; Cheryl clinically reviews every patient-facing string;
  operator owns Google/Cloudflare UIs.
