/**
 * Website shop catalogue (/shop), as collections.
 *
 * Mirrors business-intelligence/scripts/shop/catalog.json, which creates the
 * Stripe Products and Payment Links; keep names and prices in sync. A `buy`
 * option is a tracked `web-pay-<key>` go-link (app.py LINK_SLUGS) that 302s to
 * the item's Payment Link, so only use `buy` once that link exists in
 * SHOP_PAY_URLS. Until then an option is `ask` (price on request, WhatsApp) or
 * `soon` (placeholder, register interest on WhatsApp). Sales are entered into
 * Plato by the front desk (Phase 1), so pack sizes must match the Plato SKUs.
 */
import type { CtaSlug } from "./links.ts";

export type ShopStatus = "buy" | "ask" | "soon";

export interface ShopOption {
  key: string;
  name: string;
  detail?: string;
  /** Display price; omitted for `ask` / `soon` options. */
  price?: string;
  status: ShopStatus;
  /** Required when status is "buy". */
  slug?: CtaSlug;
}

export interface ShopCollection {
  id: string;
  title: string;
  lead: string;
  note?: string;
  /** A photo, or a watercolour bloom when there's no photo yet. */
  photo?: { src: string; alt: string; position?: string };
  bloom?: "berry" | "flower" | "ripen" | "sprig";
  /** Shown under the art when the collection has no photo yet. */
  artCaption?: string;
  options: ShopOption[];
}

export const SHOP: ShopCollection[] = [
  {
    id: "private-pilates",
    title: "Private Pilates",
    lead:
      "55-minute reformer and mat sessions with our STOTT PILATES® certified instructor, one to one or shared with someone you train with.",
    note: "Introductory prices until 30 Nov 2026.",
    photo: { src: "/photos/services/private-pilates-800.webp", alt: "A client on the reformer during a Private Pilates session at Goji." },
    options: [
      { key: "pp-1to1-5", name: "1:1, 5 sessions", detail: "Just you and your instructor", price: "$669", status: "buy", slug: "web-pay-pp-1to1-5" },
      { key: "pp-1to1-10", name: "1:1, 10 sessions", detail: "Just you and your instructor", price: "$1,229", status: "buy", slug: "web-pay-pp-1to1-10" },
      { key: "pp-2to1-5", name: "2:1, 5 sessions", detail: "Shared by two people, price covers both", price: "$899", status: "buy", slug: "web-pay-pp-2to1-5" },
      { key: "pp-2to1-10", name: "2:1, 10 sessions", detail: "Shared by two people, price covers both", price: "$1,649", status: "buy", slug: "web-pay-pp-2to1-10" },
    ],
  },
  {
    id: "clinical-pilates-sc",
    title: "Clinical Pilates and Strength & Conditioning",
    lead:
      "55-minute sessions led by our AHPC-registered physiotherapists. One package covers both, so your programme can change as you progress.",
    photo: { src: "/photos/services/strength-conditioning-800.webp", alt: "A woman training with a kettlebell during a Goji Strength & Conditioning session." },
    options: [
      // TODO(price): switch to `buy` once the Stripe links exist (catalog.json `inferred`).
      { key: "cpsc-5", name: "5 sessions", detail: "Use across both services", status: "ask" },
      { key: "cpsc-10", name: "10 sessions", detail: "Use across both services", status: "ask" },
    ],
  },
  {
    id: "pregnancy-courses",
    title: "Pregnancy and postnatal courses",
    lead:
      "Ten-session courses that bring together services we already offer, so your sessions for pregnancy or the months after birth are planned as one course.",
    photo: { src: "/photos/services/prenatal-physiotherapy-800.webp", alt: "A pregnant client working with a Goji physiotherapist." },
    options: [
      { key: "prenatal-10", name: "Prenatal course, 10 sessions", detail: "Details coming soon", status: "soon" },
      { key: "postnatal-10", name: "Postnatal course, 10 sessions", detail: "Details coming soon", status: "soon" },
    ],
  },
  {
    id: "gift-vouchers",
    title: "Gift vouchers",
    lead:
      "For someone expecting, recovering or getting stronger. A voucher can be used on any Goji service for 12 months, and you choose the amount at checkout.",
    bloom: "ripen",
    options: [
      { key: "gift-voucher", name: "Goji gift voucher", detail: "We'll send you the code to pass on", price: "From $50", status: "buy", slug: "web-pay-gift-voucher" },
    ],
  },
  {
    id: "goji-socks",
    title: "Goji socks",
    lead: "Our own socks, in Goji colours. Collect them at the clinic on your next visit.",
    bloom: "flower",
    artCaption: "Photos coming soon",
    options: [
      { key: "socks", name: "Goji socks", detail: "Sizes and price coming soon", status: "soon" },
    ],
  },
];
