/**
 * Site-wide constants (NAP — name/address/phone — and meta).
 * Single source so the contact details stay consistent everywhere, matching
 * marketing/site-capture/content-inventory.md.
 */

export const SITE = {
  name: "Goji Physiotherapy",
  fullName: "Goji Women's and Family Physiotherapy",
  promise:
    "We're not here to fix you. We're here to help you feel confident in your body again.",
  tagline: "Care that grows with you.",
  seoTitle: "Goji Physiotherapy | Women's & Family Physio at Lentor MRT",
  seoDescription:
    "Physiotherapy for women and children at Lentor MRT. Prenatal, post-partum, paediatric, and pelvic health care in one trusted clinic.",
  email: "hello@gojiphysio.com",
  phone: "+65 8377 0401",
  phoneE164: "+6583770401",
  instagram: "https://www.instagram.com/gojiphysio/",
  googleMaps: "https://maps.app.goo.gl/wBaCkBiDNfF7JCGv8",
  address: {
    line1: "Lentor Modern, #01-13",
    line2: "Lentor Central, Singapore 788887",
    note: "1-minute walk from Lentor MRT (Thomson-East Coast Line, Exit 1).",
  },
  hours: [
    { days: "Monday – Saturday", time: "8am – 8pm" },
    { days: "Sunday & Public Holidays", time: "Closed (by appointment only)" },
  ],
} as const;
