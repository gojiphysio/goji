# SEO / AEO audit — 2026-10-26

Two weeks after the tier A fixes shipped (#133-#140, 14-19 Oct). Query set
`../../aeo-queries.json` (now 47 queries; the 2 private-Pilates queries are new,
so trends use the 45 shared ids). Home SG IP (MyRepublic, no VPN).

Files: `aeo-google.json`, `aeo-claude-ai-sg-ip.json`,
`aeo-chatgpt-sg-ip-loggedout.json`.

## Scoreboard (shared ids only)

| Engine | Metric | 12 Oct | 19/20 Oct | 26 Oct |
|---|---|---|---|---|
| Claude (Incognito, sg-ip) | Goji named | n/a | 13/45 | **15/45** |
| Claude | gojiphysio.com cited | n/a | 0 | 0 |
| ChatGPT | Goji named | n/a | 17/45 (logged-in temp chat) | 11/45 (logged out, **different mode**) |
| Google AI Overview | Goji in AIO | 10/35 | 3/36 | 8/35 · 7/36 |
| Google Maps pack | Goji in pack | 12/35 | 7/36 | 8/35 · 8/36 |
| Google Maps pack | Goji **#1** | **9**/35 | 1/36 | **1** |
| Google organic | Goji on page 1 | 6/35 | 5/36 | 3/35 · 4/36 |

26 Oct Google is shown against each baseline's shared ids (35 / 36).

ChatGPT ran logged out because the owner's account had Memory switched back
on; it starts a new series and is not a trend against 20 Oct. On it, Goji is
named 12/47, every time with a gojiphysio.com citation, and no fact is wrong.

## Search Console (11 days either side of 14 Oct)

| | 3-13 Oct | 14-24 Oct |
|---|---|---|
| Clicks | 70 | 68 |
| Impressions | 1,638 | 1,926 (+18%) |
| CTR | 4.3% | 3.5% |
| Avg position | 8.5 | 15.4 |

Position drop is mix: new condition/Private Pilates pages earning impressions
at 30-57. Existing money queries improved (postnatal 4.5→1.4, prenatal
3.7→2.3, women's health 2.4→1.8). Homepage impressions −29% (808→577), mostly
"postpartum gym singapore" 41→0. Google reports `/conditions/dry-needling`
(no slash) as its own page.

## Technical (live audit + build check)

Fixed since 12 Oct: hub 404, 22 long meta descriptions, homepage H1, clinic
`@id`, llms.txt sync, redirecting internal links 93→18. Open: 18 slash-less
links on `/conditions/`, 4 services without FAQs, 260 KB logo, sitemap
`lastmod` 0, apex https→http hop, no PSI key.

## What moved

- **Maps #1 collapsed (9→1) and has not recovered** since the ~15 Oct profile
  edit. Goji is #2-3 on six wedge queries, mostly behind Embrace (5.0, 185
  reviews vs Goji 24). Dropped from packs on AMK, Katong (now an ad only),
  women's health physio, pelvic pain.
- **Claude improved slightly**: +pelvic-floor-near-me, +prolapse; now says book
  "via WhatsApp or online" (was Instagram). Still lists Goji last as "the pick
  in the north", and brand answers still come from an Instagram mirror
  (imginn) + a staff LinkedIn: "couldn't find their official website or
  pricing". Home visits credited to competitors, never Goji.
- **Google AIO recovered from 19 Oct** (3→7): Goji named first for home
  visits; pregnancy, postnatal, DDH cited.
- **Old Squarespace site** (bison-goby-mrsl.squarespace.com) still indexed;
  #5 for "private pilates lentor".
- **Zero on every engine**: general questions (cost, referral, first visit),
  condition questions, scoliosis, MSK.

## Next, by tier

**Owner / operator:**
1. Business Profile: categories vs Embrace and Calyx; steady review asks
   (24 vs 185).
2. Instagram bio + LinkedIn: website and `go.gojiphysio.com` link first.
3. Take down or redirect the old Squarespace site.
4. Roundup outreach (Little Steps, Expat Living, Sassy Mama, Women's Weekly):
   still 0/4.

**B — Cheryl:** answer-first ledes on pelvic floor, incontinence, prolapse,
PGP, menopause; cost / referral / first-visit pages; FAQs on Clinical
Pilates, MSK, Paediatric, S&C.

**A — loop:** trailing slashes on the 18 `/conditions/` links; logo to WebP.

**C:** sitemap `lastmod`; `PSI_API_KEY`.

## Method notes

- The browser pane got signed in to Google mid-run (SSO from signing in to
  ChatGPT/Claude). Google and logged-out ChatGPT ran in gstack's headed
  browser (`$B connect`), each pinned to its own tab with `BROWSE_TAB`.
  Headless gstack hits Google's "unusual traffic" page at once.
- Before the ChatGPT logged-in series can resume, the owner must switch off
  Memory, Reference record history and Connector search.
