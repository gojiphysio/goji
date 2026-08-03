# Handoff — Goji website

Pick-up notes for continuing this work in a local session.

- **Project root:** `marketing/website/prototype/` (directory name is
  historical — this is the production site source).
- **Status (2026-07-13): LIVE IN PRODUCTION at gojiphysio.com** on
  Cloudflare Pages, deploying from `main`. Squarespace is deprecated. Built
  out: homepage, `/book` (native booking + attribution), 11 condition pages,
  6 service pages, 3 team bios, `/physiotherapy-lentor`, privacy, sitemap,
  robots, llms.txt, per-page JSON-LD (MedicalWebPage + bylines + FAQPage on
  conditions; Service + Offer + FAQPage on services; enriched Person on
  team). **Added 2026-08-03:** a `/media` hub with two children — `/blog`
  (template + schema ready, **no posts published yet**) and `/press` (the
  Lianhe Zaobao interview, citation schema) — plus `/rss.xml` and Pagefind
  full-text site search with a mobile-first search sheet.
  Remaining: design polish, per-page OG images, and **publishing the blog** —
  the first three drafts are awaiting Cheryl's clinical review in the Drive
  folder "Articles" (`1_7lYb2OiP3x3qORovG6Wg6TxLVClE7Nb`).
- **Live ops notes:** the apex→www 301 is a Cloudflare zone rule (not in
  `public/_redirects`) — verify it exists when touching DNS. Google Search
  Console ownership + sitemap submission is an operator task tracked in
  `../../seo/seo-geo-review.md` §1 (P0: inner pages were not indexed at the
  2026-07-13 audit).

## Where we're heading next (owner's priorities)

In rough order, the immediate goals for the next session(s):

1. **Improve the design / look + feel.** The bones are here; the brief is to make
   it feel more polished and distinctive. The look lives in one file
   (`src/styles/tokens.css`) — start there, use `/styleguide` as the QA surface.
2. **Implement a blog.** New surface, not built yet. Astro content collection
   (`src/content/blog/`, Markdown/MDX) + an index page + a post template. Keep the
   same components/tokens so it inherits the design system.
3. **Fill the blog with pre-written, backdated content.** Seed real posts with
   past `pubDate` frontmatter so the blog looks established at launch (not empty).
   Compliance rules below apply to every post.
4. **Deploy live, low/no cost.** Cloudflare Pages is the planned path (free, Astro
   preset, per-PR preview URLs) — see the hosting steps below.

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

**In Claude Code:** a launch config is committed at `.claude/launch.json`
(`website-prototype`, port 4232), so the built-in preview tool can start the dev
server and show a live pane without touching the terminal — just start the
`website-prototype` server. Port 4232 is only a convention for that pane; plain
`npm run dev` still serves on 4321.

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

## Next phases

Status re-marked 2026-08-03: phase 2 (blog scaffolding) is **done** alongside 4
(deploy), 5 (content porting) and 6 (SEO/schema). Phase 3 (seed content) is
**drafted but not published** — the three posts are in clinical review in Drive,
and `/blog` shows a "Coming soon" placeholder until one is approved. The enquiry
form piece of 7 remains. Active items: 1 (design polish), per-page OG images,
and getting the drafts reviewed and published against the clusters in
`../../seo/seo-geo-review.md` §3.

1. **Design polish** — raise the look + feel. Work in `src/styles/tokens.css`
   (the single knob) and the component CSS; `/styleguide` is the QA surface so a
   token change is visible everywhere at once. Don't hardcode hex/px in components.
2. **Blog** — add an Astro content collection at `src/content/blog/` (define the
   schema in `src/content/config.ts`: `title`, `description`, `pubDate`, optional
   `updatedDate`, `tags`, `heroImage`). Build `/blog` (index, newest-first) and a
   `/blog/[...slug]` post template that reuses `BaseLayout` + existing components.
   Add per-post SEO/schema (Article JSON-LD) when you reach phase 6.
3. **Seed backdated content** — write real posts as Markdown/MDX under
   `src/content/blog/` with past `pubDate` values so the blog reads as established.
   Every post still obeys the compliance guardrails (no cure/outcome claims, no
   superlatives, no testimonials by default — see `../strategy/03-compliance-guardrails.md`).
   Source ideas from `../content-engine/` and `../strategy/` if useful.
4. **Deploy (Cloudflare Pages, free)** — follow the hosting steps above to get a
   `*.pages.dev` URL that rebuilds on push, with per-PR previews. This is the
   low/no-cost target. (Alternatives if ever needed: Netlify, GitHub Pages — but
   Cloudflare is the plan and is free.)
5. **Content porting** — home + `../condition-pages/*.md` (4 drafts) + 3 bios into
   Astro pages / MDX content collections; add per-condition CTA slugs to `LINK_SLUGS`.
6. **SEO/schema** — JSON-LD (LocalBusiness, MedicalWebPage, FAQPage, Article),
   per-page meta, sitemap, Lentor Modern map embed.
7. **Enquiry form handler + DNS cutover** — replace Squarespace's form with a
   free/DIY Cloudflare Pages Function feeding the front-desk Leads pipeline
   (`marts.lead_events`); then cut DNS over from Squarespace once look + content
   are approved (stage on `*.pages.dev` first; leave the `go.gojiphysio.com`
   Cloud Run service untouched).

Full plan with rationale was captured during the planning session; this file plus
`AGENTS.md` and `README.md` are the durable record.
