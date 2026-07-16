# Marketing — conventions

This directory holds the 90-day campaign strategy, content plan, and guardrails.
When building anything that touches marketing data or the dashboard's Marketing
tab, honour these:

- **WhatsApp-first conversion.** Customers message before booking (high price
  point; they want to explain symptoms and discuss scheduling). The leading
  *intent* signal is a click-to-WhatsApp, not a booking-page visit. Every channel's
  CTA routes through the dashboard's `GET /r/<slug>` redirect; the channel-specific
  prefilled message also seeds the **enquiry log** source for attribution.
- **Glanceable headline metrics.** A few numbers with trends, readable at a glance.
  Deep analysis stays in the native platform.
- **Free / DIY data first.** Meta Graph API (Instagram), Google Search Console
  (SEO), Google Business Profile (local). Defer paid rank-tracking and generative-
  visibility tools until the free path is exhausted.
- **Priority SEO terms** (from `strategy/01-campaign-strategy.md` /
  `strategy/04-90-day-plan.md`): *women's physio singapore, postnatal physio,
  pelvic floor physiotherapy, physiotherapy [neighbourhood], physio near me,
  branded.* The full **keyword → page map, GEO conventions and SEO audit**
  live in `seo/seo-geo-review.md`; the **live Google Ads campaign spec** is
  `ads/google-ads-campaign-plan.md` (mechanics in `ads/google-ads-playbook.md`).
  We own **both brand names**: "Goji Women's and Family Physiotherapy"
  (canonical/structured) and "Goji Physio" (shorthand) — naming rules in the
  review doc §2.
- **Compliance is a hard constraint.** `strategy/03-compliance-guardrails.md`
  (Singapore healthcare-advertising rules) governs all copy and claims — check it
  before writing any patient-facing or ad content.
- The Marketing tab's WIP cards are the **seams** for live integrations; see
  `../business-intelligence/scripts/dashboard/AGENTS.md`.
