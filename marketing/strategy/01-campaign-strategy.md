# Goji 90-Day Top-of-Funnel Strategy

The master strategy. Built on Goji's actual patient book (live data, 2026-05-29), Singapore market research (`02-market-research.md`), and the two-lane compliance model (`03-compliance-guardrails.md`). Execution arc is in `04-90-day-plan.md`.

## The overarching objective

**Become THE name for women's and family physiotherapy and fitness in Singapore.**

That is a multi-year brand goal. This 90-day campaign is the opening move: establish Goji as the most trusted, most visible women's-and-family physio voice in its catchment, and convert that authority into visits, active patients, and bookings.

## North-star KPIs (from the Goji BI dashboard)

1. **Number of visits** - appointments delivered (`fct_appointment`).
2. **Number of active patients** - distinct patients with a delivered service in the period (cohort metrics).
3. **Bookings** - dollar value of packs/sales (`fct_invoice_line`).
4. **Discovery Rank Score** - the % of priority patient questions where Goji appears in the top 5 across Google, ChatGPT, Gemini, Claude, TikTok, and Instagram. Tracked weekly via the Discovery Rank Sweep routine on the ops dashboard. This is the leading indicator for discovery — the commercial three are the lagging outcomes. **Not yet instrumented; build task for Week 4.**

Everything below is in service of all four.

## What the data says (and why the strategy is shaped this way)

Live Plato pull, 2026-05-29 (n=72 patients, 310 appointments in 2026). Numbers will drift; verify in the BI dashboard before reporting.

- **82% of patients (known sex) are female.** The women's positioning is reality, not aspiration.
- **Age: 53% are 30-44; 24% are 65+.** A post-partum/active-mum core, plus a real active-aging cohort. "Family" is supported (mums centre, parents and kids around them).
- **Top condition is Musculoskeletal (26 tagged). The women's pelvic/perinatal cluster sums to ~26 as well** (post-partum 10, pre-natal 5, pelvic-girdle-pain 5, pelvic-incontinence 3, prolapse 2, plus others). **MSK and women's health are co-largest segments.**
- **Delivery is physio-dominant.** Of mapped appointments: Physio ~69%, Pilates ~13%, S&C ~12%, Home Visit ~6%. Fitness (Pilates + S&C) is ~12% of all appointments. (49% of appointment codes were unmapped - treat fitness % as a floor and fix the BI mapping.)

**Conclusion:** lead with clinical authority (education) in the two real demand segments, spearhead the brand with the defensible women's-health wedge, and use fitness as a conversion/retention adjunct rather than the primary reach driver.

## Positioning

**Goji helps women and their families feel confident and capable in their bodies - through expert physiotherapy and movement, led by clinicians who get it.**

