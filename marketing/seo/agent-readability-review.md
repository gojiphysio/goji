# Agent-readability playbook: fit for Goji (2026-10-20)

Assessment of an 11-point "get recommended by Meta's assistant" playbook (a
tweet shared by Charles) against gojiphysio.com. Measured on the built site
(47 pages) and the live site. Compliance (`../strategy/03-compliance-guardrails.md`)
overrides the playbook wherever they conflict.

| # | Playbook item | Goji status before | Action |
|---|---|---|---|
| 1 | Accessibility tree: named icon buttons, labelled form fields, descriptive alt, no key info in images | Every button has a name; every image has alt (22 empty are decorative bloom illustrations). The 4 homepage hero photos were hidden from the tree. 1 unlabelled field: `/book` notes box uses `aria-describedby`. | **Done:** descriptive alt on the hero photos; `/book` notes box now `aria-labelledby` (Charles approved, 2026-10-23). |
| 2 | Key info in raw HTML, not script | Astro is static: prices, address, hours, services are all in HTML. Only booking slots load by script (correctly). Phone number appears only in JSON-LD, never as visible text. | **Done (Charles, 2026-10-23):** phone shown as plain text in the footer, the homepage contact block and `/getting-here`. Not a `tel:` link, which would be an untracked CTA. |
| 3 | Reader's main question as the first H2 | Condition and service pages already lead with question H2s. Homepage and hub led with slogans. | **Done:** homepage "What is Goji Physio?", hub "Which appointment do I need?" |
| 4 | "It depends" answer under 100 words | None. | **Done** on the hub (77 words), mapping stage/symptoms to the 4 women's-health appointments, restating each service page's "Who is it for". **Not done:** competitor "X vs Y" answers. Comparative claims are a hard no under the compliance guardrails. |
| 5 | Definitions, not slogans | Homepage about section was a slogan ("A clinic women can trust through it all"). | **Done:** a what/who/what-it-does definition from facts already on the site. |
| 6 | Testimonials as plain text | Homepage already shows patient reviews as plain text (added 29 Jun). | **Not adopted.** The existing homepage reviews stay (Charles, 2026-10-23); no new testimonials are added. |
| 7 | "As of" dates on key facts | Prices undated. | **Done:** `SITE.pricesAsOf` ("October 2026") on `/services`, the hub and `llms.txt`; `check_dist.py` fails if they disagree. |
| 8 | robots.txt `User-agent: meta-webindexer` / `Allow: /` | `User-agent: *` / `Allow: /` already covers it; meta-externalagent, meta-webindexer and facebookexternalhit all get 200 live. A bot-specific group would *replace* the `*` group's Disallow rules for that bot. | **Not needed.** Meta crawlers added to the weekly `live_audit.py` access check instead. |
| 9 | Fix broken links (Screaming Frog) | Internal links: checked on every PR (`check_dist.py`) and weekly live. 1 redirect left (`/book?service=` prefill links). Outbound links unchecked. | **Done:** prefill links now point at `/book/?…` (prefill verified); internal redirects ratcheted to ERROR; weekly outbound-link and tracked-CTA (`go.gojiphysio.com`) checks. No paid tool needed. |
| 10 | Semantic HTML | Every page has `<header>`, `<nav>`, `<main>`, `<footer>`; actions are `<a>`/`<button>`; no clickable divs. | Nothing to fix. |
| 11 | Freshness: published/updated dates, refresh every 30-90 days | Condition pages show "Reviewed by" but no date; JSON-LD has no `dateModified`/`lastReviewed`. | **Deferred (Charles, 2026-10-23).** When picked up: Cheryl supplies a real review date per condition page (`lastReviewed` frontmatter), rendered as "Clinically reviewed by X · <date>" + `lastReviewed` JSON-LD. Never auto-bump dates: an "updated" date must mean a real review. The monthly loop flags pages older than 90 days for Cheryl. |

## Also worth doing

- **Measure Meta's assistant.** Add it as a fourth engine in the monthly AEO
  sweep (same 45 queries) once there's a no-memory way to use it.
- **The playbook's own premise:** AI agents read the accessibility tree and raw HTML. The new website
  `AGENTS.md` rule (descriptive alt, facts in static HTML) keeps this true for
  future pages.
