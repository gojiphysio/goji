# Marketing Asset Templates - Specification

The set of reusable templates to build (themed with `../design-system/design-system-brief.md`) so the operator can produce on-brand assets fast. Each spec lists purpose, size, structure, and the lane (clinical vs fitness) it typically serves. Every output passes the lane-aware checklist in `../strategy/03-compliance-guardrails.md`.

Design priorities: mobile-first, on-screen text on all video, the berry-dot motif as the consistent signature, education-first framing.

## Sizes reference

| Use | Aspect | Pixels |
|---|---|---|
| Instagram Reels / Stories / TikTok | 9:16 | 1080 x 1920 |
| Instagram feed (carousel/static) | 4:5 | 1080 x 1350 |
| Instagram square | 1:1 | 1080 x 1080 |
| Google Business Profile post | ~1:1 / 4:3 | 1200 x 1200 |
| Email header | wide | 1200 x 600 |
| Landing page hero | wide | 1600 x 900 |

---

## 1. Instagram Reel cover / title frame (9:16)
- **Purpose:** the hook frame for educational Reels (wedge + MSK).
- **Structure:** bold one-line hook (e.g. "Is leaking after birth normal?"), small Goji mark, Linen/White or warm-photo background, Deep Red accent dot. Title in top two-thirds (avoid bottom UI zone).
- **Lane:** mostly A (education). Keep "can help," never "cure."

## 2. Educational carousel (4:5, 5-8 slides)
- **Purpose:** the save-worthy authority format. One idea, broken into steps.
- **Structure:** Slide 1 hook; slides 2-N one point each with berry-dot bullets and simple diagrams; final slide soft CTA ("Questions? Message us" / "Book a women's-health assessment") + logo.
- **Variants:** "Is this normal?" series, "3 things about [condition]," "What to expect at your first visit," "Returning to exercise after birth."
- **Lane:** A. Final-slide CTA stays educational/consult-oriented, not a clinical promo.

## 3. Practitioner intro / credibility card (4:5)
- **Purpose:** put a trusted face to the brand (the trust engine).
- **Structure:** practitioner photo, name, credentials/registration title, special interest, one warm line in brand voice.
- **Lane:** A. Factual credentials only; no superlatives.

## 4. "What we treat" / service card (4:5 or 1:1)
- **Purpose:** plain-language service explainers.
- **Structure:** service name, who it's for, what a session involves, berry-dot points, soft CTA.
- **Lane:** A for physio services (factual, no guarantees); B for general Pilates/S&C classes (can carry an offer).

## 5. Fitness / movement offer card (4:5, 9:16) - Lane B
- **Purpose:** the freer lane - founding-member, intro class, "return to movement" bridge.
- **Structure:** energetic but on-brand; clear offer and CTA; movement imagery.
- **Lane:** B. May include offers/promotions. Must NOT attach a clinical treatment claim.

## 6. GBP post template (1200x1200)
- **Purpose:** 2-3x/week local-discovery posts (repurpose Reels/carousels).
- **Structure:** clean image + short headline + CTA button mapping (Book / Call / Learn more). Education, services, hours, or a tip.
- **Lane:** both.

## 7. Email template (1200 wide, modular)
- **Purpose:** nurture + education + reactivation.
- **Structure:** header (logo on Linen), one hero education block, optional secondary block, CTA, footer (address, hours, WhatsApp, unsubscribe). Modular blocks reusable across sends.
- **Lane:** A content stays educational; B content may carry offers.

## 8. WhatsApp message snippets (text + optional image)
- **Purpose:** the SG booking/nurture workhorse.
- **Structure:** short, warm, plain-text templates: greeting/auto-reply, FAQ quick-replies, appointment reminder, gentle reactivation, post-visit check-in. Consent-first.
- **Lane:** both; keep clinical replies factual.

## 9. Condition / service landing page block kit (web)
- **Purpose:** capture "physio near me" + condition/neighbourhood search intent and convert to booking.
- **Structure:** hero (condition + reassurance + book CTA), "is this you?" symptoms, how Goji helps (education, no cure claim), what to expect, meet the team, FAQ, location/hours, booking. NAP consistent with GBP.
- **Pages to build first:** post-partum recovery, pelvic floor, back pain, neck/shoulder. Then: pre-natal, active-aging, Clinical Pilates, S&C.
- **Lane:** A for condition pages (educational framing); B for the Pilates/S&C pages.

## 10. Workshop / event kit
- **Purpose:** promote and run workshops (e.g. "Returning to exercise after birth").
- **Structure:** announcement post (4:5 + 9:16 + GBP), registration page block, on-screen slide template (reuse the brand slide deck), follow-up email.
- **Lane:** A (educational workshop framing).

## 11. Quote / testimonial surface (4:5) - use with care
- **Purpose:** social proof, only when compliant.
- **Structure:** Deep Red background, Linen White text, light logo.
- **Lane:** A. Only for testimonials given directly to Goji, unedited, consented; never before/after; never reposted from a patient's own account. When unsure, do not use - prefer an education card.

## 12. Stat / "did you know" card (1:1, 4:5)
- **Purpose:** myth-busting and education with a big number.
- **Structure:** big Deep Red number, Earth Brown label, source line.
- **Lane:** A. Cite credible sources; no embellished claims.

---

## Build order (for Claude Design)

1. Carousel (#2), Reel cover (#1), GBP post (#6) - the weekly workhorses.
2. Practitioner card (#3), service card (#4), stat card (#12) - authority set.
3. Fitness offer (#5), workshop kit (#10) - the campaign drivers.
4. Email (#7), WhatsApp snippets (#8) - nurture.
5. Landing page block kit (#9) - the conversion surface.
6. Testimonial surface (#11) - last, gated on compliance sign-off.
