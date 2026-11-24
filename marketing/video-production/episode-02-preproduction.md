# Episode 2 — a repeatable Goji game world

**24 November 2026 · Preproduction and research, not a rendered episode.**

The immediate change is to make our characters, sets and camera behaviour
reusable. Episode 1's last full edit is 30.8 seconds, with a separately corrected
final squat scene. It works as a cut, but its recorded driving-direction and
door/contact problems show why the next episode needs controlled staging.

The reusable [Goji GTA video skill](skills/goji-gta-video/SKILL.md) is the workflow
entry point. The [illustrated series bible](skills/goji-gta-video/references/series-bible.md)
preserves the existing girl and therapist, and tightens the PS2 standard for
all NPCs. The [research and model comparison](skills/goji-gta-video/references/research-2026-11-24.md)
includes Reddit reports and official model sources. The [production protocol](skills/goji-gta-video/references/production.md)
contains the shot record, test criteria and revision rules.
The [Blender staging contract](skills/goji-gta-video/references/blender-staging.md)
and [editable shot template](skills/goji-gta-video/assets/shot-template.yaml)
turn those decisions into a reusable scene and export record.
The [San Andreas reference pack](skills/goji-gta-video/references/san-andreas-reference.md)
adds source-platform checks, timestamped game actions and proposed character,
vehicle and camera behaviours. Its [editable presets](skills/goji-gta-video/assets/behaviour-presets.yaml)
are ready for staging experiments; they have not been rendered or calibrated to
PS2 handling measurements.

## What we keep and what we establish

Keep the maroon-clad, ponytailed Goji girl, her single black handbag, the
short-bobbed physiotherapist in black with a plain back, the Singapore setting,
rear-follow exterior camera and calmer interior cutscenes.

Establish reviewed multi-view character sheets, a small NPC roster, consistent
character scale, reusable location layouts and camera marks. Every person must
look like a character from the same PS2 game. The older interior reference has
smoother rendering than the street scene; its character/clothing information is
useful, but it is not an exemption from the stricter shared style.

## Blender workflow now chosen

The user prefers low-poly 3D staging. Build a small recurring cast and set kit,
then animate each scene from those assets. The model comparison runs separately
in `local-benchmark/`; a taxi interaction there is a technical test inspired by
Episode 1, not the chosen Episode 2 story. Its proxy characters do not establish
new canonical faces, and this workflow document does not claim benchmark results.

The first asset pass should solve appearance and reuse in this order:

1. **Cast lineup:** GG-01, GP-01 and one needed NPC together under neutral light.
   Match the inherited identities, relative scale, painted detail and PS2 shading.
   Save front, rear and three-quarter views from the same assets.
2. **One exterior set:** reusable road, kerb, sheltered walkway and entrance;
   establish camera marks and a reverse view of the same layout. Extend it only
   as shots require. Keep illustrative geography labelled.
3. **One interaction:** stage the full action with visible contact and release,
   fixed prop ownership and a settled endpoint. Validate its timing before
   building a longer sequence around it.
4. **Look and export preset:** record the actual camera projection, light,
   materials and colour transform. Produce a clean opening look frame and only
   the aligned control passes supported by the selected renderer.

Review gates are quality checks, not repeated permission requests. A motion
blockout can proceed with clearly labelled proxies; final identity/style review
needs the reviewed cast. Keep direct Blender output available for interactions
whose rigid geometry remains unreliable in generation. Model choice can change
without rebuilding the cast, set or timed action.

## Working Episode 2 concept

**Provisional: “Return to Goji — new mission.”** The story has not been supplied
or approved. This sequence is a practical continuity test and starting point,
not a commitment to repeat Episode 1 or its taxi gag. Replace it when the user's
story arrives. No dialogue, clinical benefit claim or final CTA copy is locked.

| Beat | Proposed screen time | Action and production purpose |
|---|---|---|
| Return to the neighbourhood | 0–8s | Rear-follow walk past two NPCs; brief occlusion and reappearance tests identity and all-human style. |
| Mission entrance | 8–16s | Continue to the yellow Goji marker; finish the walk before the intentional loading transition. Tests camera/motion continuity. |
| Familiar therapist | 16–24s | Girl enters, sets her handbag down visibly, and exchanges a simple greeting gesture. Tests two identities and prop state. |
| New mission payoff | 24–32s | One clear, guideable movement or comic pose; the therapist reacts. Editable mission UI carries the payoff. Exact action awaits story choice. |

Target is provisionally around 32 seconds. Leave room to alter pacing after the
animatic. Fewer, sustained scenes are the test objective; there is no need to
force a 32-second single take or pad an action to meet a model's duration ceiling.

## Pilot before episode production

The original chat owns the current local-model pilot and its take log. The tests
below are proposed follow-on coverage; no passing results are asserted here.

**T01 — 8-second walk and occlusion.** Girl, two differently dressed NPCs,
fixed rear-follow camera, then stop. All faces, bodies and extras retain the
PS2 look. No outfit or handbag change when the girl reappears.

**T02 — 8-second two-character interaction.** Girl puts the handbag on a fixed
surface; therapist turns and gestures. Keep both in the same shot, with a simple
set and visible hands. Check cast separation, contact, scale and geometry.

**T03 — 15-second sustained action and one extension.** Advance only passing
models. Use a guide for the complete action and test continuation from a moving
tail. Check the joined shot against original references. Label native generation
and extension separately. Only then test a 20–30-second scene where supported.

Use the [scorecard](skills/goji-gta-video/references/production.md#model-comparison-that-measures-production-value):
identity, all-human style, structure, contacts, camera and time continuity.
Record longest usable take, total attempts, wall time, hands-on repair and cost
per accepted second. Two initial takes per candidate expose some repeatability;
they are a pilot, not statistically conclusive benchmarking.

## Model testing and practical constraints

The active local comparison covers LTX-2.5, Wan and MiniMax H3 subject to verified
runtime feasibility. The model-testing chat owns downloads, credentials, exact
profiles, inference and measured results; this workflow chat should not duplicate
those jobs. H3 access has been enabled for the approved Singapore-based test.

Keep a common-first-frame baseline separate from each model's native-control
track. Start with a complete action inside the practical shared native duration,
then test longer scenes and continuation. Record exact model/runtime revisions,
resolution, native FPS and supplied controls. A proxy-based pilot measures
structural feasibility and appearance stability, not final cast fidelity.

Paid models remain possible later if local results fail the required action;
no paid generation is authorised by this plan. Use the research as a dated
candidate list and verify current access, controls and cost before any such run.

Do not run every model in the catalogue. If no candidate preserves rigid
geometry, use a small reusable low-poly 3D scene and render that action directly
or use it as the structural guide. The first investment should solve a repeated
shot requirement, not build an entire virtual city.

## Ready now / still to do

- Ready: research, reusable skill, recovered reference PNGs with hashes, cast and
  world bible, proposed cameras, Blender staging/export contract, editable shot
  record, test scenarios and acceptance criteria.
- Still to do: final Episode 2 premise; reviewed turnarounds/NPC lineup and set
  masters; episode-specific timed animatic; completed model comparison and final footage.
- Nothing has been posted to Instagram. No video-generation credit was spent.

The source skill lives in `marketing/video-production/skills/goji-gta-video/`.
An installed copy in `~/.codex/skills/goji-gta-video/` supports reuse on Tidepool.
Update the source and refresh that copy together; the assets travel with it.
