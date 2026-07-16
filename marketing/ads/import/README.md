# Google Ads bulk-import CSVs

Importable CSVs generated **from `../google-ads-campaign-plan.md`** (the source
of truth — never hand-edit these; regenerate instead). They save the operator
from hand-typing the campaign into the Google Ads UI.

**Scope: AG2–AG4 only.** AG1 (pelvic floor) is intentionally excluded because
its landing page is held (`draft: true`) pending Kristy's copy + photo — see the
plan's §3 note. Regenerate to include AG1 once that page is live.

## Files
| File | Contents | Google Ads Editor import target |
|---|---|---|
| `keywords.csv` | 27 phrase/exact keywords, AG2–AG4 | Keywords |
| `responsive-search-ads.csv` | 3 RSAs (10 headlines + 4 descriptions each), with final URLs | Responsive search ads |
| `negative-keywords.csv` | 25 shared campaign negatives incl. brand negatives | Campaign negative keywords |

## How to import (Google Ads Editor)
1. Create the campaign shell first in the UI/Editor — type **Search**, budget,
   bidding, geo, and the final-URL suffix per the plan §2 & §8 (these are
   campaign-level settings, not in these CSVs). Name it exactly
   **`Goji - Search - Non-brand`** so the CSV `Campaign` column matches.
2. Editor → **Account → Import → From file** (or Ctrl/Cmd-V paste) → select each
   CSV. Editor matches on the `Campaign` / `Ad group` columns and creates the
   ad groups if they don't exist.
3. Review the proposed changes, then **Post**.
4. Copy is Lane-A compliant and char-limit-validated, but **Cheryl still signs
   off before the ads serve** (plan §6). One flag for her: the AG1 headline
   "Leakage Is Common & Treatable" (AG1 is held anyway).
5. Extensions (sitelinks/callouts/snippets) are set in the UI — plan §7. Do
   **not** add the "Pelvic floor physio" sitelink until that page is live.

## Regenerate (after editing the plan, or to add AG1)
```
cd marketing/ads && python3 import/generate.py
```
Re-parses the plan and rewrites all three CSVs. To add AG1, un-hold the page,
then add its row to the `AG` map in `generate.py`.
