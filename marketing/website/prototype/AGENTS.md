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

## The watercolour look (Goji design system)
- Source of truth is the Goji design system artifact
  (https://claude.ai/artifact/GGKPrziiY9GdwFqYLbW51t); `tokens.css` mirrors its
  tokens. Type: Newsreader Medium (display optical size) for headings and
  large brand quotes; Figtree for everything else (body, buttons, nav, labels,
  prices). A heading under about 20px (FAQ question, card label) sets
  `font-family: var(--font-body)` in SemiBold. Never italic. No uppercase
  eyebrow labels on the home page.
- **No arches or round-topped frames** (they read as a tombstone in Asian
  culture). Photos use the petal frame (`components/watercolor/PetalPhoto.astro`).
- **No WhatsApp green**, not even on the glyph; WhatsApp CTAs are brand red
  (`Button variant="whatsapp"`) and the glyph takes the label colour.
- Motion is the procedural watercolour engine in `src/scripts/goji-watercolor.js`
  (vendored from the design system; re-copy, don't edit). `BaseLayout` runs
  `Goji.enhance()` on every page: use `components/watercolor/Bloom.astro`,
  `PaintedWord.astro`, `PetalPhoto paint`, `.gj-reveal`, `data-gj-wash`.
  Never put a reveal or a paint-in veil on above-the-fold content (LCP), and
  never let motion gate content or scrolling. Paintings start when a sliver is
  in view; on the site they run at `speed` 2.25-2.4 (`Bloom speed`,
  `data-speed`), with short `data-delay` steps, so a reader scrolling at normal
  pace sees them grow.

## Hard rules (inherited from repo + marketing AGENTS.md)
- **Every CTA is a tracked link.** Route through `go.gojiphysio.com/<slug>` via
  the `cta()` helper / Button `slug` prop (`src/lib/links.ts`). Never publish a
  raw `wa.me` / Plato URL, never the internal `dashboard.*` domain. Only slugs
  that exist in `LINK_SLUGS` (`business-intelligence/scripts/dashboard/app.py`)
  are exposed today: `web-wa`, `web-book` (the Book CTA points at our own `/book`
  form via `web-book`, not Plato), plus the campaign slug `web-99-wa` (9.9
  Pilates / S&C promo - drop it from `CtaSlug` when the offer ends), and
  `bio-wa` / `bio-book`, used only on `/links` (the Instagram link-in-bio page that
  replaced bio.site; the dashboard shows these as "Link in bio"). A new CTA
  needs its slug added there first.
- **Booking funnel stages are allowlisted server-side.** A new
  `bookingApi.track()` stage must be added to `VALID_STAGES` in
  `business-intelligence/scripts/booking/app.py` (and the `FunnelStage` type in
  `src/lib/booking.ts`) in the same PR, or the backend silently drops it.
  `service_selected` with `detail = "deep_link"` means step 1 was skipped (a
  service page's `/book/?service=…` link already filled it), so count those
  apart when reading step-1 drop-off. `detail = "no_focus"` means Continue was
  tapped on Physiotherapy without a type: it books as "Not sure / other" and
  step 3's optional answer lands in the Plato note as "Looking for: …", never
  in `physio_focus` (that would re-filter clinicians after the slot was chosen).
- **The landing beacon sends three event types**, all to `/api/web-event`:
  `session_start` / `page_view` on arrival, and `page_engagement` once per page
  load on first hide (`visibilitychange` → hidden, or `pagehide`), carrying
  `dwell_ms` (visible time only) + `scroll_pct`. New fields must be copied
  through `web_event_row()` in `business-intelligence/scripts/booking/app.py`
  **and** added to `marts/53_web_session_events.sql` in the same PR, or the
  backend silently drops them (same allowlist idiom as the funnel stages).
  Two traps, both learned the hard way: **never measure scroll depth at init**
  (during first layout `scrollHeight` isn't final, which reads as "whole page
  seen" and pins the metric at 100 forever — measure on scroll and at flush),
  and **use `fetch(..., {keepalive:true})`, not `sendBeacon`** (the API is
  cross-origin and `sendBeacon` can't run the CORS preflight a JSON body needs,
  so the browser drops it on unload without an error).
- **Compliance is a hard constraint** (`marketing/strategy/03-compliance-guardrails.md`).
  Applies to placeholder copy too: no cure/outcome/time guarantees, no
  superlatives ("best/leading/No.1"), no comparative claims, no before/after
  imagery, **no patient testimonials by default** (Lane A). `QuoteSurface` is
  for the brand promise, not a testimonial.
- **Voice/style:** warm, plain, educational. Regular dashes (no emdashes), no
  emojis in brand copy, **never italic** (enforced in `base.css`).
  Page intros say what the page has, plainly: no copy about the page itself
  ("in plain language", "written out properly"), no hedge-then-reassure
  ("Nothing here replaces X, but…"), no "Explore", "tailored", "journey",
  "with confidence".
- **Condition pages carry a clinician byline.** Every `conditions` entry sets a
  `reviewer: { name, slug }` (the reviewing physio, from the source doc). The
  detail template renders a "Reviewed by <name>" line linking to `/team/<slug>`
  and emits `reviewedBy` in the MedicalWebPage JSON-LD. Strip the source doc's
  italic reviewer/status/SEO-slug/structured-data notes and inline CTA — the
  template supplies the H1, byline, and CTA.
- **Third-party embeds are click-to-load.** Nothing may fire a third-party
  request on page view. Videos use the `YouTubeShort` facade (branded poster;
  the iframe is injected only on click). The map uses `SITE.googleMapsEmbed` —
  a keyless `output=embed` URL, because the `maps.app.goo.gl` short link in
  `SITE.googleMaps` cannot be iframed. Keep both URLs in `site.ts`, never
  hardcoded in a component.
- **`tone="closing"` needs an on-dark CTA.** The `primary` button is Deep Red on
  the Deep Red closing surface and disappears. Give the non-WhatsApp CTA a linen
  fill (see `.gh-btn-light` on `/getting-here`).
- **Mobile-first.** Most reach is on a phone. Base CSS before `@media`; check
  down to ~375px.
- **Branch & PR to `main`** — never push to `main` directly.

## SEO/GEO rules (from the 2026-07 review — full map in `../../seo/seo-geo-review.md`)
- **Per-page schema is required**, by page type: conditions emit MedicalWebPage
  + reviewedBy (from `reviewer`) + BreadcrumbList + FAQPage; services emit
  Service + Offer + BreadcrumbList + FAQPage (frontmatter `faqs`); team pages
  emit enriched Person; blog posts emit BlogPosting (author + optional
  reviewedBy Person, both linking to `/team/<slug>`) + BreadcrumbList +
  FAQPage. New page types define their schema before merging.
- **Site-wide JSON-LD lives in `src/lib/schema.ts`**, not in `BaseLayout`, so
  the SEO loop can improve it as a tier A change without touching the layout
  (analytics beacon, tier C). Tiers: `../../seo/AGENTS.md`.
- **Press pages never claim authorship.** A `/press/<slug>` page is a `WebPage`
  whose `citation` is the outlet's `NewsArticle` (their headline, their URL,
  their publisher); the index adds `subjectOf` against the clinic
  Organization. The visible page is **our** summary plus at most one short
  attributed quote and a link out - never a copy of the outlet's article, in
  any language. It is their copyright, and a duplicate would be ignored by
  search engines anyway.
- **Condition and blog FAQPage is parsed from the body**: keep the exact format
  `## Frequently asked questions` with `### <question>` blocks — other
  heading levels (e.g. `####`) or bullet questions silently emit no FAQPage.
  The parser is shared (`src/lib/faq.ts`) — don't re-implement it per template.
- **Every condition page carries a byline** via `reviewer: { name, slug }`
  frontmatter; the template renders "Reviewed by <name>" linking to
  `/team/<slug>` and emits `reviewedBy` in the MedicalWebPage JSON-LD.
- **Meta descriptions ≤160 chars.**
- **Internal page links end in `/`** (`/conditions/vertigo/`). Cloudflare
  Pages 308s the bare form; `check_dist.py` fails the PR on it.
- **`seoTitle` (services and conditions) overrides only the `<title>`.** Use it
  to target the national query ("Pelvic Floor Physiotherapy Singapore") without
  "Singapore" leaking into the H1, breadcrumbs or schema `name`, which read from
  `title`/`cardTitle`. Don't stuff the geo into `title` itself. The template
  appends " | Goji Physiotherapy" (20 chars), so keep `seoTitle` to about 40
  characters to stay under the ~60 a SERP shows.
- **Condition file slugs don't carry `-singapore`.** The route is
  `/conditions/<slug>`; the geo goes in `seoTitle` and the meta description.
- **Condition groups live in three places - keep them in sync.** The
  `category` enum in `src/content/config.ts`, the `categories` array in
  `src/pages/conditions/index.astro` (an enum value missing there never
  renders), and the `careAreas` titles on the homepage. Current groups:
  Women's Health, Paediatrics, Musculoskeletal & Sports, Vestibular
  Rehabilitation, Lymphatic Health (names match the Drive folders). Reviewers:
  Cheryl Long for Musculoskeletal & Sports, Claire Ng for Vestibular and
  Lymphatic. Dry needling and adult scoliosis are Cheryl-only services.
- **Condition body format** (all 37 pages follow it): intro paragraph with no
  H1, `##` sections, `H3` only for the FAQ, plain `- Label: text` bullets, no
  bold, no inline links and no "Related pages" section (strip the source doc's
  internal-links line). `cardTitle` is the page H1, so keep it equal to the doc
  title unless a shorter heading is intended. Add new pages to `public/llms.txt`.
- **`/womens-health-physiotherapy-singapore` is the women's-health hub.** It
  owns the broad national query; the four women's-health service pages own
  their own keyword and each links back up to it. Adding a women's-health
  service or condition page means adding it to the hub's `services` /
  `conditionGroups` list in the same PR, or the hub goes stale. The hub is
  deliberately **not** in the primary nav (kept short for phones) — it is
  reachable from `/services` and from every child page, so don't let those
  links rot or it becomes an orphan.
- **Service frontmatter escape hatches.** `metaTitle` is a verbatim `<title>`
  (beats `seoTitle`); `closingCopy` overrides the
  closing "Book your ..." paragraph; `bookingService` is optional - omit it for a
  service with no Plato calendar and the Book CTA opens the general `/book` form.
  **Private Pilates** (instructor-led, not physio) is bookable: Plato
  online-booking calendar `vXKlwa7` (rule: Camille, `pF9S`/`ICT`), type `N1z9`,
  and every booking is stamped Space Requirement "Reformer needed" (`code_Left`
  `YS06`, `space_code` in the booking `config.py`). Clinical and Private Pilates
  must stay distinct: AHPC-registered physiotherapist-led vs STOTT PILATES®
  certified instructor-led, and Private package credits are never described as
  interchangeable with Clinical/S&C.
- **Only claim a physical presence at Lentor.** Wider reach is "home visits
  across Singapore" — no neighbourhood pages implying a clinic elsewhere.
- **Update `public/llms.txt` in the same PR** as any page/service/price/team
  change — it is the canonical machine brief for AI answer engines.
- **Prices carry an "as of" month** (`SITE.pricesAsOf`, shown on `/services`,
  the hub and in `llms.txt`). Bump it in the same PR as any price change or
  re-confirmation; `check_dist.py` fails if `llms.txt` disagrees with the site.
- **The phone number is never a `tel:` link** (a call link can't go through the
  tracked redirector). Where it is tappable (footer, `/getting-here`) it opens
  WhatsApp through `cta("web-wa")`, so the tap is still tracked.
- **Every image gets descriptive alt text** (what a sighted visitor sees, as a
  sentence), and key facts live in static HTML, never injected by script:
  answer engines and agents read the accessibility tree and raw HTML.
- **Ad final URLs are direct site URLs, never `go.gojiphysio.com` links**
  (Google disallows redirector final URLs); on-page CTAs stay go-links.

## Assets
Logos in `public/brand/` are **copies** of the source of truth at
`business-intelligence/design/brand_assets/`. Re-sync if the brand updates.
Photos are real, consented clinic/practitioner images in production — no stock,
no before/after. Components show branded placeholders until photos land (a
`public/` photo that isn't in yet should degrade to a placeholder, not a broken
`<img>` — see the `.gh-photo[data-missing]` pattern on `/getting-here`).

Icons come from Tabler via `astro-icon` (`<Icon name="tabler:*" />`). When Tabler
has no suitable glyph, drop a stroke-styled SVG into `src/icons/` and reference
it by filename (`<Icon name="subway" />`) — don't pull in another icon set.

## Media IA (/media, /blog, /press)
One nav item, **Media**, fronts two children: `/blog` (what we write) and
`/press` (what others write about us). They stay separate pages — different
schema, different intent — but a single nav entry keeps the primary nav short
on a phone. Breadcrumbs on all four pages read Home › Media › …

**Posts are reviewed in the PR, not in Drive.** A draft post lands as a `.md`
in `src/content/blog/` on a branch; Cheryl reads it on the PR's Cloudflare
Pages preview, and her sign-off adds `reviewer:` before the owner merges
(tier B). Brief: `../../content-engine/blog-brief.md`; plan:
`../../seo/blog-plan.md`. A new post also needs its line in `public/llms.txt`
(`check_dist.py` fails otherwise). `src/pages/blog/index.astro`
branches on `posts.length`: with none it renders a "Coming soon" placeholder
that is `noindex` and excluded from search, and with one or more it becomes the
real index and re-enables both. **Don't hardcode the placeholder away** — drop
an approved `.md` into the collection and the page fixes itself.

## Site search (Pagefind)
Full-text search, built by the `pagefind` CLI over `dist/` as the second half
of `npm run build`. Config in `pagefind.yml`; Cloudflare Pages needs no change.

- **It only exists after a build.** `astro dev` has no `/pagefind/`, so
  `src/lib/search.ts` returns `null` and the UI shows a "production build only"
  note. To exercise search locally use the `website-preview` launch config, or
  `npm run build && npm run preview`.
- **What gets indexed is decided in markup.** `BaseLayout` puts
  `data-pagefind-body` on `<main>` (so header/footer/floating CTA never match)
  plus `data-pagefind-filter="type:<SearchType>"` for the result grouping.
  Pages pass `searchType`; utility pages (search, book, privacy, 404,
  styleguide) pass `searchable={false}`, which emits `data-pagefind-ignore`.
  Repeated in-page CTA blocks are stripped by `exclude_selectors` in
  `pagefind.yml` — add a selector there when you add a new repeating CTA, or
  every query will match "Message us on WhatsApp".
- A new page type needs a `SearchType` in `src/lib/search.ts` (add it to
  `TYPE_ORDER` and `typeLabel` too) before it will group correctly.

## Gotchas worth remembering
- **`_redirects` beats static assets on Cloudflare Pages.** A wildcard rule
  shadows real pages under that path. `/blog/*` and `/blog` used to 301 to
  `/conditions` and had to be removed when the blog shipped; the legacy rule is
  now scoped to `/blog/conditions/*`. Check `public/_redirects` before adding
  any new top-level section.
- **A `display` declaration beats `[hidden]`.** The UA rule is
  `[hidden] { display: none }`, so any element you toggle with the `hidden`
  attribute *and* style with `display: flex/grid` needs an explicit
  `.thing[hidden] { display: none }`. Hit by the booking form and again by the
  search panes.
- **Astro frontmatter can't `export type`.** Shared types live in `src/lib/*`
  and are imported with `import type` (esbuild fails on the union otherwise).
- **White fill + `--color-border` + `--shadow-sm` is the *interactive* recipe.**
  Buttons, chips and linked cards wear it, so a static fact/stat strip that wears
  it reads as tappable and people poke at it. Facts belong on the page ground
  with hairline `--rule` dividers instead - see `.gh-glance` on `/getting-here`.
  Same trap in reverse: an affordance ("Enlarge map") must sit *inside* the
  element that handles the click, not beside it.
- **A `class` passed to a child component needs `:global()` to style.** The class
  lands on that component's root element, which carries the *component's* scope
  attribute, not the page's - so a page-scoped `.foo { }` compiles to
  `.foo[data-astro-cid-<page>]` and silently matches nothing. `.gh-anchor`'s
  `scroll-margin-top` was dead this way for months. Related to the "scoped CSS
  doesn't reach into child components" rule, but easier to miss because the class
  *is* on the element you can see in devtools.

## Run it
See `README.md`. `npm install` then `npm run dev` (hot reload). `npm run build`
+ `npm run preview` is the Cloudflare-Pages-parity dry run (serves `dist/`) and
the only way to test search.

## Roadmap (remaining)
Active focus (see `HANDOFF.md` for status): design polish (via `tokens.css`),
more blog posts on the clusters in `../../seo/seo-geo-review.md` §3, and an
enquiry-form handler (free/DIY, a Pages Function feeding the front-desk Leads
pipeline). Deploy, content porting, SEO/schema, the Squarespace cutover, and
the blog/press/search surfaces are done. Capture new rules here as they surface.
