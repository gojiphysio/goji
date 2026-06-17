# Website prototype — conventions

The Goji public website, rebuilt off Squarespace. **Astro** (static output),
bound for **Cloudflare Pages**. This is currently a *design-system prototype*:
a living styleguide (`/styleguide`) + one composed homepage (`/`) so we can land
on a look before porting all content and going to production.

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
  are exposed today: `web-wa`, `web-plato`. A new CTA needs its slug added there
  first.
- **Compliance is a hard constraint** (`marketing/strategy/03-compliance-guardrails.md`).
  Applies to placeholder copy too: no cure/outcome/time guarantees, no
  superlatives ("best/leading/No.1"), no comparative claims, no before/after
  imagery, **no patient testimonials by default** (Lane A). `QuoteSurface` is
  for the brand promise, not a testimonial.
- **Voice/style:** warm, plain, educational. Regular dashes (no emdashes), no
  emojis in brand copy, **never italic** (enforced in `base.css`).
- **Mobile-first.** Most reach is on a phone. Base CSS before `@media`; check
  down to ~375px.
- **Branch & PR to `main`** — never push to `main` directly.

## Assets
Logos in `public/brand/` are **copies** of the source of truth at
`business-intelligence/design/brand_assets/`. Re-sync if the brand updates.
Photos are real, consented clinic/practitioner images in production — no stock,
no before/after. Components show branded placeholders until photos land.

## Run it
See `README.md`. `npm install` then `npm run dev` (hot reload). `npm run build`
+ `npm run preview` is the Cloudflare-Pages-parity dry run (serves `dist/`).

## Roadmap (not built yet)
Active focus (see `HANDOFF.md` for the ordered plan): design polish (via
`tokens.css`), a blog (Astro content collection at `src/content/blog/` with an
index + post template) seeded with backdated posts, and a free Cloudflare Pages
deploy. Then: hosting hardening (+ per-PR preview URLs), porting
`../site-capture/content-inventory.md` + `../condition-pages/` + 3 bios, an
enquiry-form handler (free/DIY, a Pages Function feeding the front-desk Leads
pipeline), SEO/schema, and DNS cutover from Squarespace. Capture new rules here
as they surface.
