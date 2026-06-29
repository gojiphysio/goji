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
    /** Optional ordering within category on the index page */
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
    tagline: z.string(),
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
    draft: z.boolean().default(false),
  }),
});

export const collections = { conditions, team };
