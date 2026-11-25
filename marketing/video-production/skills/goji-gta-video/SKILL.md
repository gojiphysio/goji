---
name: goji-gta-video
description: Plan, generate, revise, and review Goji's recurring GTA San Andreas / PS2-style Singapore Instagram episodes, preserving character, NPC, location, camera, and motion continuity. Use for this series and its video-model comparisons, not Goji's watercolour clips or generic marketing copy.
---

# Goji GTA video production

Build a reusable cast and world, then stage and animate the episode. Optimise for
coherent usable seconds and predictable revision effort. A longer model output
is not proof of a coherent scene; a seed or repeated description is not an identity lock.

## Load only the context needed

- Read [series-bible.md](references/series-bible.md) for every episode. It contains
  existing character references, the PS2 standard, and proposed camera presets.
- Read [san-andreas-reference.md](references/san-andreas-reference.md) for game
  appearance, locomotion, vehicle behaviour or chase-camera work. It links
  timestamped footage and separates observations from proposed Blender presets.
- Read [production.md](references/production.md) when planning or making footage;
  it includes the shot record, continuity gates, and revision procedure.
- Read [blender-staging.md](references/blender-staging.md) when building or reusing
  3D assets, cameras, animatics or control exports. Copy its shot template when
  an existing job format does not already record those details.
- Read [research-2026-11-24.md](references/research-2026-11-24.md) when comparing
  models or changing the workflow. Recheck dated capabilities on the exact runtime.
- Read [local-pilot-2026-11-24.md](references/local-pilot-2026-11-24.md) for the
  proxy pilot, matched Episode 1 rerun and Blender chase control routes; do not turn its single
  seed or five-second result into a general model or long-scene guarantee.
- Read the target repository's `AGENTS.md` and `marketing/AGENTS.md`. For
  patient-facing copy, read `marketing/strategy/03-compliance-guardrails.md`.

## Recover the actual state

Find the current episode's brief, reviewed cut, selected assets, and take log.
Preserve accepted footage and the most recent corrections. For Episode 1,
v8 is the full cut and v9 replaces only its final squat scene; v5 is an earlier
storyboard, not the final motion or wardrobe authority. The bible records provenance.

Separate inherited choices, new proposals, and user approvals. If the story is
missing, ask once while preparing the reusable production pack; label any example
story provisional. Do not turn a proposed camera preset or unreviewed turnaround
into approved series canon.

## Stage before rendering

1. Define the episode's hook, action, payoff and intended length. Plan scenes as
   complete actions, with deliberate cuts. Budget time for movement to finish.
2. Select the same character assets for Goji girl and the physiotherapist; make
   missing views from those assets. Fix character sheets, NPC style, location
   layout and a representative look frame before long renders. Review every
   human, including distant extras and reflections, against the same PS2 standard.
3. Record each shot using the production reference. Attach identity, location,
   style and motion references with explicit roles. Crop individual views from
   sheets for conditioning unless the selected model explicitly supports sheets.
4. Make a timed animatic. For difficult contacts, vehicles or exact camera paths,
   use a simple 3D blockout or driving performance. Validate geometry and motion
   in the guide before paying for, or waiting on, generation.
   Keep blockout proxies distinct from reviewed cast/look assets. A first-frame
   video test inherits the proxy's appearance; it cannot establish final cast quality.
5. For GTA-specific movement, select a relevant game reference and an explicit
   behaviour state (walk/idle, cruise/brake/slide, entry/takeover). Keep PS2,
   remaster and mod provenance distinct. Proposed preset values are not measured
   game physics; preview contacts and timing before adopting them.

## Choose the control and model

**User-selected default, 25 November 2026:** use **H3 Ref2VA with a continuous
video reference** for this series, especially complex action, interactions,
occlusions or camera movement. Keep Blender as the motion and camera foundation.
**H3 with indexed still guides can be the better choice for simpler scenes**;
choose it when sparse anchors are sufficient and review motion between them.
See [production.md](references/production.md#choose-h3-guidance-per-shot) for routing.
This preference supersedes treating LTX as the default starting renderer.

Use LTX or Wan for a specific draft, fallback or requested comparison when useful;
do not rerun a model comparison automatically for every episode.
For visual-quality comparisons, use a reviewed episode image or look frame and
match the conditioning budget, prompt and actual canvas. Keep extra-control
experiments separate from model comparisons; a primitive blockout cannot test
cast likeness or final appearance.

Prefer available local/free routes first; identify paid APIs, subscriptions and
GPU rental explicitly. Research alone does not authorise spending or publishing.
Apply any existing user budget without asking again.

- Appearance across a cut: canonical character + location references and a
  correctly staged new keyframe.
- Continuous movement: native video extension or multi-frame/latent context
  supported by that exact pipeline. A lone last image does not carry velocity.
- Hand contact, body mechanics, rigid objects: pose/depth/layout/motion controls;
  consider a directly rendered 3D shot if exact geometry is essential.
- Persistent character/style failure across otherwise valid shots: consider a
  model-compatible character or style LoRA after references have been cleaned.

Check model version, mode, reference restrictions, aspect ratio, duration,
resolution and hardware before constructing a job. Do not assume first/last
frames and multiple references can be combined. Do not transfer LTX, Wan or H3
conditioning syntax between pipelines. Keep one renderer within a continuous
shot where practical; compare look matching before mixing renderers across cuts.

## Generate, inspect, decide

Start with the hardest continuity test, not a batch of the whole episode.
Log all attempts, controls, source hashes, runtime, cost, retained ranges and
failure reasons. Change one major variable per retry. After three attempts with
the same structural failure, change the guide/control/model or staging instead
of adding more adjectives. This is a default experiment budget, adjustable to
the user's task and compute allowance.

Review normal-speed playback, slow playback around interactions and seams, and
start/middle/end frames. Check identities, NPC rendering, direction, geometry,
contacts, wardrobe, props, reflections and camera motion. Reject failures inside
the required action even if an attractive fragment could be rescued. Review
extensions against the original references, not just the preceding generation.

Keep raw takes; assemble by source frame index. Overlay HUD, signs requiring
exact lettering, subtitles and audio separately where practical. Apply the
shared look once; do not bake repeated grades into continuation inputs. Do not
use photorealistic face restoration on deliberately low-poly people.

## Deliver and retain learning

Provide a mobile-readable HTTPS review page with embedded frames, MP4 links,
selected-take records and clear remaining issues. Verify the links and preserve
repository access controls. Keep sound stems and overlays editable. Follow the
series audio choice; Episode 1 used original SFX and no music, which is not a
blanket ban on music in future episodes.

Customer CTAs use a verified `https://go.gojiphysio.com/<slug>` redirect.
Do not invent a slug, use raw booking/WhatsApp destinations, or frame fictional
game stats as guaranteed treatment results. Publishing remains a separate action.
Capture demonstrated workflow lessons in the nearest `AGENTS.md` and update
the canonical skill in the repository before refreshing the installed copy.
