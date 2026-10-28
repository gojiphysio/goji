# Goji Marketing - Top-of-Funnel Campaign

A 90-day top-of-funnel campaign to make **Goji** the name for women's and family physiotherapy and fitness in Singapore.

**Goji Health Pte. Ltd.** - women's and family physiotherapy + fitness clinic (gojiphysio.com). New clinic (opened ~April 2026). Services: Physiotherapy, Clinical Pilates, Private Pilates, Strength & Conditioning, Home Visits.

> "We are not here to fix you. We help you feel confident in your body again."

## The campaign in one paragraph

We lead with our sharpest, most defensible wedge - **post-partum and women's health physiotherapy** (pelvic floor, diastasis recti, pre/post-natal recovery, safe return to fitness) - to own a category most Singapore clinics only bolt on. The clinic already has the foundation (website, Instagram, Google Business Profile, contact list), so this is an optimize-and-scale play, not a cold start. Growth is organic-led (practitioner education content, local discovery, partnerships, community) with a modest, compliance-safe paid layer. Everything is built around Singapore's strict healthcare advertising rules - read `strategy/03-compliance-guardrails.md` before publishing anything.

## North-star KPIs (from the Goji BI dashboard)

1. **Number of visits** (appointments delivered)
2. **Number of active patients** (distinct patients with a delivered service in period)
3. **Bookings** ($)

See `strategy/01-campaign-strategy.md` for the full funnel and leading indicators.

## How this project is organized

```
.
|-- README.md                          (this file - start here)
|-- strategy/
|   |-- 01-campaign-strategy.md        The master strategy. Read first.
|   |-- 02-market-research.md          Singapore market intelligence, sourced.
|   |-- 03-compliance-guardrails.md    SG healthcare advertising rules. NON-NEGOTIABLE.
|   `-- 04-90-day-plan.md              Month-by-month + weekly sprint plan.
|-- seo/
|   `-- seo-geo-review.md              SEO + GEO audit, keyword->page map, AI-answer strategy.
|-- ads/
|   |-- google-ads-campaign-plan.md    The live Google Ads campaign spec (launch-ready).
|   `-- google-ads-playbook.md         Beginner how-to for the Ads UI.
|-- website/
|   `-- (site)                         The LIVE production site (Astro, Cloudflare Pages).
|-- design-system/
|   `-- design-system-brief.md         Brief for Claude Design app (brand tokens, components).
|-- assets/
|   `-- asset-templates-spec.md        Specs for every marketing template we need.
|-- content-engine/
|   |-- content-pillars-and-calendar.md  Pillars, cadence, 12-week calendar, idea bank.
|   `-- channel-playbooks.md             How to run IG, GBP, email/WhatsApp week to week.
`-- partnerships/
    `-- partnerships-and-events.md     Referral targets, outreach, SG baby-fair calendar.
```

## Locked decisions (2026-05-29)

| Decision | Choice |
|---|---|
| Primary wedge | Post-partum / women's health |
| Budget posture | Organic-led + modest compliance-safe paid (see strategy for $) |
| Execution model | In-house operator runs delivery; Claude is the content + strategy engine |
| Existing foundation | Website live (Astro on Cloudflare Pages since 2026-07; Squarespace deprecated), Instagram active, Google Business Profile, email/WhatsApp list |
| Brand names (2026-07-13) | Own BOTH: "Goji Women's and Family Physiotherapy" (canonical/structured) + "Goji Physio" (shorthand) |
| Katong (2026-07-13) | Downgraded to secondary, content-only target — see `seo/seo-geo-review.md` §3 |
| Design system | Built in Claude Design app from the official Goji brand guidelines |

## Status

- [x] Market research (SG compliance, post-partum channels, social best practice)
- [x] Campaign strategy + KPI framework
- [x] 90-day plan
- [x] Design system brief
- [x] Asset template specs
- [x] Content engine (pillars, calendar, playbooks)
- [x] Partnerships + events plan
- [ ] Operator review + baseline numbers filled from BI dashboard
- [ ] Confirm Goji's licensable status with MOH (decides which ad ruleset governs)
- [ ] Design system built in Claude Design app
- [ ] Month 1 execution begins
