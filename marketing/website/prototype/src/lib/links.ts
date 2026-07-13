/**
 * CTA link tracking.
 *
 * Repo hard rule (AGENTS.md): every outbound CTA routes through the public
 * redirector `go.gojiphysio.com/<slug>` (the `goji-links` Flask service) so the
 * click is logged and attributable. NEVER publish a raw wa.me / Plato URL.
 *
 * Only the slugs that already exist in `LINK_SLUGS`
 * (business-intelligence/scripts/dashboard/app.py) are exposed here. Adding a
 * new slug means adding it to that map first — the union type below will then
 * stop a typo or an un-wired slug from shipping.
 *
 * Golden-flow attribution: on-site `web-*` CTA links are decorated at runtime by
 * a small inline script in `BaseLayout.astro` that appends `?sid=<booking
 * session>&p=<path>`. The redirector logs those onto `link_click_events` so a
 * WhatsApp/book tap can be tied back to the booking session + page it came from.
 * Nothing to do at each call site — just use `cta()` / the `Button` `slug` prop.
 */

const REDIRECT_BASE = "https://go.gojiphysio.com";

/** Slugs the redirector serves today. Keep in sync with app.py `LINK_SLUGS`. */
export type CtaSlug = "web-wa" | "web-book";

/** Resolve a slug to its tracked redirect URL. */
export function cta(slug: CtaSlug): string {
  return `${REDIRECT_BASE}/${slug}`;
}

/** Human-friendly defaults for the two web CTAs. */
export const CTA = {
  whatsapp: { slug: "web-wa" as CtaSlug, label: "Message us on WhatsApp" },
  book: { slug: "web-book" as CtaSlug, label: "Book an appointment" },
} as const;
