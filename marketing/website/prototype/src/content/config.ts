import { defineCollection, z } from "astro:content";

const conditions = defineCollection({
  type: "content",
  schema: z.object({
    title: z.string(),
    description: z.string(),
    /** Short heading shown on the index card */
    cardTitle: z.string().optional(),
    /** One-sentence summary for the card */
    cardLead: z.string(),
    category: z.enum([
      "Women's Health",
      "Musculoskeletal & Sports",
      "Paediatrics",
      "Vestibular",
      "Lymphatic & Oncology",
    ]),
    /** WhatsApp CTA slug — use "web-wa" until condition-specific slugs are wired in app.py */
    ctaSlug: z.string().default("web-wa"),
    /** Clinician who clinically reviewed the page. `slug` links to their
     *  /team/<slug> bio; every condition page carries a "Reviewed by" byline. */
    reviewer: z
      .object({ name: z.string(), slug: z.string() })
      .optional(),
    /** Optional ordering within category on the index page */
    order: z.number().optional(),
    draft: z.boolean().default(false),
  }),
});

const services = defineCollection({
  type: "content",
  schema: z.object({
    title: z.string(),
    /** Meta description (SEO) — also the default OG/description. */
    description: z.string(),
    /** Short heading shown on the index card (defaults to title). */
    cardTitle: z.string().optional(),
    /** One-sentence summary for the index card. */
    cardLead: z.string(),
    /** Hero image (path under /public) + its alt text. Shown on the detail page
     *  and the index card. */
    heroImage: z.string().optional(),
    heroAlt: z.string().optional(),
    /** Grouping bucket on the /services index. */
    category: z.enum([
      "Pregnancy & Postpartum",
      "General Health",
      "Children",
      "Holistic Care",
    ]),
    /** Facts header (from the source doc's Duration / Options / Physios lines). */
    durationMin: z.number(),
    priceClinic: z.number(),
    priceHome: z.number().optional(),
    /** Clinician display names for the "Seen by" line. */
    clinicians: z.array(z.string()),
    /** Which existing booking option this page preselects. */
    bookingService: z.enum([
      "physiotherapy",
      "mummy-baby",
      "clinical-pilates",
      "strength-conditioning",
    ]),
    /** Physio sub-type to preselect on the booking form (omit for mummy-baby). */
    bookingFocus: z
      .enum(["general", "womens-health", "paediatrics", "scoliosis", "others"])
      .optional(),
    /** Optional structured Q&A → FAQPage JSON-LD (progressive; add later). */
    faqs: z.array(z.object({ q: z.string(), a: z.string() })).optional(),
    /** Ordering within a category on the index page. */
    order: z.number().optional(),
    draft: z.boolean().default(false),
  }),
});

const team = defineCollection({
  type: "content",
  schema: z.object({
    name: z.string(),
    role: z.string(),
    credentials: z.string(),
    /** The hero lede. Long-form; use `metaDescription` for the <meta> tag. */
    tagline: z.string(),
    /** The <meta description>. Falls back to `tagline`, which may exceed 160. */
    metaDescription: z.string().max(160).optional(),
    /** Substring of `tagline` to underline in the hero. Ignored if it doesn't match. */
    taglineHighlight: z.string().optional(),
    photo: z.string().optional(),
    specialties: z.array(z.object({
      title: z.string(),
      description: z.string(),
    })),
    approach: z.string(),
    education: z.array(z.string()),
    experience: z.array(z.string()),
    training: z.array(z.string()),
    languages: z.array(z.string()),
    personalNote: z.string().optional(),
    /** Candid photo beside the personal note; degrades to a placeholder if unset. */
    personalPhoto: z.string().optional(),
    personalPhotoAlt: z.string().optional(),
    draft: z.boolean().default(false),
  }),
});

export const collections = { conditions, services, team };
