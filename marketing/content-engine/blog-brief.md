# Blog post brief

The one brief every Goji blog post is written against, by a person or an
agent. It keeps posts consistent and keeps them inside the compliance and SEO
rules. Plan and phase order: `../seo/blog-plan.md`. Keyword map:
`../seo/seo-geo-review.md` §3. Compliance: `../strategy/03-compliance-guardrails.md`.

## Where a post lives

`website/prototype/src/content/blog/<slug>.md`, one file per post. The slug is
the URL (`/blog/<slug>/`): lowercase, hyphenated, query-shaped, no
`-singapore` unless the query needs it.

```yaml
---
title: "Question-shaped title, the way someone would type or ask it"
description: "The direct answer in 140-160 characters. Hard max 160."
cardTitle: "Short card heading"
cardLead: "One sentence for the index card."
pubDate: 2026-10-27 # placeholder; reset to the merge date at sign-off
author:
  name: "Cheryl Long"
  slug: "cheryl-long"
# reviewer: added by the reviewing clinician on sign-off, never by the drafter
category: "Pelvic & Perinatal Health" # or Musculoskeletal | Movement & Fitness | Active Ageing & Family | Clinic News
tags: ["postnatal", "pelvic floor"]
relatedConditions: ["urinary-incontinence"] # existing slugs only
relatedServices: ["pelvic-floor-physiotherapy"] # existing slugs only
ctaSlug: "web-wa"
draft: false
---
```

Authors (`/team/<slug>`): `cheryl-long` (Clinical Director), `kristy-ng`,
`claire-ng` (Senior Physiotherapists), `camille-tan` (Pilates instructor; Lane B
topics only).

Who has to approve a post (decision 2026-10-27, to spare Cheryl's time):

| Post type | Approval | Byline |
|---|---|---|
| Clinic news, event recaps, local guides, "what to expect" | None: the owner merges | Omit `author`: "By the Goji team" |
| Clinical advice (symptoms, exercises, red flags, treatment) | Any AHPC-registered physio on the team signs off | That physio, plus `reviewer:` |

Never put a clinician's name on a post they haven't read.

## Shape (what wins citations in the 2026-10 audits)

1. **Answer first.** The first two or three sentences answer the title
   outright, with the number or the yes/no. No scene-setting.
2. **Question-shaped `##` headings** that match how people ask.
3. **At least one table** where the content is comparative or stepwise
   (timelines, who-does-what, exercise types).
4. **Primary sources linked inline**: NICE, Cochrane, peer-reviewed papers
   (PubMed/DOI), WHO, MOH/HealthHub/HPB, Singapore hospital patient pages.
   No other clinics' blogs as sources.
5. **FAQ last**, exactly `## Frequently asked questions` then `### Question?`
   blocks (other formats silently emit no FAQPage). 3-5 questions that are not
   already answered by an H2.
6. 800-1,400 words for explainers, 500-800 for clinic news.

## Accuracy rules

- Every third-party number is checked against its primary source, and the
  source is linked. If you can't verify it, cut it.
- Clinic facts (prices, durations, services, team, address, hours) come only
  from the repo: `src/content/**`, `src/lib/site.ts`, `public/llms.txt`.
- **No invented clinic experience.** Goji opened in mid-2026. Don't write
  "many of our patients", "the most common thing we hear", "plenty of the women
  we see". Say what is generally true and cite it.
- **Event recaps restate only what was published** (the Luma page, Goji's own
  Instagram caption). Never put words in a guest speaker's mouth or describe
  what was said in the room unless Goji published it. The educational part of a
  recap is our own explainer on the topic, clearly ours, not a summary of the
  talk.
- Guest doctors are named with their title and clinic as published on the
  event page. No endorsement framing in either direction.

## Compliance (Lane A unless purely fitness)

- "Can help", never "will fix". No cure, outcome or timeline guarantees.
- No superlatives (best, leading, top, only) and no comparisons with other
  providers, named or implied.
- No testimonials, patient stories, or before/after.
- Third-party listings (studios, places) are factual and alphabetical, never
  ranked, and never compared with Goji.
- Prices only if exact and taken from the repo.

## Voice

Warm, plain, educational; British spelling (physiotherapy, centre, colour).
Regular hyphens, never em or en dashes. No emojis, no italics, no bold in body
copy. No "delve", "crucial", "robust", "comprehensive", "nuanced", "it's
important to note", "in today's world". Short paragraphs.

## Images

- Every post has `heroImage` + `heroAlt` + `ogImage`. The hero is a real,
  consented Goji photo (no stock, no before/after), preferably upright and
  active. Reuse `public/photos/` until event or topic photos arrive; event
  photos replace stand-ins once everyone shown has consented.
- `ogImage` is a 1200x630 JPG crop of the hero in `public/og/blog/<slug>.jpg`
  (the WhatsApp/Facebook preview). `heroAlt` describes what a sighted reader
  sees, as a sentence.
- Body photos are plain Markdown images; the template frames them.

## Links and CTAs

- Internal links end in `/` (`/conditions/diastasis-recti/`). Bare forms fail
  `check_dist.py`. Link only to pages that exist.
- No CTA in the body and never a raw `wa.me` or Plato link: the template adds
  the tracked WhatsApp CTA from `ctaSlug`.
- Every post goes into `public/llms.txt` under `## Blog` in the same PR
  (`check_dist.py` fails otherwise) and gets a row in the keyword map.

## Before it ships

`npm run build && python3 ../../seo/tools/check_dist.py` passes; grep the post
for `—`, `–` and the banned words.

A post goes live as soon as Cheryl approves it, with no holding back for a
cadence. In the sign-off commit, add `reviewer:` and set `pubDate` to the day
it merges. `pubDate` is when the post went live (it is `datePublished` in the
schema): never backdate it to an event date. The recap text carries that.
