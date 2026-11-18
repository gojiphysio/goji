# SEO / AEO audit — 2026-11-11

Second November tick. #224 (the 4 Nov run, which measured no engine) and its
fixes #222/#223 merged today, so this run is the first November engine data.
SG IP, home line (AS56300 MyRepublic, no VPN). Google was still skipped: the
loop treated the SG IP as a VPN, and the browser pane is the signed-in one
(see 26 Oct method notes).

Files: `live/`, `dist.json`, `aeo-chatgpt-sg-ip-loggedout.json`.

## Scoreboard (shared ids only)

| Engine | Metric | 26 Oct | 11 Nov |
|---|---|---|---|
| ChatGPT (logged out, sg-ip) | Goji named | 11/45 · 12/47 | **12/45 · 14/47** |
| ChatGPT | gojiphysio.com cited | 12/47 | **14/47** |
| Claude (Incognito) | Goji named | 15/45 | **not measured**: claude.ai signed out |
| Google AIO / Maps pack / organic | — | 8/35 · 8/35 · 3/35 | **not measured**: skipped |
| Search Console | 28d vs prior 28d | — | **not measured**: `bq` reauth needed |

ChatGPT's logged-in series still can't resume (login expired). The 7 `blog-*`
queries were not run, so the logged-out series stays at 47 ids.

## What moved (ChatGPT, logged out)

- **Newly named (5):** women's physio (#2), women's health physio (#3),
  postnatal (#2), menopause (#5), private reformer (#6).
- **Lost (3):** prenatal (was only a price example), C-section, DDH.
- **Up:** home visit #4→#2; pelvic pain from price example to #3. Private
  Pilates still #1.
- **Wrong fact:** home visit quoted at **S$330** in 3 answers (local-wh-lentor,
  wedge-postnatal, wedge-home-visit). The site says S$380; S$330 is the
  in-clinic Mummy & Baby assessment. Minor: Sundays/PH said "Closed" (site:
  closed, by appointment only). All other prices, staff, address and hours
  correct.
- Every Goji booking link ChatGPT shows is `/book/?service=private-pilates`,
  even on general physio questions.

## Technical (live audit + build check, before #222/#223 deployed)

Same as 4 Nov: `/team/` 404 (fixed by #223), postpartum title 67 chars
(fixed by #222), Zaobao press title 82 chars, sweatboxyoga link 502,
`PSI_API_KEY` unset.

## Next, by tier

**Owner / operator:**
1. Sign claude.ai and ChatGPT back in to the browser pane; ChatGPT
   personalisation off.
2. `gcloud auth login` as hello@gojiphysio.com for Search Console.
3. Carried over: GBP categories + review asks, Instagram/LinkedIn website
   link, old Squarespace takedown, roundup outreach.

**B — Cheryl:** make the home-visit price unambiguous where both S$330 and
S$380 appear on one page (the source of ChatGPT's mix-up), after checking
which pages pair them.

**C — Charles:** `AGENTS.md` method notes are stale: logged-out ChatGPT `?q=`
no longer auto-sends (type + Enter), and Web search sits under "+". Also
"SG IP" ≠ VPN; the loop should check ipinfo `org` before skipping Google.
Zaobao `seoTitle`; dead sweatboxyoga link; sitemap `lastmod`; `PSI_API_KEY`.

**A — loop:** none open; #222/#223 merged.
