/**
 * Site-wide JSON-LD, rendered on every page by BaseLayout.
 *
 * Lives here rather than in BaseLayout so the SEO loop can improve structured
 * data (a Tier A change, see ../../../../seo/AGENTS.md) without touching the
 * layout, which also carries the analytics beacon and booking wiring (Tier C).
 */
import { SITE } from "./site.ts";

/** MedicalClinic + LocalBusiness for local SEO (NAP from SITE). */
export function businessSchema(origin: URL) {
  return {
    "@context": "https://schema.org",
    "@type": ["MedicalClinic", "LocalBusiness"],
    name: SITE.fullName,
    alternateName: [SITE.name, "Goji Physio"],
    url: origin.href,
    image: new URL("/og-image.jpg", origin).href,
    email: SITE.email,
    telephone: SITE.phoneE164,
    priceRange: "$$",
    address: {
      "@type": "PostalAddress",
      streetAddress: SITE.address.line1,
      addressLocality: "Singapore",
      postalCode: "788887",
      addressCountry: "SG",
    },
    hasMap: SITE.googleMaps,
    areaServed: [
      { "@type": "Place", name: "Lentor, Singapore" },
      { "@type": "Place", name: "Ang Mo Kio, Singapore" },
      { "@type": "Place", name: "Yio Chu Kang, Singapore" },
      { "@type": "Place", name: "Upper Thomson, Singapore" },
      { "@type": "Place", name: "Springleaf, Singapore" },
      { "@type": "Place", name: "Bishan, Singapore" },
      { "@type": "Place", name: "Singapore" },
    ],
    medicalSpecialty: "Physiotherapy",
    openingHoursSpecification: [
      {
        "@type": "OpeningHoursSpecification",
        dayOfWeek: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
        opens: "08:00",
        closes: "20:00",
      },
    ],
    availableService: [
      "Physiotherapy",
      "Women's Health Physiotherapy",
      "Pelvic Floor Physiotherapy",
      "Pregnancy Physiotherapy",
      "Postnatal Physiotherapy",
      "Home Visit Physiotherapy",
      "Mummy & Baby Assessment",
      "Paediatric Physiotherapy",
      "Clinical Pilates",
      "Strength & Conditioning",
      "Lymphoedema Physiotherapy",
      "Vestibular Rehabilitation",
    ].map((name) => ({ "@type": "MedicalTherapy", name })),
    sameAs: [SITE.instagram, SITE.googleMaps],
  };
}
