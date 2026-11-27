# Production and continuity protocol

This workflow combines Episode 1 failure evidence, linked research, production
judgment and the dated local pilot. Read the pilot for measured results and
review limits; proposed acceptance thresholds below are not model guarantees.

## Separate the four controls

1. **Identity:** who appears, their shape, face, wardrobe and props. Use stable
   canonical references, with separate identity and episode-state records.
2. **World:** where they stand and how the location is arranged. Use an empty
   set, plan, landmarks and camera marks. Image similarity does not prove geometry.
3. **Motion:** how bodies, objects and the camera travel through time. Use video,
   pose/depth, trajectories or a 3D blockout for precise action.
4. **Look:** how everything is rendered and graded. Validate every person and
   material against the series look, not only the lead's face.

The user has chosen low-poly Blender staging as the preferred foundation.
Use a small reusable set and rigged characters to supply camera/pose/depth guides,
or finished shots when geometry must stay exact. A benchmark blockout is not a
reviewed cast library. The [Blender staging contract](blender-staging.md) defines
asset versions, camera calibration, action contacts and export records. Start
with the repeated hard set/action, not a full model of Singapore. Use original
or appropriately licensed assets.

## Stage gates

**Brief → reference pack → timed animatic → continuity test → scene takes → edit.**

A gate means an observable quality check, not a new permission request. Existing
user choices stand. Surface only consequential creative uncertainties. If a
reference fails, repair it before animating. Do not ask video to repair a wrong
seat position, body pose, camera view or uniform while performing a complex move.

The animatic should establish how many real seconds each action needs, its
starting and ending state, and why any cut occurs. Include short edit handles
where useful. Longer scenes can contain planned coverage; an uninterrupted take
must pass as an uninterrupted take. A multi-shot model's “30-second video” may
include cuts, which does not meet a single-take test.

## Choose H3 guidance per shot

The user selected H3 with video reference as the winner on 25 November 2026,
while noting that H3 still guides can win on simpler scenes. Apply that preference
to future Goji GTA episodes; it is a production choice, not a universal leaderboard.

- Default to **H3 Ref2VA with continuous video guidance** when the path or timing
  between poses matters: chases, interacting subjects, contacts, occlusions or
  coordinated camera movement. Stage those relationships in Blender first.
- Consider **H3 with indexed still guides** for a simple action, modest movement
  and a fixed or uncomplicated camera when the intermediate motion can be left
  to the model. Select anchors for that shot; six is the benchmark's count, not
  a universal requirement.
- If a still-guided take loses trajectory, timing, contacts or camera continuity
  between anchors, move to the continuous guide. Do not rescue the required
  action through cuts solely to keep the cheaper control route.
- Stills connected only to `MiniMaxH3AddGuide` are invisible to the text
  encoder. Also connect any still the prompt names to a `ref_images` slot.
- **Tested, not adopted (27 Nov):** Fun ControlNet Union with a Blender depth
  pass plus cast and look references. At strength 1.0 the references won and the
  layout came from a reference picture; at 2.0 the layout held but identity, set
  look and prop shape were lost. Keep the raw Blender clip as `<Video 1>`.

Settings, frame grid, draft and final recipes, and the prompt format are in
[h3-practice.md](h3-practice.md).

Record the chosen route and reason in the shot record. Use the tested Ref2VA
runtime route from the local pilot; the old FL2VA installation is not equivalent.
Review the first usable style-conversion pass as a possible finished shot rather
than automatically adding the benchmark's second rendering pass. Cast, all-NPC
PS2 style and complete-action checks still apply whichever guidance route wins.

## Minimum shot/take record

Store a record alongside every rendered take, using JSON/YAML or the existing
job format. Unknown values remain explicit rather than being invented.
For Blender work, start with the [shot template](../assets/shot-template.yaml)
and add the generation/evaluation fields below. It is a planning record, not
a renderer command or a claim that listed controls are supported.

