# Google Ads campaign plan (launch spec)

**Status: LIVE (launched 2026-07-16).** Campaign `Goji - Search - Non-brand`
(id 24037615913): Enabled · Search · SGD 20/day · Maximize clicks + SGD 3.50
CPC cap · Singapore (Presence) · auto-tagging ON · final-URL suffix set · 4 ad
groups · 25 campaign negatives. Conversion action live (`AW-18230150966` +
booking label). Most keywords cleared the healthcare-policy review via exemption;
a few tail terms may stay limited. The prior Smart campaign "Goji Physio
Singapore" is paused; the first `[DEPRECATED]` Search build was removed. Next:
day-3 search-terms check (§11).

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

**AG1 — Pelvic floor / women's health**
```
"pelvic floor physiotherapy"      [pelvic floor physiotherapy singapore]
"pelvic floor physio"             [pelvic floor physio near me]
"pelvic floor therapy"            "pelvic physiotherapist"
"womens physiotherapy"            [womens physio singapore]
"womens health physio"            "prolapse physio"
"incontinence physiotherapy"      "physio for incontinence"
"best pelvic floor physio singapore"   <- targeting only; ad copy never says "best"
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
"exercise during pregnancy"       "pubic pain during pregnancy"
"birth prep physio"               "epino physio"
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
