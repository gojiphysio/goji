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
- **The SEO/AEO loop** (scheduled audit, approval tiers, AEO measurement
  protocol, what an agent may self-merge) is governed by `seo/AGENTS.md`.
- **Compliance is a hard constraint.** `strategy/03-compliance-guardrails.md`
  (Singapore healthcare-advertising rules) governs all copy and claims — check it
  before writing any patient-facing or ad content.
- **Watercolour social clips** (Reels, Stories, feed, GBP) are made in `assets/watercolor-studio/` (open `index.html`; exports MP4/PNG). Its engine is a copy of the Goji design system bundle: re-copy it when the system changes rather than editing it here.
- The Marketing tab's WIP cards are the **seams** for live integrations; see
  `../business-intelligence/scripts/dashboard/AGENTS.md`.

- **Goji GTA episodes.** Use `video-production/skills/goji-gta-video/SKILL.md`
  for the recurring PS2/Singapore series. Preserve cast and location references;
  all people, including background NPCs and reflections, share the same PS2
  rendering standard. A matched last still does not preserve motion: use the
  runtime's supported video context and review the seam. Model capability claims
  must be checked on the exact runtime; record complete usable actions and all
  retries before choosing a renderer. The skill's bible distinguishes inherited
  choices from proposed camera/style defaults. Keep its installed copy in sync.
  The user's selected renderer is H3 with video reference; H3 indexed still
  guides can suit simpler scenes. Apply the skill's per-shot guidance routing.
  For San Andreas-specific appearance or behaviour, use the skill's
  `references/san-andreas-reference.md`: retain source-platform provenance and
  distinguish inspected footage, documented mechanics and proposed Goji values.
  Do not present an unrendered motion preset as measured PS2 physics.

- **Approved recurring vehicles.** For future Goji GTA episodes, reuse CONFRONT v3 and GRIP v2 from `assets/goji-girl/vehicle-references/README.md`; preserve their fictional branding, unbadged bodies and S-prefixed plates. The series bible links the exact approved images.
