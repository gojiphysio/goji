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

## Blender-guided chase: later controlled test

The [chase protocol and take log](https://github.com/gojiphysio/goji/blob/codex/goji-episode1-model-comparison/marketing/video-production/chase-benchmark/README.md)
use an Episode 1 styled conversion of a Blender rear-follow shot with two
overtakes. Its six stills and continuous clip share decoded pixels. The source
master is 576×1024; every model receives the same 288×512 guide pixels with
576×1024 requested outputs. This guide scale is a local memory choice for this test,
not a required production resolution.

Choose the checkpoint **and runtime route**, not just the model family:

- H3 **Ref2VA** in Comfy supports six indexed `MiniMaxH3AddGuide` nodes and
  native reference video. The earlier installed MLX **FL2VA** route does not
  establish either capability. Six ordered appearance references are not the
  same as six indexed guides. Ref2VA uses its own Turbo adapter.
- LTX's `ICLoraPipeline` Python API accepts empty task-LoRA/video lists. That
  permits the same full-resolution eight-step topology for indexed stills and
  Layout-to-Render video, without a different upscale/refine stage in one cell.
- Wan **VACE Fun** supplies frame/mask controls; the installed Wan I2V route is
  not a substitute. Native VACE mask compression can discard isolated anchors.
  The tested input adapter holds six distinct stills in ±1-frame windows at
  16 fps, and verifies all six effective latent-mask anchors. Describe these as
  windows, not exact single-frame locks.

In this Comfy H3 reference node, 121 video frames silently crop to 107. Repeat
the final frame three times to reach its 124-frame grid, then compare only the
original five seconds. Record native cadence and padding. Verify video decoding
against the PNGs before calling two representations the same input.

H3's indexed-still and video runs took 13:10 and 16:59; both preserved the two
overtakes in sampled review. LTX's six-still run took 4:19, preserving the action
with more changing background detail. These are one-seed, five-second results;
normal-speed production acceptance is pending. Wan results and the LTX video
cell must be read from the current take log, not inferred from support claims.

The styled master was made by H3 and can favor its appearance. Use this test
primarily to compare control methods within a family. The small rear-facing
driver cannot establish face likeness, physiotherapist identity or pedestrian
NPC consistency. Preserve those as separate cast tests.

Those per-run timings exclude the shared **31:08** H3 style conversion. That
first conversion is already a candidate final shot; the extra generations here
are a controlled experiment, not a required second production pass. If Blender
already renders the accepted PS2 assets, use that render as the styled master.
Regenerate a good converted shot only for a specific revision or comparison.

The first native Wan VACE UniPC adaptation produced only colored noise despite
a successful encode. A one-second Euler diagnostic produced a recognizable
scene; full results still require inspection. Treat this as a setup distinction,
not a model-quality loss. Preflight actual guided pixels on the exact backend
before full takes; preserve failed graphs and do not silently tune one member
of a still/video pair. The current take log records the exact replacement recipe.
