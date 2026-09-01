# Google Ads campaign plan (launch spec)

**Status: LIVE (launched 2026-07-16).** Campaign `Goji - Search - Non-brand`
(id 24037615913): Enabled · Search · SGD 20/day · Maximize clicks + SGD 3.50
CPC cap · Singapore (Presence) · auto-tagging ON · final-URL suffix set · 4 ad
groups · 25 campaign negatives. Conversion action live (`AW-18230150966` +
booking label). Most keywords cleared the healthcare-policy review via exemption;
a few tail terms may stay limited. The prior Smart campaign "Goji Physio
Singapore" is paused; the first `[DEPRECATED]` Search build was removed.
**First-pass readout + broad-match fix done 2026-07-22 — see §12.** Next:
re-measure after ~5–7 days of clean traffic.

Ad copy **reviewed by Cheryl + team 2026-07-16** and incorporated (new
keywords across AG2–AG4; "leakage"→"incontinence" framing; "tummy
gap"→"diastasis"). "Treatable" was reviewed and kept. Three of their edits
exceeded Google's char limits and were trimmed to fit while preserving intent
(AG1 headline → "Incontinence Is Treatable"; AG1 desc drops redundant "urinary
leakage"; AG4 headline → "Physio Near Upper Thomson") — reconfirm these three
with Cheryl if the exact wording matters. This is the live campaign spec —
what to actually build in the Google Ads UI. The how-to mechanics (where
each screen is, why each rule exists) live in `google-ads-playbook.md`;
SEO/keyword context lives in `../seo/seo-geo-review.md`. Update this file
whenever the running campaign changes — it is the source of truth for what
should be live.

Compliance: every headline/description here follows
`../strategy/03-compliance-guardrails.md` (no superlatives, no
cure/outcome/time guarantees, no comparisons, "can help" framing). Plain
prices are allowed. Do not edit copy in the UI without rechecking.

## 1. Why paid, and how it complements SEO

- Paid covers the **pre-rank window**: the wedge pages are new and the site
  was homepage-only in the index at audit (review doc §1 P0) — ads put the
  pages in front of high-intent searchers now, while organic catches up.
- **Google Search is the only paid lever for the wedge**: Meta blocks
  pelvic-floor/pelvic-health ad content, Google does not.
- The **search-terms report is SEO research we pay for once**: weekly,
  winners become keywords + rows in the review doc's keyword map; junk
  becomes negatives (§9).

## 2. Launch gates (all UI/env work, no code)

1. Campaign type is **Search** (pause any Smart/PMax) — playbook §1.
2. Conversion action `Booking confirmed` created — playbook §6a.
3. `PUBLIC_GADS_ID` + `PUBLIC_GADS_BOOKING_LABEL` set in Cloudflare Pages
   (Production) + redeploy — playbook §6b. Verify with a test booking.
4. **Auto-tagging ON** (Admin → Account settings).
5. Campaign **final URL suffix**:
   `utm_source=google&utm_medium=cpc&utm_campaign={campaignid}&utm_term={keyword}`
   — the `{keyword}` ValueTrack lands the matched keyword in
   `marts.web_session_events.utm_term`, giving keyword-level attribution in
   BigQuery before the ROADMAP Phase 5 transfer views exist.

## 3. Campaign structure

One campaign: **"Goji - Search - Non-brand"**. Four ad groups, each pointed
at its money page (Quality Score = message match):

| # | Ad group | Final URL |
|---|---|---|
| 1 | Pelvic floor / women's health | `https://www.gojiphysio.com/services/pelvic-floor-physiotherapy` |
| 2 | Postnatal / postpartum | `https://www.gojiphysio.com/services/postpartum-physiotherapy` |
| 3 | Prenatal / pregnancy | `https://www.gojiphysio.com/services/prenatal-physiotherapy` |
| 4 | General physio / near me / Lentor | `https://www.gojiphysio.com/physiotherapy-lentor` |

Rule: ad final URLs are always **direct site URLs**, never
`go.gojiphysio.com` links (Google disallows redirector final URLs;
attribution comes from gclid + the URL suffix, and on-page CTA clicks are
still tracked via the site's own go-links).

## 4. Keywords (phrase + exact only, never broad)

> **Match-type incident (2026-07-22).** The live build had two keywords as
> **broad** and duplicated across all four ad groups — `physio for pregnant
> women` and `pregnancy pelvic pain treatment`. Broad match generated **80% of
> impressions and 71% of spend** on junk (pilates studios, gynae/GP searches,
> competitor names, how-to queries) and drove **0 bookings**. Fixed: deleted all
> 8 broad instances, re-created each as **phrase in Prenatal/pregnancy only** (a
> pregnancy searcher must not land on the pelvic-floor/postnatal/general page).
> Changing match type = delete + re-create (new policy review), so re-create only
> where the keyword belongs — don't convert duplicates. `exercise during
> pregnancy` **paused** (informational intent, 0 engagement). Winners added from
> the first search-terms pass are marked ⊕ below.

**AG1 — Pelvic floor / women's health**
```
"pelvic floor physiotherapy"      [pelvic floor physiotherapy singapore]
"pelvic floor physio"             [pelvic floor physio near me]
"pelvic floor therapy"            "pelvic physiotherapist"
"womens physiotherapy"            [womens physio singapore]
"womens health physio"            "prolapse physio"
"incontinence physiotherapy"      "physio for incontinence"
"best pelvic floor physio singapore"   <- targeting only; ad copy never says "best"
"pelvic health physiotherapy" ⊕   "pelvic floor dysfunction" ⊕
"pelvic floor therapist singapore" ⊕
```

**AG2 — Postnatal / postpartum**
```
"postnatal physio"                [postnatal physiotherapy singapore]
"postpartum physio"               "postpartum physiotherapy"
"post pregnancy physio"           "postnatal check physio"
"diastasis recti physio"          "abdominal separation treatment"
"c section recovery physio"       "physio after birth"
"returning to sports postpartum"  "low back pain postpartum"
"pelvic pain pregnancy"
```

**AG3 — Prenatal / pregnancy**
```
"prenatal physiotherapy"          [prenatal physio singapore]
"pregnancy physio"                "antenatal physiotherapy"
"pregnancy back pain physio"      "pelvic girdle pain physio"
"pregnancy pelvic pain treatment" "physio for pregnant women"
"pubic pain during pregnancy"     "pelvic girdle pain in pregnancy" ⊕
"birth prep physio"               "epino physio"
# "exercise during pregnancy" — PAUSED 2026-07-22 (informational intent)
```

**AG4 — General / near me / Lentor**
```
"physio near me"                  [physiotherapy near me]
"physiotherapy lentor"            "physio lentor"
"physiotherapy ang mo kio"        "physio upper thomson"
"physiotherapy clinic singapore"  "physiotherapist singapore"
"back pain physio singapore"      "neck and shoulder physio"
"physiotherapy upper thomson"     "physiotherapy sengkang"
"physiotherapy punggol"           "physiotherapy for elderly"
"physiotherapy in yio chu kang"   "physiotherapy in woodlands"
[physiotherapy yishun] ⊕          "home physiotherapy singapore" ⊕
```

## 5. Negative keywords (shared campaign list)

```
polyclinic        community hospital    hospital
chiropractor      chiro                 massage
sports massage    tcm                   诊所
government        subsidised            chas
medisave          free                  cheap
job               jobs                  vacancy
course            salary                internship
```
Brand negatives in this non-brand campaign (keeps brand traffic organic):
```
goji    "goji physio"    "goji physiotherapy"    "goji womens"
```
**Added 2026-07-22** (from search-terms pass): gynae/gynecologist/obgyn,
"female doctor"/"women's clinic" (they want an OB/GP, not physio), confinement,
osteopath/osteo, acupuncture, "bone setting"/sinseh/"chinese physician",
craniosacral/"myofascial release"/"dry needling"/cupping/gyrotonic,
emsella/ceragem, kegel(s), informational ("how to"/"what is"/exercises/
stretches/symptoms), and competitor clinic names. Full paste list is
`import/negative-keywords.txt` (source of truth).

**Pilates/yoga deliberately NOT negatived.** Clinical Pilates is a real Goji
offering. The junk was generic *fitness* Pilates ("pilates near me", "reformer")
— a $30–45/class buyer, wrong for physio-priced clinical Pilates. It only entered
via broad match, so deleting the broad keywords (§4) removed it without a
negative. If we ever buy Pilates paid, it's a **separate ring-fenced ad group +
its own landing page + own budget** (exact "clinical/rehab pilates" only), tested
after the wedge is proven — never blended into the physio ad groups.

Weekly ritual (§9) grows this list from real search terms.

## 6. Responsive Search Ads

One RSA per ad group to start (add a second variant after the first
search-terms review). Pin nothing; let Google rotate. All copy Lane A
compliant — **Cheryl reviews before launch**.

**AG1 — Pelvic floor / women's health**

Headlines (≤30 chars):
```
Pelvic Floor Physiotherapy      Women's Health Physio
AHPC-Registered Physios         1 Min From Lentor MRT
Private 55-Minute Sessions      Incontinence Is Treatable
First-Line Care, No Referral    Prolapse & Pelvic Pain Care
Book Online In Minutes          Ask Us On WhatsApp First
Home Visits Island-Wide         Open Mon-Sat, 8am To 8pm
```
Descriptions (≤90 chars):
```
Physio for incontinence, prolapse & pelvic pain. Private, unhurried, evidence-based care.
Assessment with an AHPC-registered physiotherapist at Lentor Modern, 1 min from the MRT.
A clear plan for symptoms many women are told to live with. Book online or WhatsApp us.
55-minute one-on-one sessions at $260. Home visits available across Singapore.
```

**AG2 — Postnatal / postpartum**

Headlines:
```
Postnatal Physiotherapy         Postpartum Recovery Check
Diastasis Recti Assessment      C-Section Recovery Support
Returning to Sports Postpartum  Bring Your Baby Along
Home Visits Island-Wide         1 Min From Lentor MRT
AHPC-Registered Physios         Book Online In Minutes
```
Descriptions:
```
Pelvic floor, diastasis and scar assessment, with a plan for your return to exercise.
Suitable after vaginal and Caesarean birth - weeks, months or years postpartum.
One-on-one care with physios experienced in women's health. Home visits island-wide.
Not sure what you need? Message us on WhatsApp and we will point you to the right session.
```

**AG3 — Prenatal / pregnancy**

Headlines:
```
Prenatal Physiotherapy          Pregnancy Aches? We Can Help
Pelvic Girdle Pain Care         Birth Preparation Sessions
Care Adapted To Your Stage      Stay Active In Pregnancy
1 Min From Lentor MRT           AHPC-Registered Physios
Book Online In Minutes          Home Visits Available
```
Descriptions:
```
Physiotherapy for pregnancy aches, pelvic pain and birth preparation, at any trimester.
One-on-one sessions adapted to your stage of pregnancy, with AHPC-registered physios.
Manage pain, keep exercising confidently and prepare your body for birth.
At Lentor Modern, above Lentor MRT. Home visits available across Singapore.
```

**AG4 — General / near me / Lentor**

Headlines:
```
Physiotherapy In Lentor         Physio Above Lentor MRT
Women's & Family Physio         Back, Neck & Knee Physio
Open Mon-Sat, 8am To 8pm        Physio Near Upper Thomson
Book Online In Minutes          Home Visits Island-Wide
Serving Ang Mo Kio & Bishan     WhatsApp Us Your Symptoms
```
Descriptions:
```
Physiotherapy at Lentor Modern, a 1-minute walk from Lentor MRT Exit 1 (TEL).
Women's, family, and musculoskeletal physio - one clinic, AHPC-registered physios.
Easy to reach from Ang Mo Kio, Yio Chu Kang, Upper Thomson, Springleaf and Bishan.
Book online or message us on WhatsApp first - we will recommend the right appointment.
```

## 7. Assets (extensions)

- **Sitelinks:** Book an appointment → `/book` · Pelvic floor physio →
  `/services/pelvic-floor-physiotherapy` · Conditions we treat →
  `/conditions` · Physiotherapy in Lentor → `/physiotherapy-lentor`
- **Callouts:** AHPC-Registered Physios · 1 Min From Lentor MRT · Home
  Visits Island-Wide · Open Mon-Sat 8am-8pm · Women's & Family Focus
- **Structured snippet (Services):** Pelvic Floor Physio, Prenatal,
  Postnatal, Paediatric Physio, Clinical Pilates, Schroth Scoliosis
- **Call asset:** +65 8377 0401 (clinic hours only)
- **Location asset:** link the GBP once claimed (P0 in the review doc)

## 8. Budget, bidding, geo

- **Budget (M1, per strategy/01):** ~70% of SGD 800-1,200/mo on Google
  Search → **SGD 19-28/day**. M2: ~SGD 35-47/day. M3: ~SGD 47-58/day,
  shifted toward whatever shows the cheapest cost-per-booking.
- **Bidding:** Maximize clicks with **max CPC cap SGD 3-4** until ~15-30
  tracked `Booking confirmed` conversions → **Maximize conversions** →
  add a tCPA once cost-per-booking is known.
- **Geo:** Singapore, location setting **"Presence"** only; +8-10 km radius
  around Lentor Modern with a positive bid adjustment. No separate Katong
  geo — Singapore-wide targeting already reaches East-side searchers
  (Katong is a content-only target; review doc §3).
- **Schedule:** optional; if enquiry response matters, weight to Mon-Sat
  8am-8pm.
- Expect wedge CPCs to be volatile at this budget — judge ad groups on
  cost-per-booking after conversions flow, not CPC.

## 9. Brand defense: monitor, don't spend

No brand campaign at launch. Goji ranks #1 organically for all brand
variants and no competitor brand-bidding was observed (review doc §2).
Brand terms stay as negatives here (§5).

**Weekly monitor** (part of the search-terms ritual): search "goji physio",
"goji physiotherapy", "goji women's and family physiotherapy" from a
Singapore device/VPN and check Auction Insights. **Trigger to reverse:** a
competitor ad appears on any brand query → launch a capped SGD 2-3/day
exact-match brand campaign (playbook §2 has the steps).

## 10. Measurement

- **Keyword → visit:** gclid + `utm_term={keyword}` →
  `marts.web_session_events` (utm_source=google, utm_medium=cpc).
- **Visit → booking:** `web_session_events.session_id` →
  `marts.booking_funnel_events` (carries gclid/utm through to
  `submitted`); `Booking confirmed` conversion fires in-platform with the
  service price as value.
- **Visit → WhatsApp intent:** landing-page WhatsApp taps log to
  `marts.link_click_events` (web-wa slug) joined via session — remember
  WhatsApp, not booking, is the leading intent signal (marketing/AGENTS.md),
  so judge ads on both.
- **Spend/impressions:** existing `google_ads` BQ Data Transfer feeds the
  dashboard's campaign card (`fetch_google_ads`); keyword/search-term-level
  BigQuery views are dashboard ROADMAP Phase 5.
- **Weekly search-terms ritual:** add booking-producing terms as keywords
  (and to the SEO keyword map), add junk as negatives, log anything
  surprising in this doc.

## 11. Launch runbook

- **Week 0 (gates):** §2 items; Cheryl signs off copy; GBP claim underway.
- **Week 1:** build campaign per §3-8; launch at SGD 20/day; check search
  terms after 3 days (broad-match leakage shows up fast even on phrase).
- **Week 2:** first search-terms pass (§10); verify conversions and
  `web_session_events` rows with utm_term are landing; kill any keyword
  with spend > SGD 15 and zero engaged sessions.
- **Week 3:** second RSA variant in the best-spending ad group; adjust
  radius bid based on where enquiries actually come from.
- **Week 4:** review vs the M1 budget; if ≥15-30 conversions, switch to
  Maximize conversions; write the month-1 readout (spend, CPC,
  cost-per-booking, search-term winners) into this doc.

## 12. First-pass readout (2026-07-22, days 1–6)

**Verified end-to-end in BigQuery** (`web_session_events`,
`booking_funnel_events`, `link_click_events`). The funnel machine is **sound**;
the only fault was targeting.

- **Tracking works.** Booking conversion tag (`AW-18230150966/t--8CKuH8LwcEL…`)
  is installed and armed — confirmed the `send_to` global loads at runtime.
  Google Ads showing **0 conversions is accurate**, not a bug. ⚠️ **Tag Assistant
  gives a false negative** on this site (Cloudflare blocks its fetcher → "timeout");
  verify with curl/runtime globals or a real test booking, not Tag Assistant.
- **Ads drove 0 bookings.** 47 paid sessions landed (gclid + utm_term capture
  100% OK) → **0 entered the booking funnel**, 1 WhatsApp tap. The 9 real
  on-site bookings since launch all came from **non-ad** sources (GBP `gbp-book`
  ×1, link-in-bio `bio-book` ×2, direct ×6) — none carried a gclid.
- **Cause = broad-match junk** (§4 incident), now fixed. Landing pages + CTAs +
  `/book` funnel dogfooded and healthy (clear CTAs, deep-link pre-selects the
  service, WhatsApp routes through the tracked go-link). No page fix needed.
- **Next:** let clean phrase keywords run ~5–7 days, then re-pull search terms +
  the BQ funnel and judge on cost-per-booking + WhatsApp taps. Before switching
  to Maximize Conversions, set a **campaign-specific goal = website booking
  action only** — the account still has Smart-campaign/GBP Local actions as
  Primary account-default goals (would misdirect Smart Bidding).

## 13. Month-2 readout (2026-09-01, covering 2026-07-16 → 2026-08-31)

**Verdict: targeting is fixed, conversion is not. The campaign is buying the
right traffic and that traffic does not book.** Pulled from the `google_ads`
BQ transfer + `marts.web_session_events` / `booking_funnel_events` /
`link_click_events`. Everything below is BigQuery-verified; no UI screenshots.

### Spend vs bookings

| Month | Spend | Clicks | CPC | `Book appointment` conv |
|---|---|---|---|---|
| Jul (from 16th) | SGD 330.55 | 191 | 1.73 | **1** |
| Aug | SGD 607.45 | 294 | 2.07 | **1** |

~SGD 948 for **2 bookings** ≈ **SGD 474 per booking** against a SGD 260 clinic
session. August nearly doubled July's spend and produced the same one booking.
Campaign ran all of August at the full SGD 20/day on `TARGET_SPEND`
(= Maximize Clicks), so it optimised for clicks and delivered clicks.

### The 78 "conversions" were not bookings

Account-wide conversions since June are dominated by
**`Local actions - Directions`** (36 in Jun, 39 in Jul) from the now-paused
Smart campaign, plus 1 `Clicks to call`. Only **2** `Book appointment`
conversions exist in the entire account. This is the §12 landmine confirmed:
the account-default Local goals are live and would misdirect Smart Bidding.
**Do not switch to Maximize Conversions before setting a campaign-specific
goal** (see §14).

### Targeting: fixed

August search terms are on-profile — *pelvic floor physiotherapy singapore,
physio near me, prenatal physiotherapy, pelvic organ prolapse*. The broad-match
junk of §12 is gone. Residual leakage is ~SGD 40/mo: competitor names
(*keo ran*, *yip wan hui*, *xuan kai*), wrong-geo (*physio orchard*,
*joo chiat*, *ang mo kio*, *jurong east*, *bedok*), and off-service
(*hydrotherapy*, *indiba*, *eswt*, *intellicare*). Negatives listed in §14.

### Where it actually dies: on-site conversion

| Cohort (Aug) | Sessions | Entered funnel | Booked |
|---|---|---|---|
| Paid (gclid) | 198 | 9 (4.6%) | 1 (0.51%) |
| Organic/other | 1,488 | 250 (16.8%) | 18 (1.21%) |

Paid visitors are **engaged, not bouncing**: 40–52s dwell, 70–74% scroll on the
money pages. They read the page and leave. `/physiotherapy-lentor/` — the #1
paid landing page — took **83 paid sessions and produced 0 funnel entries**;
across paid+organic it is 125 sessions → 1 entry.

Per ad group (Aug), the generic head-term group burns 59% of budget for nothing:

| Ad group | Spend | Clicks | Conv |
|---|---|---|---|
| General / near me / Lentor | 358.79 | 173 | **0** |
| Pelvic floor / women's health | 186.33 | 91 | **0** |
| Prenatal / pregnancy | 40.51 | 20 | **1** |
| Postnatal / postpartum | 21.82 | 10 | **0** |

### What is working: GBP, for free

Recovering channel via the go-link `cid` passthrough (August arrivals → booked):

| Origin | Arrivals | Bookings | Rate |
|---|---|---|---|
| **Google Business Profile** (`gbp-book`) | 69 | **6** | **8.7%** |
| Instagram bio (`bio-book`) | 53 | 1 | 1.9% |
| Website CTA (`web-book`) | 5 | 0 | — |

GBP converts ~17× better than paid and costs nothing. It has no dashboard card
and no owner. That is the highest-ROI gap on this list.

### Attribution: verified healthy (a correction)

An earlier pass suspected the on-site `?sid=` passthrough was missing because it
is absent from `curl`'d HTML. **It is not missing** — the decorator in
`BaseLayout.astro` runs client-side and appends `?sid=<session>&p=<path>` to
every `go.gojiphysio.com/web-*` link. Verified in a real browser. `sessionStorage`
survives the redirector round-trip (same origin), so paid sessions keep their
`session_id` through to `/book`. **The paid funnel numbers above are real, not an
attribution artifact.**

Caveat worth fixing: `link_click_events` counts bot traffic. 85 of 95 sid-less
`web-wa` taps have **no referer at all**, and the redirector logs crawler hits on
`/robots.txt` as a slug (167 rows in Aug). Filter bots before trusting tap counts.

### Organic search: still blind

`ads_PaidOrganicStats` is **empty** — Search Console is not linked to Google Ads,
and is not ingested into BigQuery either. 30 content pages are built for organic
with no visibility into impressions, position, or query. Unchanged since §12.

## 14. Action list (2026-09-01) — UI changes, in order

Do these in the Google Ads UI. Each is independent; 1–3 are the money savers.

### 1. Pause the "General / near me / Lentor" ad group (2 min)

Campaigns → **Goji - Search - Non-brand** → Ad groups → tick
**General / near me / Lentor** → Edit → **Pause**.

It spent SGD 358.79 in August (59% of budget) for 0 bookings across 173 clicks.
These are the most competitive, lowest-intent head terms in the account and we
lose them to bigger budgets. Freed budget flows to the wedge groups below.

### 2. Cut daily budget SGD 20 → SGD 8 (2 min)

Campaign → Settings → Budget → **SGD 8/day**.

Not a full pause: keeping it live preserves account history and Quality Score,
and the prenatal group is showing signal. At SGD 8/day the worst case is ~SGD
240/mo while the landing pages get fixed. Revisit once cost-per-booking is on
the dashboard.

### 3. Set a campaign-specific conversion goal (5 min) — **do before any bidding change**

Campaign → Settings → **Goals** → "Use campaign-specific goals" → select
**only** `Book appointment` (`AW-18230150966/t--8CKuH8LwcELaO6PRD`).
Deselect `Local actions - Directions` and `Clicks to call`.

Without this, the account-default Local goals stay Primary. Those are the 76
"conversions" in §13 and they are directions taps, not patients. Any future
switch to Maximize Conversions would optimise straight toward them.

**Stay on Maximize Clicks for now.** Only move to Maximize Conversions after
~15–30 `Book appointment` conversions — at current rates that is a long way off,
which is itself the argument for fixing the landing pages first.

### 4. Add negatives from the August terms pass (5 min)

Campaign → Settings → Negative keywords → add as **phrase** match. Also append
to `import/negative-keywords.txt` (source of truth) in the same change:

```
hydrotherapy      indiba          eswt            intellicare
"keo ran"         "yip wan hui"   "xuan kai"      "city osteopathy"
"movemed"         "physio & sole"
orchard           "joo chiat"     "ang mo kio"    amk
"jurong east"     jurong          bedok           tampines
hougang           yishun          novena          clementi
woodlands         bishan          "senior day care"   dementia
```

Geo negatives matter more than they look: we only have a physical presence at
Lentor (site AGENTS.md forbids implying otherwise), so a *physiotherapy bedok*
click can never convert. ~SGD 40/mo recovered, and it compounds.

### 5. Point the two surviving ad groups at their money pages (5 min)

Confirm final URLs — **direct site URLs, never `go.gojiphysio.com`** (Google
rejects redirector final URLs; on-page CTAs stay go-links):

| Ad group | Final URL |
|---|---|
| Pelvic floor / women's health | `https://www.gojiphysio.com/services/pelvic-floor-physiotherapy/` |
| Prenatal / pregnancy | `https://www.gojiphysio.com/services/prenatal-physiotherapy/` |
| Postnatal / postpartum | `https://www.gojiphysio.com/services/postpartum-physiotherapy/` |

Keep auto-tagging on (it is) so `gclid` keeps landing in `web_session_events`.

### 6. Link Search Console to Google Ads (5 min)

Tools → Setup → **Linked accounts** → Search Console → Link.

Populates `ads_PaidOrganicStats` (currently empty), which gives the paid-vs-
organic view per query: where we pay for a click we already rank for, and where
organic has impressions but no rank worth having.

### Not an Ads change, but the biggest win

GBP converts at 8.7% for free (§13) versus paid at 0.51%. Before spending more
on Ads, give Google Business Profile an owner: posts, photos, review velocity,
and the `gbp-book` CTA. It is already the best acquisition channel in the
business and nobody is running it.
