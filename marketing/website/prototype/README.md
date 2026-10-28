# Goji website — design-system prototype

Astro project that turns the Goji brand brief into real, reusable components.
Two pages to look at:

- **`/`** — a composed sample homepage (the "look" on a real page).
- **`/styleguide`** — every token and component, the reference + QA surface.

## Run locally

```bash
cd marketing/website/prototype
npm ci
npm run dev          # http://localhost:4321  (hot reload — edit and see instantly)
```

Then open `http://localhost:4321/` and `http://localhost:4321/styleguide`.

## Production-parity check (what Cloudflare Pages will serve)

```bash
npm run build        # outputs static site to dist/
npm run preview      # serves dist/ exactly as Cloudflare Pages would
```

## Tweaking the look

Everything visual is driven by **`src/styles/tokens.css`** — colours, type
scale, spacing, radius. Change a value there and the whole site (including the
styleguide) reflows. No component edits needed for global look changes.

## Layout

```
src/
  styles/tokens.css   # the single "look" knob (CSS custom properties)
  styles/base.css     # reset + element defaults
  lib/links.ts        # CTA slug -> go.gojiphysio.com/<slug> (tracked links)
  lib/site.ts         # address, hours, contact (NAP) constants
  layouts/BaseLayout.astro
  components/          # Button, BerryList, EducationCard, StatBlock, etc.
  pages/index.astro    # sample homepage
  pages/styleguide.astro
public/brand/          # logo PNGs (copies of business-intelligence/design/brand_assets)
```

See `AGENTS.md` for conventions (link tracking, compliance, the no-build
exception, etc.).
