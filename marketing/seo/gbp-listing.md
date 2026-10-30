# Google Business Profile — source of truth

The checked-in canonical for Goji's GBP listing. **NAP here must stay
byte-identical** with the site's structured data ([`site.ts`](../website/src/lib/site.ts))
and every external citation — diff against this when auditing NAP consistency.
Task list / cadence: `../strategy/05-30-day-campaigns.md` (Campaign 2).
Compliance floor for all copy below: `../strategy/03-compliance-guardrails.md`.

GBP is an **operator UI task**, except posts. Posts come from Instagram
automatically: `business-intelligence/scripts/ingestion/gbp_post_sync` turns
each new IG post into a GBP post (dry run until Google approves API access;
requested 28 Oct 2026 as hello@ for project goji-bi / 277737358846, case
2-7527000041676, quoted review time 7–10 business days. Don't file a second
request: duplicates slow the review).
Instagram is also linked under Social profiles (28 Oct 2026), which shows IG
posts in the profile's mobile "Social media updates" section.

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
| Post button (auto-synced from IG) | `https://go.gojiphysio.com/gbp-post-book` | `gbp-post-book` |

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

**Add: Pelvic Floor Physiotherapy.** It's missing from the list above. Then
paste a description into each service (GBP allows 300 characters). Why: Search
Console shows Goji at positions 1-4 for "women's physio singapore",
"postnatal physio", "pelvic floor therapy" and "physiotherapy", with about 0
website clicks. Those are Maps-pack impressions, where the services list
decides what the profile matches. Every line restates the site:

| Service | Description |
|---|---|
| Pelvic Floor Physiotherapy | Private, unhurried one-to-one sessions for leaking, prolapse, pelvic pain and recovery after birth. 55 minutes with an AHPC-registered physio. You can book directly, no referral needed. |
| Postnatal Physiotherapy | A proper look at how your body is recovering after a vaginal or Caesarean birth, and a plan for getting back to exercise, the gym or sport. Bring your baby along, or book a home visit. |
| Pregnancy Physiotherapy | Help to move more comfortably through pregnancy: back and pelvic pain, pelvic floor symptoms, staying active, and getting your body ready for birth. |
| Mummy & Baby Assessment | One appointment for both of you: your recovery after birth, and your baby's movement and early development from 0 to 12 months. $330 at the clinic, $450 at home. |
| Women's Health Physiotherapy | Physio for women at every stage, from pregnancy and the months after birth to pelvic floor and bladder concerns. At Lentor Modern, one minute from Lentor MRT, or at home. |
| Clinical Pilates | Pilates led by a physiotherapist, one-to-one or two-to-one, to build strength, mobility and confidence in how you move. |
| Strength & Conditioning | Physio-led training to build strength and movement capacity, matched to where you are now and where you want to get to. |

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
- 2–3 posts/week thereafter: automatic from Instagram once `gbp_post_sync`
  is live; don't post by hand as well or the profile shows each one twice.
- Reviews: **ask, never incentivize** (no discounts-for-reviews — hard NO).
