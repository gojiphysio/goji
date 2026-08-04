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
      "Women's Health Physiotherapy",
      "Paediatric Physiotherapy (0-18Y)",
      "Musculoskeletal Physiotherapy",
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

/**
 * Blog — the educational surface. Posts follow the answer-block pattern
 * (plain answer high on the page, question-phrased H2s, an FAQ section) that
 * `marketing/seo/seo-geo-review.md` §4.4 asks for, and the body's
 * `## Frequently asked questions` section is parsed into FAQPage JSON-LD by
 * the shared `src/lib/faq.ts` parser — same contract as condition pages.
 */
const blog = defineCollection({
  type: "content",
  schema: z.object({
    title: z.string(),
    /** Meta description. Hard SEO rule: 160 chars max. */
    description: z.string().max(160),
    /** Short heading shown on the index card (defaults to title). */
    cardTitle: z.string().optional(),
    /** One-sentence summary for the index card. */
    cardLead: z.string(),
    pubDate: z.date(),
    /** Set when a post is meaningfully revised, not for cosmetic edits. */
    updatedDate: z.date().optional(),
    /** Byline. `slug` links to the author's /team/<slug> bio. */
    author: z.object({ name: z.string(), slug: z.string() }),
    /** Clinician who clinically reviewed the post — same E-E-A-T byline
     *  pattern as conditions. Omit while a post is awaiting review. */
    reviewer: z.object({ name: z.string(), slug: z.string() }).optional(),
    /** Content pillars, from marketing/content-engine/content-pillars-and-calendar.md */
    category: z.enum([
      "Pelvic & Perinatal Health",
      "Musculoskeletal",
      "Movement & Fitness",
      "Active Ageing & Family",
      "Clinic News",
    ]),
    tags: z.array(z.string()).default([]),
    heroImage: z.string().optional(),
    heroAlt: z.string().optional(),
    /** Slugs of related content, rendered as an internal-links block. */
    relatedConditions: z.array(z.string()).default([]),
    relatedServices: z.array(z.string()).default([]),
    ctaSlug: z.string().default("web-wa"),
    draft: z.boolean().default(false),
  }),
});

/**
 * Press — third-party media coverage and events. We are NOT the publisher of
 * the source article: entries carry our own summary plus a link out, never a
 * copy of the outlet's text. `originalUrl` is the canonical source and is what
 * the page's `citation` JSON-LD points at.
 */
const press = defineCollection({
  type: "content",
  schema: z.object({
    /** Our headline for the entry (not the outlet's). */
    title: z.string(),
    description: z.string().max(160),
    cardLead: z.string(),
    /** Publication name, e.g. "Lianhe Zaobao". */
    outlet: z.string(),
    outletUrl: z.string().url(),
    /** Optional outlet logo filename (path under /public/press). */
    logo: z.string().optional(),
    /** The headline as published, in the language it was published in. */
    originalTitle: z.string(),
    /** Canonical source URL — the "Read the full article" destination. */
    originalUrl: z.string().url(),
    language: z.enum(["en", "zh"]).default("en"),
    pubDate: z.date(),
    /** The journalist's byline, as credited by the outlet. */
    author: z.string().optional(),
    kind: z.enum(["press", "event"]).default("press"),
    /** Team members featured, linking to their /team/<slug> bios. */
    featuring: z
      .array(z.object({ name: z.string(), slug: z.string() }))
      .default([]),
    /** Optional hero image (path under /public) + its alt text. */
    heroImage: z.string().optional(),
    heroAlt: z.string().optional(),
    /** One short attributed quote. Keep it short - this is someone else's
     *  copyrighted text, quoted for attribution, not reproduced. */
    pullQuote: z.string().optional(),
    order: z.number().optional(),
    draft: z.boolean().default(false),
  }),
});

export const collections = { conditions, services, team, blog, press };
