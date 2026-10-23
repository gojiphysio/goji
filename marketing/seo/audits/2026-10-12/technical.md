# Technical SEO + AEO audit: www.gojiphysio.com (2026-10-12)

Read-only crawl of the live site. No source edited. Previous audit:
`../../seo-geo-review.md` §1-2 (2026-07-13).
Astro source = `marketing/website/prototype/` (paths below are relative to it).

**Scope:** 44 sitemap URLs + every internal link discovered from them (95 URLs fetched
incl. non-slash variants and 7 `/book?service=` variants), 7 external links, JSON-LD on
every 200 page, 4 host variants, robots/sitemap/llms.txt, 9 crawler UAs x 4 URLs,
PageSpeed Insights (mobile) on 5 URLs.

**Raw data:** `schema_report.json`, `ai_crawlers.csv` and `hosts.txt` are kept
here. The bulky per-page crawl dumps were not committed; later runs regenerate
them with `../../tools/live_audit.py`.

"NEEDS HUMAN APPROVAL" = touches /book, booking code, `src/lib/links.ts`, CTA slugs,
prices, `_redirects`, analytics beacon, `astro.config.mjs` or robots policy.

## Issues, ranked

| # | Pri | Issue | URL(s) | Evidence | Suggested fix | Owning file(s) |
|---|---|---|---|---|---|---|
| 1 | **P0** | Women's-health hub is **404** but still linked internally and advertised to AI engines | `/womens-health-physiotherapy-singapore` | 404 live. Linked from `/services/`, `/services/pelvic-floor-physiotherapy/`, `/prenatal-physiotherapy/`, `/postpartum-physiotherapy/`, `/mummy-baby-assessment/` (5 pages = the 4 money pages + services index). Also listed in live `llms.txt`. Page was moved to `marketing/website/offline-pages/` in commit `80c464b` (2026-08-07, "being reworked"); links were not removed. `AGENTS.md` still describes it as the live hub. | Either restore the page (move it back to `src/pages/`) or remove the 5 links + the llms.txt line until it returns. Update the hub rule in `AGENTS.md` either way. | `src/pages/services/index.astro`; `src/content/services/{pelvic-floor,prenatal,postpartum}-physiotherapy.md`, `mummy-baby-assessment.md`; `public/llms.txt`; `../offline-pages/womens-health-physiotherapy-singapore.astro` |
| 2 | **P1** | Every internal link uses the **non-slash** URL form; all 308-redirect to the slash form that the canonical + sitemap use | site-wide (nav, footer, cards, breadcrumbs, JSON-LD, llms.txt) | 93 distinct internal targets 308 (e.g. `/services` -> `/services/`, 95 inlinks each for nav items). Canonicals and sitemap are `.../services/`. JSON-LD URLs mixed: breadcrumb `https://www.gojiphysio.com/conditions`, reviewer `.../team/cheryl-long` (both 308) vs page `url` with slash. All 31 page URLs in `llms.txt` 308. Legacy `_redirects` targets are also non-slash, so e.g. `/cheryl-long` -> 301 `/team/cheryl-long` -> 308 `/team/cheryl-long/` (2 hops). | Pick one form and emit it everywhere. Lowest-risk: keep the slash form (matches canonical/sitemap/Cloudflare) and change hrefs + schema URLs to end in `/`. Setting `trailingSlash: "always"` in config enforces it at build. **`astro.config.mjs` change and the `/book` / `/book?service=` hrefs: NEEDS HUMAN APPROVAL.** | `src/layouts/BaseLayout.astro` (nav, footer), `src/pages/**` breadcrumb + schema builders, `src/components/*`, `public/llms.txt`; `astro.config.mjs` and `public/_redirects` targets (approval) |
| 3 | **P1** | Homepage has **no `<h1>`** | `/` | 0 H1; first headings are H2 "A clinic women can trust through it all". The hero line is `<p class="hero__tagline">` / `<p class="hero__sub">`. Every other page has exactly 1 H1. | Promote the existing hero line to `<h1>` (markup only, no copy change). | `src/pages/index.astro` (~L209-210) |
| 4 | **P1** | Money service pages are **near-orphans** (1 unique internal referrer) and condition pages don't link to any service | `/services/{pelvic-floor,prenatal,postpartum,paediatric,musculoskeletal}-physiotherapy/`, `/services/schroth-scoliosis-adults/` | Unique inlinking pages = 1 (`/services/` only). Condition pages link out only to nav/footer + `/team/cheryl-long` (9 internal links, none to a service). Each condition page has 2 referrers (`/`, `/conditions/`). The removed hub (#1) was the other path in. | Add a related-service link block to the condition template (content field like the blog's `relatedServices`), and link the women's-health services from the homepage service cards. | `src/pages/conditions/[...slug].astro`, `src/content/config.ts` (conditions schema), `src/pages/index.astro` |
| 5 | **P1** | Clinic entity schema missing **`@id`, `geo`, `logo`**; thin `sameAs` | every page (site-wide `MedicalClinic`/`LocalBusiness` block) | `@id`: none (95/95 pages). `geo`: absent. `logo`: absent. `sameAs`: Instagram + a maps.app.goo.gl short link only. `openingHoursSpecification` present (Mon-Sat 08:00-20:00), `telephone` +6583770401, `address` present (`streetAddress` = "Lentor Modern, #01-13"; llms.txt adds "Lentor Central"). Service `provider` and Person `worksFor` re-declare the clinic inline with no `@id`, and MedicalWebPage has no `publisher`, so engines can't join them to one entity. | Add `@id: "https://www.gojiphysio.com/#clinic"`, `geo` (GeoCoordinates), `logo`; reference it by `@id` from Service `provider`, Person `worksFor`, and a new MedicalWebPage `publisher`. Add GBP / other verified profile URLs to `sameAs` when available. | `src/layouts/BaseLayout.astro` (`businessSchema`), `src/lib/site.ts`, `src/pages/services/[...slug].astro`, `src/pages/team/[slug].astro`, `src/pages/conditions/[...slug].astro` |
| 6 | **P1** | Meta descriptions **> 160 chars** on 22 pages (rule in `AGENTS.md`) | 17 of 20 condition pages (235-348 chars on the 11 women's-health ones), `/` 179, `/services/` 185, `/pathways/postpartum/` 181, `/getting-here/` 162, `/book/` 169 | Condition template passes frontmatter `description` (the long intro paragraph) straight to `<meta name="description">`. Long since the 2026-07-15 commit that added bylines; §2 of the July review said descriptions were ≤160, which held for services only. | Add a short `seoDescription` (≤160) per condition, or truncate in the template. **`/book/` description: NEEDS HUMAN APPROVAL.** | `src/content/conditions/*.md`, `src/pages/conditions/[...slug].astro`, `src/pages/index.astro`, `src/pages/services/index.astro`, `src/pages/pathways/postpartum.astro`, `src/pages/getting-here.astro`; `src/pages/book.astro` (approval) |
| 7 | **P1** | `llms.txt` out of sync with the site | `/llms.txt` | Stale: hub URL (404). Missing: 9 paediatric condition pages (`adolescent-scoliosis-schroth`, `clubfoot-ctev`, `congenital-torticollis`, `developmental-concerns`, `hip-dysplasia-ddh`, `neurodevelopmental-conditions`, `paediatric-pelvic-health`, `paediatric-sports-injuries`, `post-fracture-rehab`), `/conditions/`, `/getting-here/`, `/pathways/postpartum/`. All URLs non-slash (308). Lists "Vestibular rehabilitation" and "Lymphoedema physiotherapy" as services with no page. No `llms-full.txt` (404). | Regenerate the URL lists from the sitemap (slash form), drop the hub line until #1 is resolved. | `public/llms.txt` |
| 8 | **P2** | 4 service pages lack **FAQPage** (required per `AGENTS.md`) | `/services/clinical-pilates/`, `/musculoskeletal-physiotherapy/`, `/paediatric-physiotherapy/`, `/strength-conditioning/` | No `faqs` frontmatter -> no FAQPage block. Also carried over from July §1 ("nice-to-have: FAQs for these 3"); MSK now also missing. Service + Offer + BreadcrumbList present on all 11 services. | Add clinician-reviewed `faqs` frontmatter. | `src/content/services/{clinical-pilates,musculoskeletal-physiotherapy,paediatric-physiotherapy,strength-conditioning}.md` |
| 9 | **P2** | Orphan page in sitemap | `/pathways/postpartum/` | In sitemap, **0** internal inlinks, not in llms.txt, no BreadcrumbList, description 181 chars, title 72 chars. Schema = clinic block only. | Decide: link it (e.g. from postpartum service/condition pages) or drop it from the build/sitemap. | `src/pages/pathways/postpartum.astro` |
| 10 | **P2** | Condition `MedicalWebPage` has no `lastReviewed` / `dateModified` | all 20 `/conditions/*/` | `reviewedBy` present on all 20 (good). No review/modified date in schema. | Emit `lastReviewed` (and `dateModified`) from a frontmatter date. | `src/pages/conditions/[...slug].astro`, `src/content/config.ts` |
| 11 | **P2** | Apex https downgrades to http before reaching www; no HSTS | `https://gojiphysio.com` | `https://gojiphysio.com` -> 301 `http://www.gojiphysio.com` (Squarespace) -> 301 `https://www.gojiphysio.com/` (Cloudflare) -> 308 slash. No `Strict-Transport-Security` header on www. Unchanged since July (accepted then). | Operator/infra: point apex at Cloudflare (or a redirect that targets `https://www`); add HSTS via a `public/_headers` file once apex is on https. | DNS (Google Cloud DNS) / Squarespace apex; `public/_headers` (new) |
| 12 | **P2** | No `<lastmod>` in sitemap | `/sitemap-0.xml` | 44 `<loc>`, 0 `<lastmod>`. | Add `serialize`/`lastmod` to the sitemap integration. **NEEDS HUMAN APPROVAL** (`astro.config.mjs`). | `astro.config.mjs` |
| 13 | **P2** | Titles > 60 chars (truncation risk) and mixed brand suffix | 12 pages > 60 (max 83: `/conditions/paediatric-pelvic-health/`); `"| Goji Health"` on `/book/`, `/privacy/`, 3 team pages vs `"| Goji Physiotherapy"` elsewhere | See `analysis.txt`. No duplicate titles. | Shorten long condition titles via a title override; align brand suffix. **`/book/` title: NEEDS HUMAN APPROVAL.** | `src/pages/conditions/[...slug].astro`, `src/pages/team/[slug].astro`, `src/pages/privacy.astro`; `src/pages/book.astro` (approval) |
| 14 | **P2** | BreadcrumbList missing on index/utility pages | `/services/`, `/conditions/`, `/pathways/postpartum/`, `/privacy/`, `/book/` | Present on all detail pages, `/media/`, `/press/`, `/getting-here/`, `/physiotherapy-lentor/`. | Add to the two indexes (others optional). | `src/pages/services/index.astro`, `src/pages/conditions/index.astro` |
| 15 | **P2** | Real photos with `alt=""` | `/` (4: `reception-warm`, `studio`, `session`, `strength`), `/getting-here/` (4 direction covers) | 0 `<img>` missing `alt` attribute site-wide; empty alts are otherwise decorative bloom illustrations (fine). | Give content photos descriptive alt. | `src/pages/index.astro`, `src/pages/getting-here.astro` |
| 16 | **P2** | One OG image for all 44 pages; `og:type=website` everywhere | site-wide | `og:image` = `/og-image.jpg` on 44/44. Carried over from July P2. | Per-page OG images; `article` for press/blog. | `src/layouts/BaseLayout.astro` |
| 17 | **P2** | No IndexNow key | — | `/indexnow.txt` 404, no key file in `public/`. Bing/Yandex only; Google ignores it. | Optional: add key file + ping on deploy. | `public/` |
| 18 | **P2** | Oversized images: 260 KB logo PNG loaded eagerly on every page; ~530 KB clinician headshots | site-wide header/footer logo; `/` and `/team/*` headshots | `/brand/logo_light_transparent.png` = 260 KB, rendered at 30-34 px tall, `loading="eager"`, twice per page. `cheryl-long.webp` 539 KB / `claire-ng.webp` 538 KB / `kristy-ng.webp` 503 KB (1000x670, lazy). Homepage cold load = 1.24 MB over 32 requests. | Serve a resized logo (or SVG); recompress headshots / use Astro `<Image>` with widths. | `public/brand/logo_light_transparent.png`, `src/components/LogoLockup.astro`, `public/photos/team/*.webp`, `src/components/PractitionerCard.astro` |
| 19 | info | Thin index pages | `/media/` 117 words, `/press/` 140 words | Expected (one press item, blog empty and noindexed). | None until content lands. | — |

## Passing checks

- **Status:** all 44 sitemap URLs 200, no redirect chains on canonical URLs; real 404 returns 404.
- **Canonicals:** all 44 self-reference the 200 `https://www.` slash URL. None mismatched.
- **Robots meta:** `noindex` only on `/blog/` (empty-blog placeholder, by design), `/search/`, `/styleguide/`, 404. `/blog` correctly excluded from sitemap.
- **Viewport** `width=device-width, initial-scale=1` on every page; `lang="en"` on every page; no `hreflang` (single-language site, none needed).
- **JSON-LD:** 0 invalid blocks. Conditions 20/20 = MedicalWebPage + `reviewedBy` + BreadcrumbList + FAQPage. Services 11/11 = Service + Offer (price + currency) + provider + BreadcrumbList (FAQPage on 7/11, see #8). Team 3/3 = Person with jobTitle, worksFor, sameAs, url, image, hasCredential + BreadcrumbList. Press article = WebPage + `citation`. Homepage + `/physiotherapy-lentor/` carry FAQPage.
- **OG/Twitter:** og:title/description/image/url + `summary_large_image` on all pages; og:url matches canonical.
- **External links:** 7 checked, all < 400.
- **H1:** exactly one on every page except `/` (#3).

## Hosts (`hosts.txt`)

| Start | Chain |
|---|---|
| `http://gojiphysio.com` | 301 (Squarespace) -> `http://www.gojiphysio.com` -> 301 (Cloudflare) -> `https://www.gojiphysio.com/` 200 |
| `https://gojiphysio.com` | 301 (Squarespace) -> **`http://`**`www.gojiphysio.com` -> 301 -> `https://www.gojiphysio.com/` 200 |
| `http://www.gojiphysio.com` | 301 -> `https://www.gojiphysio.com/` 200 |
| `https://www.gojiphysio.com` | 200 |
| deep link, e.g. `http://gojiphysio.com/services/pelvic-floor-physiotherapy` | path preserved: 301 -> 301 -> 308 (slash) -> 200 (3 hops) |

## robots.txt / sitemap / llms.txt

- **robots.txt** (live == `public/robots.txt`): `User-agent: *` Allow `/`, Disallow `/styleguide`, `/search`, `/pagefind/`; Sitemap line correct. No AI-crawler-specific rules; no Cloudflare-managed content-signal lines injected.
- **Sitemap:** index -> `sitemap-0.xml`, 44 URLs, slash form, **no `<lastmod>`** (#12). Hub page absent (correct, it 404s).
- **llms.txt:** see #7. `/llms-full.txt` 404.

## AI crawler access (`ai_crawlers.csv`)

GPTBot, OAI-SearchBot, ChatGPT-User, PerplexityBot, ClaudeBot, Claude-SearchBot,
Google-Extended, Googlebot, Bingbot x `/`, `/services/pelvic-floor-physiotherapy/`,
`/conditions/diastasis-recti/`, `/llms.txt`: **36/36 = 200**, identical byte counts per
URL, no `cf-mitigated` header, no challenge markup. Caveat: requests came from a
non-bot IP with a spoofed UA, so this confirms no UA-based block (Cloudflare "Block AI
bots" would act on UA) but cannot prove verified-bot IP handling.

## Core Web Vitals (PSI mobile, `psi_mobile.json`)

**Not obtained.** The keyless PSI API returned **429 "Quota exceeded ... Queries per day"**
on the first request (shared anonymous quota, `psi_mobile.json`); retries within the day
cannot succeed. No CrUX field data was retrieved. Re-run PSI v5 `strategy=mobile` for the same 5 URLs tomorrow or with an API key.
Note `/womens-health-physiotherapy-singapore` is 404, so it cannot be measured until #1
is resolved.

Fallback (`browser_timing.json`): desktop Chrome at 375x812, **unthrottled, paint metrics
not captured** (pane hidden) - indicative only, not CWV:

| URL | TTFB | load event | transfer | requests |
|---|---|---|---|---|
| `/` (cold) | 235 ms | 626 ms | 1,239 KB | 32 |
| `/book/` (warm) | 51 ms | 234 ms | 29 KB | 25 |
| `/services/pelvic-floor-physiotherapy/` (warm) | 82 ms | 244 ms | 62 KB | 17 |
| `/conditions/diastasis-recti/` (warm) | 46 ms | 240 ms | 16 KB | 15 |

Homepage weight is dominated by images (#18). Every page also loads Google Tag
Manager / Google Ads (`googletagmanager.com`, `doubleclick.net`) on view; that is
analytics/ads tagging, so any change to it **NEEDS HUMAN APPROVAL**.

## What changed since the 2026-07-13 audit

- **New since July:** 9 paediatric condition pages (all with byline + full schema); `/media`, `/blog` (empty, noindexed), `/press` + Zaobao press page with `citation`; Pagefind search (`/search` noindexed + robots-disallowed); Clinical Pilates, S&C, Paediatric, MSK service pages; `/pathways/postpartum/` (orphan).
- **Regressed:** women's-health hub launched then pulled offline (2026-08-07) leaving 5 internal links + llms.txt entry pointing at a 404 (#1). Condition meta descriptions > 160 (#6) despite §2 saying they were fixed.
- **Unchanged:** apex -> http-www hop (#11); single OG image (#16); FAQs missing on the newer services (#8).
- **Still good:** inner pages 200 + self-canonical (July P0 resolved), bio 301s, `/physiotherapy-lentor`, FAQPage/MedicalWebPage/Person schema.
