# Website — conventions

The Goji public website: **Astro** (static output) on **Cloudflare Pages**,
**live in production at gojiphysio.com** since the Squarespace cutover
(directory name "prototype" is historical). `/styleguide` remains the design
QA surface (noindexed).

> **This subtree owns the repo's only Node/npm build step**, on purpose. The
> rest of the repo is deliberately no-build (the Flask dashboard is inline
> HTML/CSS/CDN-JS). Astro is the exception because the public site is a
> multi-page content site with shared archetypes (services, areas of care,
> condition pages, bios) where component reuse is the whole point. Node is
> scoped to this directory; `node_modules/`, `dist/`, `.astro/` are gitignored.
> Astro + npm + Cloudflare Pages are all free (honours repo "Free/DIY first").

## The look lives in one file
`src/styles/tokens.css` is the single knob. Colour, type scale, spacing, radius,
shadow, and layout are all CSS custom properties. To retheme (warmer, softer,
bigger), edit tokens — do **not** hardcode hex/px in components. Components
reference *role* aliases (`--bg-page`, `--cta-bg`, `--berry`), not raw values,
so a token change reflows everything (styleguide is the QA surface).

## Hard rules (inherited from repo + marketing AGENTS.md)
- **Every CTA is a tracked link.** Route through `go.gojiphysio.com/<slug>` via
  the `cta()` helper / Button `slug` prop (`src/lib/links.ts`). Never publish a
  raw `wa.me` / Plato URL, never the internal `dashboard.*` domain. Only slugs
  that exist in `LINK_SLUGS` (`business-intelligence/scripts/dashboard/app.py`)
  are exposed today: `web-wa`, `web-book` (the Book CTA points at our own `/book`
  form via `web-book`, not Plato). A new CTA needs its slug added there first.
- **Compliance is a hard constraint** (`marketing/strategy/03-compliance-guardrails.md`).
  Applies to placeholder copy too: no cure/outcome/time guarantees, no
  superlatives ("best/leading/No.1"), no comparative claims, no before/after
  imagery, **no patient testimonials by default** (Lane A). `QuoteSurface` is
  for the brand promise, not a testimonial.
- **Voice/style:** warm, plain, educational. Regular dashes (no emdashes), no
  emojis in brand copy, **never italic** (enforced in `base.css`).
- **Condition pages carry a clinician byline.** Every `conditions` entry sets a
  `reviewer: { name, slug }` (the reviewing physio, from the source doc). The
  detail template renders a "Reviewed by <name>" line linking to `/team/<slug>`
  and emits `reviewedBy` in the MedicalWebPage JSON-LD. Strip the source doc's
  italic reviewer/status/SEO-slug/structured-data notes and inline CTA — the
  template supplies the H1, byline, and CTA.
- **Mobile-first.** Most reach is on a phone. Base CSS before `@media`; check
  down to ~375px.
- **Branch & PR to `main`** — never push to `main` directly.

## SEO/GEO rules (from the 2026-07 review — full map in `../../seo/seo-geo-review.md`)
- **Per-page schema is required**, by page type: conditions emit MedicalWebPage
  + reviewedBy (from `reviewer`) + BreadcrumbList + FAQPage; services emit
  Service + Offer + BreadcrumbList + FAQPage (frontmatter `faqs`); team pages
  emit enriched Person. New page types define their schema before merging.
- **Condition FAQPage is parsed from the body**: keep the exact format
  `## Frequently asked questions` with `### <question>` blocks — other
  heading levels (e.g. `####`) or bullet questions silently emit no FAQPage.
- **Every condition page carries a byline** via `reviewer: { name, slug }`
  frontmatter; the template renders "Reviewed by <name>" linking to
  `/team/<slug>` and emits `reviewedBy` in the MedicalWebPage JSON-LD.
- **Meta descriptions ≤160 chars.**
- **Only claim a physical presence at Lentor.** Wider reach is "home visits
  across Singapore" — no neighbourhood pages implying a clinic elsewhere.
- **Update `public/llms.txt` in the same PR** as any page/service/price/team
  change — it is the canonical machine brief for AI answer engines.
- **Ad final URLs are direct site URLs, never `go.gojiphysio.com` links**
  (Google disallows redirector final URLs); on-page CTAs stay go-links.

## Assets
Logos in `public/brand/` are **copies** of the source of truth at
`business-intelligence/design/brand_assets/`. Re-sync if the brand updates.
Photos are real, consented clinic/practitioner images in production — no stock,
no before/after. Components show branded placeholders until photos land.

## Run it
See `README.md`. `npm install` then `npm run dev` (hot reload). `npm run build`
+ `npm run preview` is the Cloudflare-Pages-parity dry run (serves `dist/`).

## Roadmap (remaining)
Active focus (see `HANDOFF.md` for status): design polish (via `tokens.css`),
a blog (Astro content collection at `src/content/blog/` with an index + post
template) seeded with backdated posts — the biggest open GEO lever — and an
enquiry-form handler (free/DIY, a Pages Function feeding the front-desk Leads
pipeline). Deploy, content porting, SEO/schema and the Squarespace cutover are
done. Capture new rules here as they surface.
