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
| Address | `Lentor Modern, #01-13, Lentor Central, Singapore 788887` |
| Phone | `+65 8377 0401` |
| Website | `https://www.gojiphysio.com/` |
| Email | `hello@gojiphysio.com` |

Never use "Goji Physio" / "Goji Health Pte Ltd" in the **name** field — the
formal name is the canonical structured entity. "Goji Physiotherapy" is the
shorthand (`alternateName`), fine in description prose only.

## Categories

- **Primary:** Physiotherapist
- **Secondary:** Women's health clinic · Physical fitness program

## Hours

```
Mon–Sat  8:00 am – 8:00 pm
Sun & PH Closed (by appointment only)
```

## Tracked CTA links (never publish raw wa.me / Plato)

| GBP field | Link | Logs as |
|---|---|---|
| Booking / appointment | `https://go.gojiphysio.com/gbp-book` | `gbp-book` |
| WhatsApp / message | `https://go.gojiphysio.com/gbp-wa` | `gbp-wa` |

Slugs defined in `LINK_SLUGS` (`business-intelligence/scripts/dashboard/app.py`).

## Services (mirror the site's schema)

Physiotherapy · Women's Health Physiotherapy · Pregnancy Physiotherapy ·
Postnatal Physiotherapy · Mummy & Baby Assessment · Paediatric Physiotherapy ·
Clinical Pilates · Strength & Conditioning · Lymphoedema Physiotherapy ·
Vestibular Rehabilitation

## Business description (compliance-checked; 524/750 chars)

> Goji Physiotherapy is a dedicated physiotherapy clinic for women and families
> at Lentor Modern, a one-minute walk from Lentor MRT. We offer women's health
> and pelvic floor physiotherapy, prenatal and postpartum care, paediatric
> physiotherapy, musculoskeletal rehabilitation, clinical Pilates, and
> strength-focused recovery. Our care is thoughtful, clinically grounded, and
> designed to support women through changing life stages — with trusted care
> that can grow with the family too.

Checked vs the hard-NO list: no superlatives (best/leading/only/specialist),
no cure/outcome/time guarantees, no discounts/packages/testimonials.

## After the core fields (Campaign 2, Week 2)

- Upload 10+ real interior + team photos (no stock).
- Seed Q&A from the homepage FAQ (first-visit, what to wear, physio in
  pregnancy, ages treated, insurance).
- 2–3 posts/week thereafter.
- Reviews: **ask, never incentivize** (no discounts-for-reviews — hard NO).
