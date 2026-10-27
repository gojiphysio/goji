# Clinical notes → aggregate insights: one-off pull

**Status:** approved to build (Charles, 2026-10-27). Script:
`scripts/clinical_notes_insights/insights.py`. Nothing has been pulled yet;
run order is in **Run steps** below.

## Goal

Turn Plato clinical notes into a handful of **aggregate, de-identified** numbers
for 2–4 blog/press pieces ("what we see in our clinic"), e.g. how far postpartum
clients are from birth at their first visit, which symptoms they come in with,
and what goals they set. Structured Plato fields (tags, age band, sessions) only
get us so far; the detail is in the notes.

## Hard rules

1. **Aggregates only leave the run.** Raw note text is held in memory during the
   run and discarded. It is never written to disk, BigQuery, git, logs, a
   spreadsheet, or sent to any third-party service (including AI APIs).
2. **Raw notes are read only in Plato, by Goji staff.** The extraction is a fixed,
   rule-based codebook (below) that Charles approves. The script prints counts
   only, so the person running it and any assistant helping never see note text.
3. **Small-cell suppression.** Any count under 5 patients is reported as "<5".
   Results are per patient, not per note.
4. **One run, then delete the script's credentials use.** It's a one-off, not a
   pipeline. A future repeat needs a fresh approval.
5. **Clinical framing is reviewed before publishing.** Any number goes through the
   normal tier B review (`marketing/seo/AGENTS.md`): no outcome promises, no
   comparisons, "what we see", not "what you'll get".

## Data source

Plato `patient_note` API (see `plato-api-docs/13-endpoint-reference.md`):

| Call | Use |
|---|---|
| `GET /{db}/patient/note/count` | Size the job first (1 request) |
| `GET /{db}/patient/note?current_page=N` | 20 notes per page |

Step 0 is a **shape check**: fetch one page and print only the field *names*
and note-type values (no text) to confirm these are the clinical/treatment
notes and not just admin notes. If clinical documentation lives elsewhere in
Plato (e.g. `letter` or form templates), stop and revise this plan.

## Not starving online booking

Plato allows **20 requests/minute per API key, clinic-wide**, shared with the
`/book` availability lookups and the ingestion jobs (see
`scripts/booking/DIAGNOSIS.md`).

- Run **11 pm – 6 am SGT**, when booking traffic is near zero and clear of the
  21:00/21:05 patient and contact syncs. `plato_appointments` still runs every
  15 minutes around the clock, so the pacing below leaves it headroom.
- Pace at **1 request every 15 seconds** (4/min, 20% of the budget), leaving
  16/min for the appointments sync and any late-night `/book` visitor.
- Read `x-ratelimit-remaining` on every response; if it drops below 8, pause
  until the next minute. On any 429, back off 5 minutes; after 3 in a row, stop.
- Validate the response shape on every page (Plato changes shapes without
  notice); stop on anything unexpected rather than guessing.
- Estimate: ~280 patients × ~5 notes ≈ 1,400 notes ≈ 70 pages ≈ **20 minutes**.

## Codebook (Charles to edit)

Each feature is a per-patient flag or value derived from that patient's notes by
keyword/regex rules (`RULES` in the script). Charles checks them against ~20
patients' notes in Plato before the full run (`--spot-check`, below).

| Feature | Rule sketch | Feeds which piece |
|---|---|---|
| Weeks postpartum at first visit | "x weeks/months postpartum / PP / post-natal" in first note | When mums first come in |
| Birth type mentioned | C-section / LSCS / vaginal / instrumental | Recovery after C-section vs vaginal |
| Leaking / urgency reported | leak, incontinence, urgency, SUI | "Common but not normal" piece |
| Diastasis measured | DRA / diastasis + finger-width or cm | Diastasis myths |
| Pain location | wrist, neck, back, pelvic girdle, shoulder | "Carrying a baby" injuries |
| Main goal | return to running/exercise, lifting baby, sleep, work | What mums want back |
| Prenatal trimester at first visit | "x weeks pregnant / trimester" | When to start prenatal physio |
| Age-60+ goal (active ageing) | balance, falls, strength, travel | Strength after 60 |

No free text, names, dates of birth, NRIC, phone numbers, addresses or exact
dates appear in the output. Dates are reduced to weeks-since-birth or trimester.

## Output

One table of counts per feature (n patients, % of the relevant group, "<5" if
small), written to the terminal and pasted by Charles into a draft.
That table is the only artefact.

## Consent / PDPA check (before the run)

- Confirm Goji's privacy notice / intake consent covers using records for
  service improvement and anonymised, aggregated reporting. If it doesn't,
  update the notice and limit this run to internal use only.
- Aggregated counts with small-cell suppression are not personal data, but the
  processing step is — hence in-memory only and clinician-approved rules.

## Approval

Charles owns this pull (no clinical sign-off needed to run it).

- [x] Privacy notice covers aggregated, anonymised use (Charles, 2026-10-27)
- [x] Codebook spot-checked against ~20 patients (2026-10-27; pain rule tightened after the first pass)
- [x] Run window agreed: 2026-10-28, 00:15 SGT

## Run steps

Run from a laptop with `PLATO_API_KEY` set in the shell (never pasted into
chat or a file). Every mode prints to the terminal only.

```bash
cd business-intelligence/scripts/clinical_notes_insights
python3 -m pytest test_insights.py -q        # rules on synthetic notes
python3 insights.py shape                    # step 1: 2 requests, field names only
python3 insights.py spot-check --patients 20 # step 2: per-patient flags, no text
python3 insights.py run                      # step 3: full pull, 11 pm–6 am SGT
```

1. **Shape.** Confirms `/patient/note` holds treatment notes and which fields
   carry the patient id, date and text. If the field names differ from the
   script's defaults, pass `--text-field`/`--patient-field`/`--date-field`.
   If the notes aren't clinical, stop and revise this plan.
2. **Spot-check.** Prints patient id + the flags each rule set, for the first
   ~20 patients (a few pages). Open each in Plato and compare; tighten `RULES`
   where it's wrong, re-run. Paging is slow by design, so this takes a few
   minutes.
3. **Run.** Refuses outside 11 pm – 6 am SGT. ~70 note pages + ~15 patient
   pages (for the 60+ group) at 1 request / 15 s ≈ 25 min. Paste the printed
   table below as the record.

## Results

**Shape (2026-10-27):** 1,253 notes (~63 pages). Fields used: `patient_id`,
`timestamp`, `note` (string, up to ~17.5k chars). Page 1 is all
`folder_name = Casenotes`, so these are the clinical case notes. Cancelled
notes (`cancel = 1`) are skipped; drafts are kept. Also present but unused:
`diagnosis` (list), `author`, `signed`, `attachments`.

_Full run not done yet._
