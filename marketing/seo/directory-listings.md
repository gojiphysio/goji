# Directory listings beyond Google — setup pack

Listings that feed AI answer engines and maps other than Google. Every value
below is copied from [`gbp-listing.md`](gbp-listing.md) (the NAP source of
truth) — keep them byte-identical; if the GBP listing changes, change these.

Each needs the owner to sign in (agents never sign in). Status column is the
record of what's live.

| Listing | Why it matters | Sign in with | Status |
|---|---|---|---|
| Bing Places | Bing's index feeds ChatGPT search and Copilot | hello@gojiphysio.com (Google) | not started |
| Apple Business Connect | Apple Maps, Siri, Spotlight | Apple ID for the business | not started |
| Wikidata item | Entity graph used by Google's Knowledge Graph and AI engines | a Wikidata account (declare the affiliation) | not started |
| Singapore Physiotherapy Association "find a physio" | Trusted directory, cited for "physio near me" | SPA membership | check eligibility |

## Shared values

| Field | Value |
|---|---|
| Business name | `Goji Women's and Family Physiotherapy` |
| Address | `Lentor Modern, #01-13, Lentor Central, Singapore 788887` |
| Phone | `+65 8377 0401` |
| Website | `https://www.gojiphysio.com/` |
| Email | `hello@gojiphysio.com` |
| Hours | Mon–Sat 8:00 am – 8:00 pm; Sun & PH closed (by appointment only) |
| Coordinates | 1.3858436, 103.8350854 |
| Booking link | `https://go.gojiphysio.com/gbp-book` (tracked; use for any "book" button) |
| Description | the 524-char compliance-checked text in `gbp-listing.md` |
| Categories | Physiotherapist (primary); Women's health clinic; Physical fitness program — map to the nearest each platform offers |

## Bing Places (≈5 min)

1. bingplaces.com → **Sign in** with the Google account that manages the
   Business Profile (hello@gojiphysio.com).
2. Choose **Import from Google Business Profile**. It copies NAP, hours,
   categories and photos and keeps them synced.
3. If import isn't offered, add manually with the shared values above.
4. Verification is usually instant for imported listings.

## Apple Business Connect (≈10 min + verification)

1. businessconnect.apple.com → sign in with an Apple ID for the business.
2. Search for the clinic; claim it if Apple already has a place card, else
   **Add a new location** with the shared values.
3. Category: Physical Therapist. Add the booking link as the action button.
4. Verify (phone call or documents).

## Wikidata item (≈10 min)

Create an account first and note on your user page that you're affiliated
with Goji (Wikidata's conflict-of-interest norm). The Lianhe Zaobao feature is
the independent reference that makes the item notable.

Paste into QuickStatements (quickstatements.toolforge.org → New batch, V1),
or add the statements by hand on wikidata.org:

```
CREATE
LAST	Len	"Goji Women's and Family Physiotherapy"
LAST	Den	"physiotherapy clinic in Lentor, Singapore"
LAST	Aen	"Goji Physiotherapy"
LAST	Aen	"Goji Physio"
LAST	P31	Q1774898	S854	"https://www.zaobao.com.sg/news/singapore/story20260721-9394054"
LAST	P101	Q186005
LAST	P17	Q334
LAST	P6375	en:"Lentor Modern, #01-13, Lentor Central, Singapore 788887"
LAST	P281	"788887"
LAST	P625	@1.3858436/103.8350854
LAST	P856	"https://www.gojiphysio.com/"
LAST	P2003	"gojiphysio"
```

IDs checked 26 Oct 2026: Q1774898 medical clinic, Q186005 physiotherapy
(medical specialty), Q334 Singapore; P31 instance of, P101 field of work,
P17 country, P6375 street address, P281 postal code, P625 coordinates, P856
official website, P2003 Instagram username, S854 reference URL.

After it's live, add the item's URL to `sameAs` in `src/lib/schema.ts`
(tier A) so the site and the graph point at each other.
