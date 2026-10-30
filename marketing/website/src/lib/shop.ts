/**
 * Website shop catalogue (/shop).
 *
 * Mirrors business-intelligence/scripts/shop/catalog.json, which creates the
 * Stripe Products and Payment Links; keep names and prices in sync. Each Buy
 * button goes through the redirector slug `web-pay-<key>` (app.py LINK_SLUGS),
 * which 302s to the item's Payment Link. Sales are entered into Plato by the
 * front desk (Phase 1), so pack sizes here must match the Plato package SKUs.
 */
import type { CtaSlug } from "./links.ts";

export interface ShopItem {
  key: string;
  slug: CtaSlug;
  name: string;
  /** Display price, e.g. "$669" or "From $50". */
  price: string;
  note?: string;
  lead: string;
}

export interface ShopGroup {
  title: string;
  intro: string;
  items: ShopItem[];
}

/** Groups shown on /shop. A group stays out until every item has a live Stripe
 * Payment Link (SHOP_PAY_URLS in app.py), or its Buy buttons loop back here. */
const PENDING = new Set(["Clinical Pilates and Strength & Conditioning packages"]);

export const SHOP: ShopGroup[] = ([
  {
    title: "Private Pilates packages",
    intro:
      "55-minute sessions with our STOTT PILATES® certified instructor. Introductory prices until 30 Nov 2026.",
    items: [
      { key: "pp-1to1-5", slug: "web-pay-pp-1to1-5", name: "1:1, 5 sessions", price: "$669", lead: "Five private sessions, just you and your instructor." },
      { key: "pp-1to1-10", slug: "web-pay-pp-1to1-10", name: "1:1, 10 sessions", price: "$1,229", lead: "Ten private sessions, just you and your instructor." },
      { key: "pp-2to1-5", slug: "web-pay-pp-2to1-5", name: "2:1, 5 sessions", price: "$899", note: "Price covers both people", lead: "Five sessions shared with a partner, friend or family member." },
      { key: "pp-2to1-10", slug: "web-pay-pp-2to1-10", name: "2:1, 10 sessions", price: "$1,649", note: "Price covers both people", lead: "Ten sessions shared with a partner, friend or family member." },
    ],
  },
  {
    title: "Clinical Pilates and Strength & Conditioning packages",
    intro:
      "55-minute sessions led by our AHPC-registered physiotherapists. One package covers both, so your programme can change as you progress.",
    items: [
      // TODO(price): inferred from the $180 single-session price, not yet confirmed.
      { key: "cpsc-5", slug: "web-pay-cpsc-5", name: "5 sessions", price: "$810", lead: "Five sessions across Clinical Pilates and Strength & Conditioning." },
      { key: "cpsc-10", slug: "web-pay-cpsc-10", name: "10 sessions", price: "$1,485", lead: "Ten sessions across Clinical Pilates and Strength & Conditioning." },
    ],
  },
  {
    title: "Gift vouchers",
    intro: "Valid for 12 months on any Goji service. You choose the amount at checkout.",
    items: [
      { key: "gift-voucher", slug: "web-pay-gift-voucher", name: "Goji gift voucher", price: "From $50", lead: "We'll send the voucher code to you, ready to pass on." },
    ],
  },
] as ShopGroup[]).filter((g) => !PENDING.has(g.title));
