/**
 * Site-wide constants (NAP — name/address/phone — and meta).
 * Single source so the contact details stay consistent everywhere, matching
 * marketing/site-capture/content-inventory.md.
 */

export const SITE = {
  name: "Goji Physiotherapy",
  fullName: "Goji Women's and Family Physiotherapy",
  promise:
    "Good physiotherapy is about more than treating symptoms. It's about helping you understand your body, move with confidence, and feel supported along the way.",
  tagline: "Care that grows with you.",
  seoTitle: "Goji Physiotherapy | Women's & Family Physio at Lentor MRT",
  seoDescription:
    "Physiotherapy for women and children at Lentor MRT. Prenatal, post-partum, paediatric, and pelvic health care in one trusted clinic.",
  email: "hello@gojiphysio.com",
  /** Month the published prices were last confirmed. Shown as "Prices as of
   *  <month>" next to prices (answer engines weight dated facts). Update it in
   *  the same PR as any price change, or when re-confirming prices. */
  pricesAsOf: "October 2026",
  phone: "+65 8377 0401",
  phoneE164: "+6583770401",
  instagram: "https://www.instagram.com/gojiphysio/",
  googleMaps: "https://maps.app.goo.gl/wBaCkBiDNfF7JCGv8",
  wikidata: "https://www.wikidata.org/wiki/Q141874843",
  // Keyless embeddable map (the goo.gl short link above will not render in an
  // iframe). Centres on the clinic by name + address; no Maps API key needed.
  googleMapsEmbed:
    "https://maps.google.com/maps?q=Goji%20Physiotherapy%2C%20Lentor%20Modern%2C%20Lentor%20Central%2C%20Singapore%20788887&output=embed",
  address: {
    line1: "1 Lentor Central, #01-13",
    line2: "Lentor Modern, Singapore 788887",
    note: "1-minute walk from Lentor MRT (Thomson-East Coast Line, Exit 1).",
  },
  hours: [
    { days: "Monday – Saturday", time: "8am – 8pm" },
    { days: "Sunday & Public Holidays", time: "Closed (by appointment only)" },
  ],
} as const;
