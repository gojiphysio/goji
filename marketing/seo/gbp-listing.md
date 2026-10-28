# Google Business Profile — source of truth

The checked-in canonical for Goji's GBP listing. **NAP here must stay
byte-identical** with the site's structured data ([`site.ts`](../website/prototype/src/lib/site.ts))
and every external citation — diff against this when auditing NAP consistency.
Task list / cadence: `../strategy/05-30-day-campaigns.md` (Campaign 2).
Compliance floor for all copy below: `../strategy/03-compliance-guardrails.md`.

GBP is an **operator UI task** — no programmatic edit path is wired up (the
Google Business Profile API needs `business.manage` OAuth + Google's manual
API-access approval; revisit only once posting cadence justifies it).

## NAP (byte-identical — do not vary spelling/spacing)

| Field | Value |
|---|---|
| Business name | `Goji Women's and Family Physiotherapy` |
| Address | `1 Lentor Central, #01-13, Lentor Modern, Singapore 788887` |
| Phone | `+65 8377 0401` |
| Website | `https://www.gojiphysio.com/` |
| Email | `hello@gojiphysio.com` |

Never use "Goji Physio" / "Goji Health Pte Ltd" in the **name** field — the
formal name is the canonical structured entity. "Goji Physiotherapy" is the
shorthand (`alternateName`), fine in description prose only.

Address follows the Business Profile (street number first, as Google
verified it). Changed from `Lentor Modern, #01-13, Lentor Central, ...` on
28 Oct 2026; the site (`site.ts`), `llms.txt`, Bing and Wikidata follow this.

## Categories

This file is the only place GBP categories are decided; other docs link here.

- **Primary:** Physiotherapist (the category Calyx and Physio Down Under use;
  Embrace uses Physical therapist). Don't switch it to "Physical therapy
  clinic": Google showed that label for Goji around the ~15 Oct 2026 edit,
  when Goji's #1 Maps spots fell from 9 to 1 (audit 2026-10-26).
- **Secondary:** Women's health clinic

## Hours

```
Mon–Sat  8:00 am – 8:00 pm
Sun & PH Closed (by appointment only)
```

## Other fields (as on the profile, 28 Oct 2026)

- Opening date: 8 April 2026
- Service area: Singapore (home visits)
- Social: https://www.instagram.com/gojiphysio/
- From the business: Identifies as women-owned
- Accessibility: wheelchair-accessible car park, seating, entrance and toilet
- Planning: appointment required. Service options: on-site services

Avoid batches of edits: each edit sends the profile back through Google's
review, and the ~15 Oct batch was followed by a Maps ranking drop.

## Tracked CTA links (never publish raw wa.me / Plato)

| GBP field | Link | Logs as |
|---|---|---|
| Booking / appointment | `https://go.gojiphysio.com/gbp-book` | `gbp-book` |
| WhatsApp / message | `https://go.gojiphysio.com/gbp-wa` | `gbp-wa` |

**Open (28 Oct 2026):** the profile's Chat field is a raw
`https://wa.me/+6583770401`, so those taps are not logged (and ChatGPT copies
it into answers). Replace it with `https://go.gojiphysio.com/gbp-wa`; if
Google rejects a non-wa.me URL in that field, keep wa.me and note it here.
Confirm the booking button uses `gbp-book`.

Slugs defined in `LINK_SLUGS` (`business-intelligence/scripts/dashboard/app.py`).

## Services (mirror the site's schema)

Physiotherapy · Women's Health Physiotherapy · Pregnancy Physiotherapy ·
Postnatal Physiotherapy · Mummy & Baby Assessment · Paediatric Physiotherapy ·
Clinical Pilates · Strength & Conditioning · Lymphoedema Physiotherapy ·
Vestibular Rehabilitation

## Business description (live on the profile, 28 Oct 2026; compliance-checked)

> Goji Women's and Family Physiotherapy is a physiotherapy clinic at Lentor
> Modern, Singapore, offering personalised, one-to-one care for women and
> families.
>
> Our AHPC-registered physiotherapists support pelvic health concerns,
> pregnancy and postpartum recovery, paediatric development, musculoskeletal
> pain and rehabilitation.
>
> Our services include pelvic floor physiotherapy, prenatal and postnatal
> physiotherapy, Mummy & Baby Assessments, Clinical Pilates, and strength and
> conditioning.
>
> We also offer home-visit physiotherapy across Singapore.

Checked vs the hard-NO list: no superlatives (best/leading/only/specialist),
no cure/outcome/time guarantees, no discounts/packages/testimonials.

## After the core fields (Campaign 2, Week 2)

- Upload 10+ real interior + team photos (no stock).
- Seed Q&A from the homepage FAQ (first-visit, what to wear, physio in
  pregnancy, ages treated, insurance).
- 2–3 posts/week thereafter.
- Reviews: **ask, never incentivize** (no discounts-for-reviews — hard NO).
