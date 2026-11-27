# Episode 2 hard-scene H3 tests (27–28 November 2026)

Paired tests of the rewritten H3 guidance on the three hardest Episode 2 scenes, before any
full-episode render. Findings, scorecards and recommendations are in
[review-notes.md](review-notes.md). Generated H3 footage carries a territorial licence
restriction, so the takes, contact sheets and MP4s are on a private review page only.

| Path | What it is |
|---|---|
| `scripts/stage_ep02.py` | Blender proxies and guides: `t01` walk/occlusion, `t02` bag + therapist, `t02v2` bag lifted above the table edge, `t03` 15 s squats (532 frames for continuation ranges); `--clay` renders NPC proxies as grey clay |
| `scripts/package_guides.py` | Encodes guides on the 17k+5 grid and hashes them into `guides.json` |
| `scripts/prompts_ep02.py` | Builds every prompt (`prompts/ep02-prompts.json`): A prose with exclusions, B six-section, D without `<Video 1>`, L street-anchored look, continuation |
| `scripts/run_ep02.py` | Submits a take to ComfyUI and writes its record to `takes/`; footage goes to `~/Projects/goji-ep02-runtime/takes/` outside the repo |
| `scripts/review_take.py`, `scripts/make_review.py` | Review sheets and the private review page |
| `evaluations.json` | Per-take scorecard, failure timecodes and usable seconds |
| `h3-weights-ep02.json` | New downloads with hashes, revisions and the shift source for the 768p adapter |
| `staging/*/stage.json`, `staging/*/sheet-*.jpg` | Per-frame transforms and contact sheets of the Blender guides (proxies, not cast) |

Every figure in the guides is a labelled proxy. Cast fidelity is not assessed: the cast
turnarounds have not been reviewed.
