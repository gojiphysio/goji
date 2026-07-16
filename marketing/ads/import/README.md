# Google Ads bulk-import CSVs

Importable CSVs generated **from `../google-ads-campaign-plan.md`** (the source
of truth — never hand-edit these; regenerate instead). They save the operator
from hand-typing the campaign into the Google Ads UI.

**Scope: all four ad groups** (AG1 pelvic floor included since its page went live
2026-07-16). The campaign is already built and live — these files are the
regenerable source for re-imports and the weekly negatives ritual.

## Files
| File | Contents | Google Ads Editor import target |
|---|---|---|
| `keywords.csv` | 55 phrase/exact keywords, AG1–AG4 | Keywords |
| `responsive-search-ads.csv` | 4 RSAs (10-12 headlines + 4 descriptions each), with final URLs | Responsive search ads |
| `negative-keywords.txt` | 25 shared campaign negatives incl. brand negatives | Campaign negative keywords (paste, see below) |

## How to import (Google Ads Editor)
1. **Create the campaign shell first** — type **Search**, budget, bidding, geo,
   and the final-URL suffix per plan §2 & §8 (campaign-level settings, not in
   these files). Name it exactly **`Goji - Search - Non-brand`** so the
   `Campaign` column matches.
2. **Keywords + RSAs:** Editor → **Account → Import → From file** → import
   `keywords.csv` then `responsive-search-ads.csv`. Editor matches on the
   `Campaign` / `Ad group` columns and creates the ad groups.
3. **Negatives:** do NOT file-import them. Select the campaign → **Keywords,
   Negative → Make multiple changes → "Add as campaign-level negative keywords"**
   → paste the contents of `negative-keywords.txt` → tick the campaign in the
   destination list → set the pasted column heading to **Keyword** → OK.
4. Review proposed changes, clear any violations, then **Post**.
5. Extensions (sitelinks/callouts/snippets) are set in the UI — plan §7.

### Gotchas learned at launch (2026-07-16)
- **Campaign-name match is exact.** A CSV whose `Campaign` differs (even
  `Non brand` vs `Non-brand`) spawns a *duplicate* campaign. Rename to match
  before importing.
- **Negatives can't be file-imported.** A `Keyword` column is read as ad-group
  keywords, so Editor invents an empty ad group. Use the paste route in step 3.
- **Healthcare policy pre-check** blocks most physio keywords locally. Select
  them → **Request exemption** (they're lawful allied-health services) → Post →
  server-side review clears in hours to ~3 days.

## Regenerate (after editing the plan)
```
cd marketing/ads && python3 import/generate.py     # keywords.csv, RSAs, negatives.txt
cd marketing/ads && python3 import/review_sheet.py > ad-copy-review-sheet.md
```
Both parse the plan (the source of truth). Keyword tokens are extracted by their
`"` / `[` delimiters, so single-spaced adjacent keywords no longer fuse.
