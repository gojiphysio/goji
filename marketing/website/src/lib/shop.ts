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

/**
 * The shop's checkout backend (booking service, POST /api/shop/checkout and
 * /api/shop/confirm). Production builds use PUBLIC_BOOKING_API. Cloudflare branch
 * previews (CF_PAGES_BRANCH != main) use the Stripe-sandbox service instead, so
 * a preview link can be shared for review without taking real money.
 * PUBLIC_SHOP_API overrides both (local testing).
 */
export const SHOP_SANDBOX_API = "";

export function shopBackend(): { api: string; sandbox: boolean } {
  const branch = typeof process !== "undefined" ? process.env.CF_PAGES_BRANCH : undefined;
  const preview = !!branch && branch !== "main";
  const api = (import.meta.env.PUBLIC_SHOP_API as string | undefined)
    || (preview ? SHOP_SANDBOX_API : (import.meta.env.PUBLIC_BOOKING_API as string | undefined)) || "";
  const sandbox = preview || import.meta.env.PUBLIC_SHOP_SANDBOX === "1";
  return { api: api.replace(/\/$/, ""), sandbox };
}

/** "$1,229" -> 122900; undefined for "From $50" / no price. */
export function priceCents(price?: string): number | undefined {
  const m = price?.match(/^\$([\d,]+(?:\.\d{2})?)$/);
  return m ? Math.round(parseFloat(m[1].replace(/,/g, "")) * 100) : undefined;
}

export const VOUCHER_AMOUNTS = [50, 100, 150, 200, 300, 500];

export type ShopStatus = "buy" | "ask" | "soon";

/** A buyable version of a product card (e.g. grip or non-grip sole). */
export interface ShopVariant {
  key: string;
  label: string;
  price?: string;
  status: ShopStatus;
  slug?: CtaSlug;
}

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
  /** Versions to pick between on a product card; each has its own price and link. */
  variants?: ShopVariant[];
  /** Price-list rows sharing a group ("1:1" / "2:1") show under a group switch. */
  group?: string;
  /** Full name for the cart line when `name` only reads well under its group. */
  cartName?: string;
}

