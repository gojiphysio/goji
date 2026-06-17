# Handoff — Goji website design-system prototype

Pick-up notes for continuing this work in a local session.

- **Branch:** `claude/trusting-franklin-itc74a` (all work is here; nothing merged to `main`).
- **Project root:** `marketing/website/prototype/`
- **Status:** Phase 1 complete — scaffolding + design system + a living styleguide
  and a composed sample homepage. No hosting, no content porting, no PR yet.

## What's built

- **Astro** static site (Node 22; see `.nvmrc`), bound for **Cloudflare Pages**.
- **`src/styles/tokens.css`** — the single "look" knob. All colour, type scale,
  spacing, radius, shadow, and layout are CSS custom properties. Edit values here
  and the whole site (incl. the styleguide) reflows. Components reference *role*
  aliases (`--bg-page`, `--cta-bg`, `--berry`), never raw hex/px.
- **Components** (`src/components/`): Button, BerryList, Section, ImageTextSplit,
  EducationCard, StatBlock, PractitionerCard, ContactBlock, QuoteSurface,
  LogoLockup, plus `layouts/BaseLayout.astro` (header/footer/fonts).
- **Pages:** `/` (sample homepage, real copy from `../site-capture/content-inventory.md`)
  and `/styleguide` (every token + component; the reference + QA surface).
- **CTAs** route through the tracked redirector via `src/lib/links.ts`
  (`web-wa`, `web-plato`). No raw `wa.me`/Plato links anywhere.

## Run it locally

Requires Node 20+ (22 recommended). From the repo root:

```bash
cd marketing/website/prototype
npm install
npm run dev            # http://localhost:4321  (hot reload)
```

Open **http://localhost:4321/** and **http://localhost:4321/styleguide**.
To tweak the look, edit `src/styles/tokens.css` and watch it reflow live.

Production-parity check (what Cloudflare Pages will serve):

```bash
npm run build          # -> dist/
npm run preview        # serves dist/ exactly as Cloudflare Pages would
```

## Get a clickable preview link (Cloudflare Pages, free, ~5 min, one-time)

Could not be done from the cloud session (its network blocks the Cloudflare API).
Do it from your own browser:

1. dash.cloudflare.com → **Workers & Pages** → **Create** → **Pages** → **Connect to Git**.
2. Authorize GitHub, pick `gojiphysio/goji`.
3. Settings:
   - Production branch: `claude/trusting-franklin-itc74a`
   - Framework preset: **Astro**
   - Build command: `npm run build`
   - Build output directory: `dist`
   - Root directory (Advanced): `marketing/website/prototype`
   - (If Node errors) env var `NODE_VERSION` = `22`
4. **Save and Deploy** → you get a `https://<project>.pages.dev` URL that rebuilds
   on every push, with per-branch/PR preview URLs.

Alternative: automate via a GitHub Action (`cloudflare/pages-action`) that deploys
on push — needs a `CLOUDFLARE_API_TOKEN` + `CLOUDFLARE_ACCOUNT_ID` as repo secrets.

## Conventions to keep (see AGENTS.md)

- **Every CTA is a tracked link** through `go.gojiphysio.com/<slug>`; only slugs in
  `LINK_SLUGS` (`business-intelligence/scripts/dashboard/app.py`) exist today —
  add new ones there first.
- **Compliance is hard** (`../strategy/03-compliance-guardrails.md`): no
  cure/outcome guarantees, no superlatives, no before/after, **no testimonials**
  by default. Applies to placeholder copy too.
- Regular dashes (no emdashes), no emojis, **never italic**.
- Branch + PR to `main`; never push to `main` directly.
- Logos in `public/brand/` are copies of `business-intelligence/design/brand_assets/`.

## Next phases (not started)

1. **Hosting** — wire Cloudflare Pages (above) for live preview URLs.
2. **Content porting** — home + `../condition-pages/*.md` (4 drafts) + 3 bios into
   Astro pages / MDX content collections; add per-condition CTA slugs to `LINK_SLUGS`.
3. **Enquiry form handler** — Squarespace's form goes away; free/DIY option is a
   Cloudflare Pages Function feeding the front-desk Leads pipeline (`marts.lead_events`).
4. **SEO/schema** — JSON-LD (LocalBusiness, MedicalWebPage, FAQPage, Article),
   per-page meta, sitemap, Lentor Modern map embed.
5. **DNS cutover** from Squarespace once the look + content are approved (stage on
   `*.pages.dev` first; leave the `go.gojiphysio.com` Cloud Run service untouched).

Full plan with rationale was captured during the planning session; this file plus
`AGENTS.md` and `README.md` are the durable record.