```yaml
shot_id: EP02-T01
status: planned  # planned / generated / rejected / selected
intent: girl walks past two NPCs, briefly occludes, reappears and stops
required_action_seconds: 8
continuous_take: true
cast: [GG-01, NPC-01, NPC-02]
character_reference_version: pending-reviewed-turnarounds
location_id: LENTOR-WALKWAY-01
location_reference_version: pending-set-master
style_version: PS2-GOJI-v1-proposed
camera:
  preset: PLAYER-A
  aspect_ratio: '9:16'
  horizontal_fov_degrees: 50
  movement: fixed-distance rear follow
blocking:
  start: GG-01 walks away from camera, handbag in left hand
  end: GG-01 stops at marker, handbag remains in left hand
  contacts: feet on pavement; handle attached to handbag
  screen_direction: forward into depth; no reversal
  occlusion: NPC-01 briefly crosses foreground; GG-01 reappears unchanged
references: []  # path/URL, sha256, role, subject, view, approval state
guides: []      # path/hash, pose/depth/layout/motion, frame range, fps
generation:
  provider: null
  model_id: null
  version_or_commit: null
  mode: null
  resolution: null
  fps: null
  frames: null
  seed: null
  prompt: null
  prompt_format: null    # H3: ref2va-six-section / base-three-field
  negative_prompt: null  # only if supported; H3 has none (CFG 1)
  adapter_and_strength: null  # e.g. Ref2V Turbo 4-step v0.1 @ 1.0, or none
  steps: null
  shifts_video_audio: null
  ref_image_size: null   # H3: match / max
  controls_and_strengths: {}
  prompt_enhancement: null
  reference_order: []
  parent_take: null
  continuation_source_frames: null
evaluation:
  wall_seconds: null
  spend_currency: null
  spend_amount: null
  longest_usable_continuous_seconds: null
  retained_source_frames: null  # inclusive start, exclusive end
  failure_timecodes: []
  decision_reason: null
```

Save the actual request/settings in addition to this readable summary. Hash
input images and guides; record provider asset IDs and model workflow commits.
Seeds help reproduce a take in a fixed runtime; equal seeds across models are
not an apples-to-apples latent comparison.

## Prompt construction

Bind references by purpose: identity A, identity B, location, style, motion.
Do not make a pose/reference sheet the literal opening composition. Start from
the staged keyframe and describe the change through time. Keep the invariant
style and character blocks stable, and keep action/camera instructions specific.

**For H3, use its own format.** Write the six Ref2VA sections (or three base-mode
fields) from [the Ref2VA template](../assets/h3-ref2va-prompt-template.md), with
roles set by `<Subject N>` lines and retention markers. Do not reuse the prose
example below or any ban list for H3.

Example of the content to cover, written as prose for a non-H3 image-to-video
mode, after staging the matching frame:

> One continuous eight-second PS2-era game shot. The maroon-clad woman follows
> the pavement away from the rear-follow camera, carrying one black handbag in
> her left hand. A low-poly commuter crosses the foreground briefly; she emerges
> with the same face, ponytail, clothes and bag. She slows and stops at the yellow
> entrance marker. The camera maintains its follow distance, height and heading.
> Every person, including both background commuters, has the same angular mesh,
> painted texture detail and diffuse shading as the supplied style reference.
> The set, sun direction and sidewalk geometry remain fixed. No shot change.

This is a motion-test prompt, not final Episode 2 copy. If a provider has no
negative-prompt field, use positive constraints and concise exclusions in its
supported prompt syntax. Do not paste a huge universal negative prompt into all
models. Disable or inspect prompt enhancement when it adds modern realism.

## Continuous-shot extensions

- Preserve the clean original, then extend its clean moving tail with the
  runtime's supported video/latent context. Keep anchors and original identities
  available where the endpoint supports them. Hidden faces cannot be recovered
  reliably from a tail containing only the back of a head.
- Record the source take, exact source frame indices, FPS and overlap. Extract
  still handoffs by frame index from the actual retained source, not approximate
  decimal seeking or an earlier storyboard.
- Preview the joined clip at normal speed and frame-by-frame around the seam.
  Check speed, foot phase, camera acceleration, lighting, prop position and
  duplicate/omitted frames. A matching still can still produce a velocity jump.
- Preserve latents only within a compatible model/VAE/workflow. Do not claim
  they can be carried between LTX, Wan and a closed API. Native continuation may
  alter earlier frames; keep the approved originals for the final edit.
- With H3, first try to fit the action in one native take (up to about 15 s).
  To continue a take, anchor its last 22 frames as a clip with
  `MiniMaxH3AddGuide` at `frame_idx` 0 and keep the same Subject lines. A guide
  clip is invisible to the text encoder; to name it as `<Video N>` with a
  `[video continuation]` summary, also connect at least 2 s of the source take
  as a reference video. This route is untested here; review the seam
  as above.
