# Measured local taxi pilot — 24 November 2026

**Correction after user review:** this proxy scene did not match Episode 1,
resolutions differed, and guided LTX had extra inputs. Do not use it as a
production visual-quality ranking. The local-only H3 preview was inaccessible.
Use the [matched Episode 1 rerun](https://github.com/gojiphysio/goji/blob/codex/goji-episode1-model-comparison/marketing/video-production/local-benchmark/episode1/README.md)
for the replacement protocol and results.

[Review page, source scene, commands and public videos](https://github.com/gojiphysio/goji/blob/codex/goji-video-workflow/marketing/video-production/local-benchmark/README.md).

This is one original low-poly proxy scene and one seed per visual recipe on
Tidepool's M5 Pro / 64 GB Mac. It tests a woman opening a taxi door, a separate
driver getting out, two background NPCs and a locked camera. It is not an
approved cast test or a general model leaderboard. Human normal-speed
production sign-off remains pending; findings below are from exact-frame
inspection, including contacts and frames between supplied guides.

| Recipe | Wall time | Observed result |
|---|---:|---|
| LTX 2.5 distilled, first frame only | 142 s | Camera drifts, NPC duplicates, driver exit not established |
| Wan 2.2 I2V 14B + four-step Lightning | 979 s | Recognisable exit; vehicle panels/props change; taxi moves late |
| Wan 2.2 TI2V 5B, 25 steps | 725 s | Wrong action, no completed driver exit; smaller 448×800 feasibility canvas |
| LTX 2.5 + six Blender images | 158 s | Closest to staged layout; contact/interpolation defects remain |
| MiniMax H3 Turbo 544p, mixed q4/q6 | 760 s | Strongest common-first-frame action in the sampled sequence |

The H3 take maintains the camera and parked taxi, a single bag and separate
characters while completing a recognisable exit/departure. It does not follow
the exact guide timing/path. Its private preview is retained locally because
the output license has territorial restrictions. The package called `4bit`
uses a q4 conditioner and q6 transformer. A cache-resolution failure was fixed
with an explicit pinned adapter file; it was not a failed visual generation.

Only about five seconds was tested (H3 124/24 = 5.17 seconds). Longer native
shots, continuation and repeatability are still untested. The next comparison must first restore the actual Episode 1 appearance and
match the conditioning budget and canvas before testing more seeds or duration. Do not promote a documented duration limit into a measured
coherence claim.

## Lessons to reuse

- Separate the common-input model test from the extra-control test. Guided
  LTX received six images; the other rows received one.
- Inspect unconditioned midpoints. Matching supplied keyframes is weak evidence
  for coherent motion between them.
- Compare the failing contact with the source guide. The proxy animation had
  approximate reach/seat mechanics; generated motion cannot be assumed to fix it.
- Check actual resolved resolution. Wan's source-aspect rounding made 5B
  smaller than the intended quality target; that limits its interpretation.
- H3 emitted a whole-frame "nearly static" warning despite visible foreground
  action. A locked background dominates that average. Inspect the action region.
- Keep direct Blender output available for exact geometry; test control support separately from model quality. Neither route substitutes
  for reviewed character assets and motion checks.

The test used LTX runtime 0.18.0 and MLX-Gen 0.40.1. Commands, revisions,
input hashes, raw clips, failed launches and precise review limits live in the
linked benchmark. Recheck support on the installed runtime before reusing a recipe.