- **Category we are claiming:** women's and family physiotherapy (with movement/fitness as the bridge to lasting strength).
- **Brand promise (from the clinic's own voice):** "We are not here to fix you. We help you feel confident in your body again."
- **Tone:** premium, modern, expert. Warm. Clinical without coldness. Lead with the insight or the patient outcome, not the setup.
- **Distinctiveness:** most Singapore clinics bolt women's health onto general physio. Goji is built women-first, family-wide, and movement-integrated. That combination is the wedge.

## Ideal patient (ICP) and the four pillars

We market to a sharp primary ICP and support it with three further pillars.

### Spearhead ICP - the post-partum / women's-health mum
30-44, recently had a baby or planning to, dealing with pelvic floor, diastasis, pelvic-girdle pain, or "I don't feel like myself / strong again." Emotionally high-intent, high-share, underserved by general clinics. This is the brand's sharp point and where we win category ownership.

### Pillar 1 - Women's pelvic & perinatal health (THE WEDGE) - Lane A
The distinctiveness engine. Education-first content on pelvic floor, post-partum recovery, pre-natal care, returning to exercise safely. Drives brand authority, partnerships (gynae, confinement, doulas), and the most defensible position.

### Pillar 2 - Musculoskeletal physio (THE VOLUME ENGINE) - Lane A
The biggest single segment and broadest search demand (back, neck, shoulder, knee, sports/desk injuries). Fills the schedule. Education content here earns the most reach and the most bookings by volume. Not glamorous, but it pays the bills.

### Pillar 3 - Movement & fitness: Clinical Pilates + S&C (THE ADJUNCT) - Lane B
The freer lane. Used for: (a) the "return to movement" bridge out of rehab, (b) compliant offers (founding-member, intro classes), (c) retention and LTV. A supporting conversion layer, not the main reach driver — it is only ~12% of delivery today. **Pilates and S&C are a relationship-extension tool for existing patients, not a top-of-funnel campaign.** Do not lead any top-of-funnel copy with fitness. Pilates is genuinely attractive to millennial women and is worth acknowledging as part of the offering, but treat it as an adjunct that keeps patients in the ecosystem after physio — not a way to acquire new ones.

### Pillar 4 - Active-aging & family (THE QUIET PILLAR) - mixed lanes
24% of patients are 65+. Light-touch content on staying strong and mobile with age, plus the family breadth (kids, partners, parents). Low effort, real returns, reinforces "family."

## Channel strategy

Foundation already exists (website, Instagram, Google Business Profile, email/WhatsApp list), so this is optimize-and-scale, not cold start.

| Channel | Role | Lane emphasis |
|---|---|---|
| **Instagram (Reels + carousels)** | Primary reach + authority. Practitioner-led education. | Lane A education (wedge + MSK), Lane B for fitness offers |
| **Google Business Profile** | Highest-leverage local discovery. Posts 2-3x/week, reviews, photos, booking link. | Both |
| **Local SEO + website** | Capture "physio near me" + condition/neighbourhood intent. Condition landing pages. Primary: **Lentor** (home base) + Singapore-wide wedge terms. **Katong downgraded 2026-07-13** to secondary/content-only (no physical presence there; reached via SG-wide content, island-wide home visits, ads — see `../seo/seo-geo-review.md` §3). | Both |
| **Email + WhatsApp** | Nurture and retention. WhatsApp is the SG booking/reminder default (~98% open). | Both |
| **Partnerships & referrals** | Gynae, confinement, doulas, lactation, prenatal studios. The post-partum referral ecosystem. | Lane A wedge |
| **Workshops & events** | In-clinic and partner-hosted sessions; baby fairs. Trust at scale. | Wedge + fitness |
| **Paid (modest)** | Amplify winners; capture high-intent search. Compliance-safe. | Google search (both); Meta retargeting + Lane B fitness offers |

See `content-engine/channel-playbooks.md` for how to run each.

## Budget recommendation

You were unsure on budget. For a new clinic with an existing foundation and Singapore's ad constraints, the right posture is **organic-led with a modest, compliance-safe paid layer** that scales as we learn. Organic (content + GBP + SEO + partnerships) does the heavy lifting; paid amplifies what already works.

Indicative monthly paid media (excludes content production and event/booth costs):

**Meta advertising restriction:** "pelvic floor" and "pelvic health" are flagged as non-advertisable by Meta Business Suite. All pelvic/women's-health content stays organic. Paid budget on Meta goes to MSK terms and branded only, or Lane B fitness offers. Plan accordingly.

| Month | Paid media (SGD) | Allocation |
|---|---|---|
| 1 | 800 - 1,200 | ~70% Google Search (high-intent: "women's physio singapore", "postnatal physio", "physiotherapy [neighbourhood]", "back pain physio Singapore", branded). ~30% Meta retargeting of site/IG visitors (MSK and general — not pelvic terms). Learn. |
| 2 | 1,500 - 2,000 | Continue search. Add Meta retargeting + small Lane B fitness-offer prospecting (neighbourhood/parenting interests). Boost top organic education Reels. |
| 3 | 2,000 - 2,500 | Scale winners. Seasonal/event tie-in. Shift spend toward whatever booking source is cheapest per first-visit. |

Plus one-off budget for: a workshop/event or baby-fair presence, and light content-production gear (tripod, mic, ring light). Notes:
- **Google Search** for services is compliant as long as ad copy carries no prohibited claims (no "best", no guarantees, no discounts on Lane A).
- **Meta** Lane A creative must avoid before/after, testimonials, superlatives, guarantees. Lane B fitness offers have far more creative freedom.
- If budget must be near-zero, the campaign still works on organic + partnerships; paid only accelerates.

## The funnel and what we measure

```
REACH        impressions, video views, GBP discovery searches
  v
ENGAGE       saves, shares, profile visits, follows, GBP photo/post views
  v
ENQUIRE      DMs, WhatsApp messages, calls, form submissions, GBP booking-link clicks
  v
BOOK         first appointment booked   ->  (BI: bookings $)
  v
ACTIVE       first visit delivered      ->  (BI: number of visits, active patients)
  v
RETAIN       repeat visits, pack purchase, return-to-movement (Pilates/S&C)  -> LTV
```

**Leading indicators we own and review weekly** (operator dashboard, separate from BI):
- Instagram: reach, profile visits, new followers, saves, DMs received
- GBP: profile views, search appearances, direction requests, calls, booking-link clicks, new reviews
- Website: sessions, condition-page views, booking-page starts
- Enquiries: new WhatsApp/call/form enquiries (tag the source)
- **Conversion to first visit** (the join between TOFU and the BI north-stars)

**North-star review (monthly, from BI dashboard):** new patients, total active patients, visits delivered, bookings $, and treatment-mix shift.

## Targets

Set against the current baseline (~72 patients as of 2026-05-29). Fill exact baselines from the BI dashboard at kickoff; these are the shape of the ambition, to be calibrated:

| Metric | Baseline (fill from BI) | 90-day target |
|---|---|---|
| New patients / month | ___ | +50-100% by month 3 |
| Total active patients | ~72 | grow materially MoM |
| Visits delivered / month | ___ | track up with active patients |
| New enquiries / month | ___ | 3-4x by month 3 |
| Instagram reach / month | ___ | 3-5x (Reels-led) |
| GBP booking-link clicks + calls | ___ | 2-3x |
| Reviews (Google) | ___ | steady velocity, +2-4/month, never incentivised |
| Cost per first-visit (paid) | n/a | establish and drive down M1 to M3 |

Targets are deliberately framed as multiples of a small base. The discipline is: pick a few, instrument them, review weekly, and reallocate toward whatever produces first visits most cheaply.

## Operating model

In-house operator runs week-to-week delivery; Claude is the strategy + content engine. Cadence:
- **Monthly:** one batch film day (practitioner Reels), review BI north-stars, plan next month's themes.
- **Weekly:** publish to calendar, post GBP updates, review leading indicators, reply to all DMs/reviews, advance one partnership.
- **Always:** every asset passes the lane-aware pre-publish checklist in `03-compliance-guardrails.md`.

## Brand name (canonical — lock this across all surfaces)

- **Short form (Instagram, website, day-to-day):** Goji Physio
- **Full form (Google Business Profile, formal use):** Goji Women's and Family Physiotherapy
- **Suggested bio / handle format:** Goji Physio | Women's and Family Physiotherapy @ Lentor
- **Legal name (internal, hidden from marketing):** Goji Health Pte Ltd

NAP must be consistent: same name, address, phone on website, GBP, Instagram, LinkedIn, and any health directories. AI engines and Google hedge when entity names conflict; consistency is what earns confident citation.

## MOH licensing status (confirmed June 2026)

Goji is **not MOH-business-licensed**. The physiotherapists are individually **AHPC-licensed**. This means:
- The HCSA strict advertising list is **best practice**, not a legal requirement for Lane A.
- The **AHPC Code of Professional Conduct** is the binding floor — always applies.
- The Medicines (Advertisement and Sale) Act still restricts treatment-of-condition claims.
- Use Embrace Physiotherapy and Physio Down Under as benchmarks (both operate under the same licensing model in 2026).

Confirm borderline Lane A claim wording with AHPC or a healthcare lawyer before any pelvic/post-partum campaign goes live.

## What success looks like at day 90

- Goji is the most active, most credible women's-and-family physio voice in its catchment on Instagram and Google.
- A repeatable content engine the operator runs without heavy lift.
- 3-5 live referral partnerships in the post-partum ecosystem.
- Measurable lift in enquiries and first visits, with a known cost-per-first-visit for paid.
- A clear, data-backed plan for quarter two.
