# Episode 2 hard-scene H3 tests — review

27–28 November 2026 · private review (H3 output carries a territorial licence restriction).
Scripts, prompts, take records and Blender sources are on the public goji branch
`marketing/h3-ep02-hard-scene-tests`; no footage is there.

**Bottom line.** For Episode 2, use H3 Ref2VA at the draft recipe (Turbo 4-step v0.1,
576×1024) with the six-section prompt and the raw Blender clip as `<Video 1>`, in takes of
8 seconds or less. Two staging rules make that work: keep handled props visible above any
occluding edge, and render every person who has no reference image as grey clay in the
guide. With those, every six-section take on the fixed T01 and T02 guides completed its
action on both seeds. Nothing is production-ready yet, for three reasons: interior people render as
smooth modern 3D rather than PS2, the 15-second take breaks after 4.75 s, and the cast
turnarounds are unreviewed (cast fidelity is **not assessed** throughout).

## Recommendation per kind of shot

| Shot type | Use | Evidence |
|---|---|---|
| Walk with NPCs, occlusion, rear-follow camera | Draft recipe, six-section prompt, Blender `<Video 1>` with NPCs as grey clay | T01 clay: 2/2 complete, all humans in one look |
| Hand–prop contact (bag on table) | Same, with the prop staged above occluders in camera | T02 v2: 4/4 contacts held (B and L); original guide 1/4 |
| Two-character interaction with turn and gesture | Same | Turn and gesture followed the guide in every take |
| Sustained action longer than 8 s | Plan 8 s takes or deliberate cuts; continuation from a clean tail (one join gave 9.13 s clean) | T03 native 15 s: clean 4.75 s only |
| Final quality pass | Keep the draft canvas for now; 768p 8-step is sharper but rebuilt the set from the reference picture on 2/2 | T02 C |
| Exact geometry from a depth pass | Do not use Fun ControlNet with cast references | D at 1.0 ignored layout; D2 at 2.0 lost ponytail, set and bag shape |

## Scorecard summary

Scores 0–2 (production.md): style · structure · contacts · camera · time. Cast is not assessed.
Usable = seconds of the required action that pass; a take that fails the required action scores 0.

| Test | Variant | Seed 1017 | Seed 2026 | Usable | Min/take |
|---|---|---|---|---|---|
| T02 bag + therapist | A prose + bans | 1·0·0·0·0 | 1·1·0·2·2 | 0 / 0 s | 29–30 |
| T02 | B six-section | 1·2·0·2·2 | 1·2·1·2·2 | 0 / 8 s | 30–31 |
| T02 v2 guide | B | 1·2·2·2·2 | 1·2·2·2·2 | 8 / 8 s | 30–31 |
| T02 v2 | C 768p 8-step v1.1 | 1·1·2·2·2 | 1·1·2·2·2 | 8 / 8 s, set drift | 101–104 |
| T02 v2 | D depth ControlNet 1.0 | 1·0·0·0·2 | not run (control changed) | 0 s | 29 |
| T02 v2 | D2 depth ControlNet 2.0 | 1·1·1·2·2 | not run | 0 s (identity lost) | 28 |
| T02 v2 | L look anchored to street ref | 1·2·2·2·2 | 1·2·2·2·2 | 8 / 8 s, no change vs B | 25–31 |
| T01 walk + occlusion | B | 0·2·2·2·2 | 0·2·2·2·2 | 0 / 0 s (NPC proxies) | 29 |
| T01 clay NPCs | B | 2·2·2·2·2 | 2·2·2·2·2 | 8 / 8 s | 25–30 |
| T03 squats | B native 15 s | 1·0·1·1·0 | not run | 4.75 s of 15.08 | 75 |
| T03 | Continuation (tail f93–114) | 1·0·1·1·0 | — | 0 s (inherited defect) | 45 |
| T03 | Continuation (clean tail f79–100) | 1·1·2·2·1 | — | 4.92 s new; 9.13 s joined | 44 |

"Style 2" on T01 clay means every human matches the Episode 1 street reference; it is not a
reviewed PS2 lineup. A–D follow your brief; the v2 guide, D2, clay and L are control changes
made when a variant failed for a structural reason, as the skill's experiment rules ask.

## What still fails

- **Interior look.** Every interior take renders smooth modern 3D people, matching the Episode 1
  reception image rather than PS2. Prompt text cannot move it (L was identical to B on two seeds).
  Interiors need a reviewed PS2 interior look frame.
- **Long takes.** The native 15 s take grew a duplicate therapist at 4.75 s and dissolved into a
  different gym at ~10 s (one seed). Continuing from a clean tail worked at the seam and gave
  9.13 s joined, but the same barbell-gym drift returned 5.8 s into the continuation. It looks
  like a squat-scene prior; try wording the action without "squat" or cutting before 5 s.
- **768p final.** Sharper, ~3.5× the compute, and it rebuilt the set from the reference picture on
  both seeds. Its shift (12 / 3) is inferred from lightx2v's v1.0 post; no source confirms it for v1.1.
- **Timing lag.** Occlusion and gestures land up to ~0.5 s after the guide.
- **Human review.** I inspected contact sheets, guide/take pairs and frame grids around every contact
  and seam. I have not watched the MP4s at normal speed; please do before choosing.

## Guidance that turned out wrong (fixed on the branch, draft PR)

1. "8–15 s can be one take" — at the draft recipe only 8 s held; the 15 s take broke at 4.75 s.
2. `attribute_transfer` placeholder wording replaces proxies — only for subjects with a reference image;
   text-only NPCs kept proxy colours until rendered as clay.
3. Fun ControlNet as the "candidate replacement" — tested and not adopted.
4. Draft timing "13–17 min per take" — 25–31 min per 8 s take with three references; 75 min at 15 s.
5. The 768p 8-step shift was undocumented — recorded as inferred 12 / 3, with sources.
6. New staging rule: keep handled props above occluders in camera (bag 1/4 → 4/4).
7. New prompt evidence: a prose prompt calling `<Picture 1>` "the appearance reference for the whole
   shot" copied its composition for the first second, then dissolved; six-section prompts never did.

Compute: 13.0 h local (M5 Pro), no paid services. New downloads (hash-checked): Ref2V Turbo
8-step v1.1 768p adapter, Fun ControlNet Union pruned bf16 — see `h3-weights-ep02.json`.
