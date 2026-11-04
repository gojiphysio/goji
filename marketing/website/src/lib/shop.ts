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
  /** Product shots (first is the main image); turns the collection into product cards. */
  photos?: { src: string; alt: string }[];
  /** A short product description, shown on product cards. */
  blurb?: string;
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
    id: "goji-gang-merch",
    title: "Goji Gang socks",
    lead: "Pilates grip socks with our two favourite berries on the cuff. Collect them at the clinic on your next visit.",
    options: [
      {
        key: "socks-girl",
        name: "Goji Girl Socks",
        detail: "One pair, collect at the clinic",
        price: "$25",
        status: "buy",
        slug: "web-pay-socks-girl",
        blurb:
          "Goji Girl has been holding the same side-lying leg lift since the day we opened, and she isn't about to stop for you. She lives on a cream rib-knit crew sock with a red cuff, over a dotted grip sole that keeps you put on the reformer while she shows off.",
        photos: [
          { src: "/photos/shop/socks-girl-art.webp", alt: "A pair of Goji Girl socks: cream rib-knit with a red cuff and an embroidered goji berry doing Pilates on a mat." },
          { src: "/photos/shop/socks-girl-front.webp", alt: "A Goji Girl sock from the side, showing the embroidered berry on the cuff." },
          { src: "/photos/shop/socks-girl-sole.webp", alt: "The sole of a Goji Girl sock, covered in grip dots with GOJI spelt out across the middle." },
        ],
      },
      {
        key: "socks-gang",
        name: "Goji Gang Socks",
        detail: "One pair, collect at the clinic",
        price: "$25",
        status: "buy",
        slug: "web-pay-socks-gang",
        blurb:
          "Two berries, one pair of sunglasses, and absolutely no plans to skip leg day. The Goji Gang roll deep on an oat rib-knit sock with a cocoa cuff, and the grip sole spells out GOJI, so even your footprints are on brand.",
        photos: [
          { src: "/photos/shop/socks-gang-art.webp", alt: "A pair of Goji Gang socks: oat rib-knit with a brown cuff and two embroidered goji berries, one in sunglasses." },
          { src: "/photos/shop/socks-gang-front.webp", alt: "A Goji Gang sock from the side, showing the two embroidered berries on the cuff." },
          { src: "/photos/shop/socks-gang-sole.webp", alt: "The sole of a Goji Gang sock, covered in grip dots with GOJI spelt out across the middle." },
        ],
      },
    ],
  },
  {
    id: "private-pilates",
    title: "Private Pilates",
    lead:
      "55-minute reformer and mat sessions with our STOTT PILATES® certified instructor, one to one or shared with someone you train with.",
    note: "Introductory prices until 30 Nov 2026.",
    photo: { src: "/photos/services/private-pilates-800.webp", alt: "A client on the reformer during a Private Pilates session at Goji." },
    options: [
      { key: "pp-1to1-5", name: "1:1 x 5 sessions Package", price: "$669", status: "buy", slug: "web-pay-pp-1to1-5" },
      { key: "pp-1to1-10", name: "1:1 x 10 sessions Package", price: "$1,229", status: "buy", slug: "web-pay-pp-1to1-10" },
      { key: "pp-2to1-5", name: "2:1 x 5 sessions Package", detail: "Shared by two people, price covers both", price: "$899", status: "buy", slug: "web-pay-pp-2to1-5" },
      { key: "pp-2to1-10", name: "2:1 x 10 sessions Package", detail: "Shared by two people, price covers both", price: "$1,649", status: "buy", slug: "web-pay-pp-2to1-10" },
    ],
  },
  {
    id: "clinical-pilates-sc",
    title: "Clinical Pilates and Strength & Conditioning",
    lead:
      "55-minute sessions led by our AHPC-registered physiotherapists. One package covers both, so your programme can change as you progress.",
    photo: { src: "/photos/services/strength-conditioning-800.webp", alt: "A woman training with a kettlebell during a Goji Strength & Conditioning session." },
    options: [
      // PLACEHOLDER prices (CP/S&C, socks): not confirmed; no Stripe link yet,
      // so these Buy buttons fall back to /shop/ until catalog.json is confirmed and synced.
      { key: "cpsc-5", name: "5 sessions Package", detail: "Use across both services", price: "$810", status: "buy", slug: "web-pay-cpsc-5" },
      { key: "cpsc-10", name: "10 sessions Package", detail: "Use across both services", price: "$1,485", status: "buy", slug: "web-pay-cpsc-10" },
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
];