- Stop extending when identity, texture or geometry drifts. Repair from a clean
  canonical reference at an intentional scene boundary or change the control.
  Repeatedly sharpening or recolouring the last frame is not a reliable cure.

## Model comparison that measures production value

Separate two questions: how models perform on the same inputs, and how well each
can use our production controls. For the common-input track, use the same staged
opening frame, action and camera requirement. For the controlled track, use each
runtime's supported guides and record the extra inputs. A guided take must not
be presented as an equal-input win over an unguided take. Record unsupported
inputs instead of simulating them with prose.

Use the shortest practical shared native duration for the baseline (for example,
about five seconds); choose a complete action that fits. Do not stretch a model
beyond its recommended native window just to reach eight seconds. Then test a
longer action and continuation on passing modes. Label native generation and
extension separately, keep framing and comparable output resolution stable,
retain native FPS and compare in seconds. A small draft canvas is a feasibility
test; do not generalise its ranking to presentation-quality output. Keep all takes.

Default pilot: at most three candidates, two takes per candidate for the first
test, then advance only those passing the style gate. The next tests cover
two-character interaction and one extension. Choose the exact candidate set
after access/hardware/budget checks; do not spend across the entire catalogue.

Score each category 0–2: **0** fails the action, **1** visible defect needing
repair, **2** acceptable at normal-speed review.

| Category | What passes |
|---|---|
| Cast identity | Both leads survive turning, occlusion and re-entry |
| All-human PS2 style | Foreground, distant NPCs, hands and reflections match |
| Spatial structure | Layout, doors, limbs, furniture and prop count remain stable |
| Motion/contacts | Feet stay grounded; contacts are causal; no penetration or teleport |
| Camera | Planned framing, projection, heading, horizon and movement persist |
| Temporal continuity | No unplanned cuts, stalls, seam jumps or progressive drift |

Proposed acceptance: at least 10/12, with 2/2 for cast, all-human style and
structure; also the **entire required action** must be usable. An 8-second file
with 2 good seconds fails an 8-second take requirement. These are project
thresholds, not a scientific benchmark. Log human judgment and failure timecodes.
If the source uses unreviewed proxy characters, mark canonical cast fidelity
as **not assessed** and do not report a final production-pass score. Appearance
stability relative to a proxy is still useful diagnostic evidence.

Track usable seconds / generated seconds, longest coherent take, attempts per
accepted shot, total wall time and hands-on repair time. Cost per accepted second
= total spend including rejects / retained unique seconds. If nothing passes,
report “no accepted footage,” not a zero cost. Local compute has time/energy
cost even when there is no API bill.

## Failure → next action

| Repeated failure | Change next |
|---|---|
| Face or wardrobe changes | Resolve conflicting references; add view of hidden side; test reference-native model |
| NPCs become photographic | Repair lineup/keyframe, remove realism terms; test shared style conditioning |
| Door, seat or contact changes shape | Correct rigid blockout, masks, depth/pose; direct 3D render if needed |
| Camera floats or flips direction | Fix camera path and world coordinates in a guide |
| Extension becomes blurry or changes colour | Return to original anchor; test multi-frame/latent continuation; reduce chain length |
| Only long takes fail | Reduce simultaneous action complexity or choose a stronger model, then plan motivated coverage |
| Logo/text warps | Track/composite exact artwork; preserve its world-space placement |

LoRAs are an escalation for repeated identity/style drift, not a fix for broken
geometry. Training views should be coherent, varied and licensed; keep character
and style factors separable. Confirm base/checkpoint compatibility and measure
held-out views before adopting. Wan-Animate specifically cautions against LoRAs
trained for standard Wan2.2 ([official guidance](https://github.com/Wan-Video/Wan2.2)).

## Revision and handoff

Interpret user timestamps against the cut they reviewed. Map to source frame
ranges before changes. Regenerate only the affected scene or region. Preserve
accepted timing/audio where appropriate. Keep signs/HUD in editable layers and
dialogue/SFX/music in separate stems; voices require their own continuity record
if added (speaker, accent, delivery and reference).

Verify MP4 decoding, dimensions, duration, frame rate/cadence and audio; then
watch the whole final edit. File validation cannot prove visual continuity.
Supply a GitHub-rendered Markdown page, a light preview and direct MP4 link,
plus selected references and known defects. Do not claim to have watched motion
when only contact sheets were inspected. Publishing to Instagram is separate.