export interface ShopCollection {
  /** Labels and hints for the group switch, in order (first is selected). */
  groups?: { id: string; label: string; hint?: string }[];
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
    lead: "Crew socks with our two favourite berries on the cuff, with a grip sole for Pilates or non-grip for every day. Collect them at the clinic on your next visit.",
    options: [
      {
        key: "socks-girl",
        name: "Goji Girl Socks",
        detail: "One pair, collect at the clinic",
        status: "buy",
        blurb:
          "Goji Girl has been holding the same side-lying leg lift since the day we opened, and she isn't about to stop for you. She lives on a cream rib-knit crew sock with a red cuff. Go grip to stay put on the reformer while she shows off, or non-grip for lounging about.",
        photos: [
          { src: "/photos/shop/socks-girl-art.webp", alt: "A pair of Goji Girl socks: cream rib-knit with a red cuff and an embroidered goji berry doing Pilates on a mat." },
          { src: "/photos/shop/socks-girl-front.webp", alt: "A Goji Girl sock from the side, showing the embroidered berry on the cuff." },
          { src: "/photos/shop/socks-girl-sole.webp", alt: "The grip sole of a Goji Girl sock, covered in grip dots with GOJI spelt out across the middle." },
        ],
        variants: [
          { key: "socks-girl-grip", label: "Grip sole", price: "$20", status: "buy", slug: "web-pay-socks-girl-grip" },
          { key: "socks-girl-nongrip", label: "Non-grip sole", price: "$20", status: "buy", slug: "web-pay-socks-girl-nongrip" },
        ],
      },
      {
        key: "socks-gang",
        name: "Goji Gang Socks",
        detail: "One pair, collect at the clinic",
        status: "buy",
        blurb:
          "Two berries, one pair of sunglasses, and absolutely no plans to skip leg day. The Goji Gang roll deep on an oat rib-knit sock with a cocoa cuff. Go grip and the sole spells out GOJI, so even your footprints are on brand.",
        photos: [
          { src: "/photos/shop/socks-gang-art.webp", alt: "A pair of Goji Gang socks: oat rib-knit with a brown cuff and two embroidered goji berries, one in sunglasses." },
          { src: "/photos/shop/socks-gang-front.webp", alt: "A Goji Gang sock from the side, showing the two embroidered berries on the cuff." },
          { src: "/photos/shop/socks-gang-sole.webp", alt: "The grip sole of a Goji Gang sock, covered in grip dots with GOJI spelt out across the middle." },
        ],
        variants: [
          { key: "socks-gang-grip", label: "Grip sole", price: "$20", status: "buy", slug: "web-pay-socks-gang-grip" },
          { key: "socks-gang-nongrip", label: "Non-grip sole", price: "$20", status: "buy", slug: "web-pay-socks-gang-nongrip" },
        ],
      },
    ],
  },
  {
    id: "private-pilates",
    title: "Private Pilates",
    lead:
      "55-minute reformer and mat sessions with our STOTT PILATES® certified instructor, one to one or shared with someone you train with.",
    photo: { src: "/photos/services/private-pilates-800.webp", alt: "A client on the reformer during a Private Pilates session at Goji." },
    groups: [
      { id: "1:1", label: "1:1" },
      { id: "2:1", label: "2:1, shared", hint: "Shared by two people. The price covers both." },
    ],
    options: [
      { key: "pp-1to1-1", group: "1:1", name: "Single session", cartName: "Private Pilates 1:1, single session", price: "$160", status: "buy", slug: "web-pay-pp-1to1-1" },
      { key: "pp-1to1-5", group: "1:1", name: "5-session pack", cartName: "Private Pilates 1:1, 5-session pack", price: "$750", status: "buy", slug: "web-pay-pp-1to1-5" },
      { key: "pp-1to1-10", group: "1:1", name: "10-session pack", cartName: "Private Pilates 1:1, 10-session pack", price: "$1,400", status: "buy", slug: "web-pay-pp-1to1-10" },
      { key: "pp-2to1-1", group: "2:1", name: "Single session", cartName: "Private Pilates 2:1, single session", price: "$210", status: "buy", slug: "web-pay-pp-2to1-1" },
      { key: "pp-2to1-5", group: "2:1", name: "5-session pack", cartName: "Private Pilates 2:1, 5-session pack", price: "$1,000", status: "buy", slug: "web-pay-pp-2to1-5" },
      { key: "pp-2to1-10", group: "2:1", name: "10-session pack", cartName: "Private Pilates 2:1, 10-session pack", price: "$1,900", status: "buy", slug: "web-pay-pp-2to1-10" },
    ],
  },
  {
    id: "clinical-pilates-sc",
    title: "Clinical Pilates and Strength & Conditioning",
    lead:
      "55-minute sessions led by our AHPC-licensed physiotherapists. Sessions are interchangeable, so your programme can move between Clinical Pilates and Strength & Conditioning as you progress.",
    photo: { src: "/photos/services/strength-conditioning-800.webp", alt: "A woman training with a kettlebell during a Goji Strength & Conditioning session." },
    groups: [
      { id: "1:1", label: "1:1" },
      { id: "2:1", label: "2:1, shared", hint: "Shared by two people. The price covers both." },
    ],
    options: [
      { key: "cpsc-1to1-1", group: "1:1", name: "Single session", cartName: "Clinical Pilates & S&C 1:1, single session", price: "$180", status: "buy", slug: "web-pay-cpsc-1to1-1" },
      { key: "cpsc-1to1-5", group: "1:1", name: "5-session pack", cartName: "Clinical Pilates & S&C 1:1, 5-session pack", price: "$850", status: "buy", slug: "web-pay-cpsc-1to1-5" },
      { key: "cpsc-1to1-10", group: "1:1", name: "10-session pack", cartName: "Clinical Pilates & S&C 1:1, 10-session pack", price: "$1,600", status: "buy", slug: "web-pay-cpsc-1to1-10" },
      { key: "cpsc-2to1-1", group: "2:1", name: "Single session", cartName: "Clinical Pilates & S&C 2:1, single session", price: "$230", status: "buy", slug: "web-pay-cpsc-2to1-1" },
      { key: "cpsc-2to1-5", group: "2:1", name: "5-session pack", cartName: "Clinical Pilates & S&C 2:1, 5-session pack", price: "$1,100", status: "buy", slug: "web-pay-cpsc-2to1-5" },
      { key: "cpsc-2to1-10", group: "2:1", name: "10-session pack", cartName: "Clinical Pilates & S&C 2:1, 10-session pack", price: "$2,100", status: "buy", slug: "web-pay-cpsc-2to1-10" },
    ],
  },
  {
    id: "gift-vouchers",
    title: "Gift vouchers",
    lead:
      "For someone expecting, recovering or getting stronger. A voucher can be used on any Goji service for 12 months. Pick the amount below.",
    bloom: "ripen",
    options: [
      { key: "gift-voucher", name: "Goji gift voucher", detail: "We'll send you the code to pass on", price: "$50 to $500", status: "buy", slug: "web-pay-gift-voucher" },
    ],
  },
];
