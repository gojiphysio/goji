# Design System Brief - for Claude Design app

A brief to build Goji's marketing design system in the Claude Design app. Source of truth is the official Goji Brand Guidelines (designer: Annie Lye). This brief translates the brand into a working system for social, web, and print marketing assets.

Use this to generate: a token set, a component library, and the asset templates specified in `../assets/asset-templates-spec.md`.

## Brand essence

- **Who:** Goji - women's and family physiotherapy and fitness, Singapore.
- **Promise:** "We are not here to fix you. We help you feel confident in your body again."
- **Personality:** premium, modern, expert. Warm. Clinical without coldness.
- **Feeling a design should evoke:** calm confidence. Trust. Capability. A reassuring expert, not a cold clinic and not a hype gym.

## Color tokens

| Token | Name | Hex | Role |
|---|---|---|---|
| `--color-primary` | Deep Red | `#91171D` | Brand accent: dots, callouts, key numbers, CTAs. Full-bleed only on testimonial/closing surfaces. |
| `--color-ink` | Earth Brown | `#3C1E1F` | Primary text. |
| `--color-linen` | Linen White | `#F7F2E0` | Primary background / warm surface; secondary text on dark. |
| `--color-accent` | Midnight Blue | `#176591` | Sparing accent: secondary data series, signal moments. |
| `--color-surface` | White | `#FFFFFF` | Content background. |

Rules:
- Deep Red is an **accent**, not a fill area. Exceptions: testimonial and closing surfaces may use Deep Red as a full background (with Linen White text + the light logo).
- Linen White and White are the working backgrounds.
- Earth Brown is the text default.
- Midnight Blue is used sparingly.
- Maintain WCAG AA contrast: Earth Brown on Linen/White passes; on Deep Red use Linen White text.

## Typography

- **Display:** Plus Jakarta Sans SemiBold (per brand guideline). Inter Bold is the simpler single-family fallback used in the existing slide template.
- **Body:** Inter Regular. Inter Bold for emphasis. Never italic (against brand spec).
- Both are Google Fonts (render natively in Slides/web).
- **Type scale (suggested):** Display 40-64, H1 32-40, H2 24-28, Body 16-18, Caption 13-14. Generous line-height on body (1.4-1.6).
- Titles: one short sentence. Lead with the insight or outcome.

## Logo system

Four transparent variants exist in the BI repo `design/brand_assets/`:
- `logo_main_transparent.png` - GOJI wordmark, Earth Brown with Deep Red "O" (light backgrounds).
- `logo_light_transparent.png` - wordmark in Linen White with Deep Red "O" (dark/red backgrounds).
- `logo_with_tagline_transparent.png` - horizontal lockup with "Women's and Family Physiotherapy" (covers, hero).
- `logo_mark_transparent.png` - the standalone "O" mark (avatars, favicons, small spaces).

Rule: use the variant that matches the background. Maintain clear space around the logo; never stretch or recolor.

## Signature motif

- **The berry dot** - the Deep Red "O" / berry mark doubles as a bullet and accent dot. Use it as the bullet style, as a list marker, and as a small accent on numbers/CTAs. It is the brand's recognizable visual signature - use it consistently.

## Voice in design (microcopy)

- Warm, plain, expert. Short sentences. Lead with the patient's experience.
- Educational over promotional. "Here's what's happening and how we help," not "best clinic, book now, limited offer."
- **No emdashes** - use regular dashes only (project style).
- No emojis in brand-voice copy unless a specific playful context calls for it.

## Components to build in Claude Design

1. **Color + type token set** (as above).
2. **Logo lockups** (the four variants, with clear-space rules).
3. **Buttons / CTAs** - primary (Deep Red), secondary (outline Earth Brown), with the berry-dot accent option.
4. **Bullet/list style** using the berry dot.
5. **Stat / big-number block** - Deep Red number, Earth Brown label (KPI and "did you know" stats).
6. **Quote / testimonial surface** - Deep Red background, Linen White text, light logo (use only for compliant, consented testimonials).
7. **Education card** - title + 3-5 berry-dot points on Linen/White, room for an image.
8. **Image + text split** - half-bleed photo + story column.
9. **Practitioner intro block** - photo, name, credentials, special interest (the credibility component).
10. **CTA / contact block** - booking prompt, address, hours, WhatsApp.

## Imagery direction

- Real clinic, real practitioners, real (consented) patients over stock. Specificity builds trust; generic stock reads as "any clinic."
- Warm, natural light. Calm, capable, not clinical-cold and not hyped-gym.
- Women and families centered; show movement and strength as well as care.
- **Compliance:** no before/after framing in any marketing imagery. Consent on file for any identifiable person.

## Accessibility & platform notes

- On-screen text on all video (most viewers watch sound-off).
- Mobile-first: design for the phone; most reach is on Instagram/GBP on mobile.
- Keep safe margins for Reels/Stories (avoid the bottom ~250px UI zone and top profile zone).

## Deliverable from Claude Design

- A published design system (tokens + components above).
- The set of export-ready templates in `../assets/asset-templates-spec.md`, themed with this system.
- Export presets sized per the asset spec (square, portrait 4:5, vertical 9:16, GBP, email header, landing hero).
