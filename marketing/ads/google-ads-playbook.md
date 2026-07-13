# Google Ads playbook (Goji)

> **The live campaign spec — exact ad groups, keywords, ad copy, budget and
> launch runbook — is `google-ads-campaign-plan.md`.** This playbook is the
> evergreen how-to: where each screen lives and why each rule exists. Where
> the two disagree, the campaign plan wins.

A practical, beginner-friendly guide to fixing Goji's Google Ads so budget goes to
**high-intent searches** (physio near me, women's physio, pelvic floor, postnatal)
instead of our own brand name and random clinic queries.

> Written for someone new to Google Ads. Do the steps in order. You do **not**
> need to touch code for any of this except the one-time conversion setup in
> §6, which is two environment variables.

---

## 0. The problem (from our own Search Terms report)

In a recent month we spent on queries like:

| Search term | Clicks | Why it's a problem |
|---|---|---|
| goji physio / goji physiotherapy / goji women's… | ~35 | **Our own brand.** These people already know us; we'd get them for free. |
| serangoon polyclinic, ang mo kio community hospital | ~27 | **Irrelevant.** Broad matching to unrelated clinics (some already excluded). |
| chiropractor near me, yishun 诊所 | few | **Off-target.** Not our service. |
| physio near me, women's physio, pelvic floor, postnatal | ~0 | **The ones we actually want — barely showing.** |

Two root causes, and the rest of this doc fixes them:
1. **Brand and cheap junk eat the budget** (usually a Smart/Performance Max campaign, or broad match with click-based bidding).
2. **No booking signal**, so Google optimises for cheap clicks (brand) rather than the searches that produce bookings.

Our priority terms (from `marketing/AGENTS.md`): *women's physio singapore, postnatal
physio, pelvic floor physiotherapy, physiotherapy [neighbourhood], physio near me,
branded.*

---

## 1. Check your campaign type first

Left menu -> **Campaigns** -> look at the **Type** column.

- **"Smart"** or **"Performance Max"** -> this is the biggest issue. They give you
  almost no keyword control and love cheap brand/loose traffic. **Create a new
  "Search" campaign** (steps below) and pause the Smart/PMax one once the new one
  is running.
- **"Search"** already -> good, we'll just restructure it.

---

## 2. Split brand into its own campaign (or pause it)

Brand clicks are cheap but low value - you likely rank #1 organically for "goji
physio" already. Don't let them spend the budget meant for high-intent terms.

- **Simplest:** in your main (non-brand) campaign, add your brand words as
  **negative keywords** (see §5) so brand never shows there.
- **Optional:** make a separate "Brand" campaign with a small daily cap ($2-3/day)
  if you want to defend against competitors bidding on your name. Otherwise skip it.

---

## 3. Structure: ad groups mapped to landing pages

One campaign ("Goji - Search - Non-brand"), a few tightly-themed **ad groups**.
Each ad group points its ads at the **most relevant page** - this raises your
Quality Score, which makes you show for the right terms at a lower cost.

The current ad-group → landing-page mapping lives in
`google-ads-campaign-plan.md` §3 (the site now has dedicated money pages:
`/services/pelvic-floor-physiotherapy`, the postnatal/prenatal service
pages, and `/physiotherapy-lentor`).

Send booking-ready traffic to `/book`; send "learn about it" traffic to the
matching condition page (which has its own WhatsApp + Book buttons).

---

## 4. Keywords (use phrase and exact match, not broad)

Match types control how loosely Google matches. **Broad match** is what pulled in
"chiropractor near me" and "serangoon polyclinic". Use **phrase** (`"..."`) and
**exact** (`[...]`) instead.

**Women's / pelvic health ad group**
```
"women's physiotherapy"        [womens physio singapore]
"pelvic floor physio"          "pelvic floor physiotherapy"
"womens health physio"         "pelvic physiotherapist"
```
**Postnatal / pregnancy ad group**
```
"postnatal physio"             "postpartum physio"
"prenatal physiotherapy"       "pregnancy physio"
"diastasis recti physio"
```
**General physio / near me ad group**
```
"physio near me"               [physiotherapy near me]
"physiotherapy lentor"         "physio lentor"
"physiotherapy clinic singapore"
```
Add a few more as you see good real search terms come in (Campaigns ->
**Search terms** -> select a good one -> "Add as keyword").

---

## 5. Negative keywords (stop the waste)

Campaign -> **Keywords** -> **Negative keywords** -> add:
```
polyclinic          community hospital     hospital
chiropractor        chiro                  massage
sports massage      诊所                    tcm
government           subsidised             free
job                 jobs                   course     salary
```
And in the non-brand campaign, add your brand as negatives so it stays separate:
```
goji        "goji physio"        "goji physiotherapy"
```

---

## 6. Conversion tracking - the highest-leverage step

Right now Google has no idea which clicks turn into **bookings**, so it optimises
for cheap clicks. Once it can see bookings, it will chase the searches that
produce them. The website is already wired to fire a "booking confirmed"
conversion - you just need to create the conversion action and paste two IDs.

**a. Create the conversion action in Google Ads**
1. **Goals -> Conversions -> Summary -> + New conversion action**.
2. Choose **Website**.
3. When asked to set it up, choose **"Set up conversions manually using code"**
   (we fire it ourselves; you do not need to install a global tag by hand).
4. Name it `Booking confirmed`. Category: **Submit lead form** (or **Book
   appointment** if offered). Value: you can leave "Use different values" - the
   site already sends the session price. Count: **One**.
5. Save. Google shows you a **Conversion ID** (looks like `AW-123456789`) and a
   **Conversion label** (looks like `abcDE_fGhIJ123`). Copy both.

**b. Give the site those two IDs** (Cloudflare Pages -> **goji** project ->
Settings -> **Environment variables**, Production):
```
PUBLIC_GADS_ID              = AW-123456789
PUBLIC_GADS_BOOKING_LABEL   = abcDE_fGhIJ123
```
Then **redeploy** the site (Astro bakes these in at build). That's it - a
confirmed booking now reports a conversion valued at the service price. (These are
inert until set, so nothing tracks until you add them.)

**c. Verify:** make a test booking on the live site, then in Google Ads open
**Goals -> Conversions** a few hours later - you should see one "Booking
confirmed". (Google can take a few hours to show conversions.)

> Alternative if you prefer GA4: set `PUBLIC_GA4_ID`, link GA4 to Google Ads
> (GA4 Admin -> Product links -> Google Ads), and import the `booking_confirmed`
> event as a conversion. The site fires that event too. Either path works; the
> direct Google Ads tag above is the simplest.

---

## 7. Bidding

- **Before** conversions are tracked (§6): set the campaign to **Maximize clicks**
  with a **max CPC limit** (e.g. $3-4) so a single click can't blow the budget.
  Tight keywords + negatives keep it sane.
- **After** you have ~15-30 conversions: switch to **Maximize conversions**
  (optionally with a target CPA once you know your cost per booking). Now Google
  optimises toward bookings.

---

## 8. Location and schedule

- **Locations:** target **Singapore**, and add a **radius** (e.g. 8-10 km) around
  **Lentor Modern** with a bid boost - "near me" and local intent lean on this.
- **Location settings:** set to **"Presence: people in your targeted locations"**
  (not "interest"), so you don't pay for people overseas researching.
- **Ad schedule:** optional - concentrate budget during clinic hours if you want
  calls/messages answered promptly.

---

## 9. Budget

Small and steady beats bursty. Start where you are (~$3-5/day on non-brand),
watch the **Search terms** report weekly for the first month, and move budget
toward the ad groups that produce bookings once §6 is live.

---

## 10. The "near me" organic side (Google Business Profile)

For "physio near me" and "women's physio near me", the Google **map pack** (the
local results with the map) often matters more than ads - and it's free. Make sure
your **Google Business Profile** is complete:

- **Primary category:** Physiotherapist. **Additional:** Women's health clinic,
  Physical therapy clinic.
- Correct name, address (Lentor Modern #01-13), phone, website, and hours.
- Services listed (prenatal, postnatal, pelvic health, paediatric, Pilates, S&C).
- Real photos of the clinic and team.
- Ask happy patients for Google reviews (within compliance - no incentives).
- Post occasional updates (offers/education) via GBP Posts.

The website already ships LocalBusiness / MedicalClinic structured data and an
`llms.txt`, which reinforce the same name/address/phone/services to Google and AI
answer engines.

---

## Quick checklist

- [ ] Campaign is **Search** (not Smart/PMax)
- [ ] Brand split out or added as negatives in the non-brand campaign
- [ ] Ad groups themed and pointed at the matching landing pages
- [ ] Keywords in **phrase/exact**, not broad
- [ ] Negative keyword list added
- [ ] **Auto-tagging ON** (Admin -> Account settings)
- [ ] Final URL suffix: `utm_source=google&utm_medium=cpc&utm_campaign={campaignid}`
- [ ] Conversion action created; `PUBLIC_GADS_ID` + `PUBLIC_GADS_BOOKING_LABEL` set in Cloudflare; site redeployed
- [ ] Bidding: Maximize clicks (capped) now -> Maximize conversions after ~15-30 bookings
- [ ] Locations: Singapore + radius around Lentor, "presence" only
- [ ] Google Business Profile complete for the "near me" map pack
