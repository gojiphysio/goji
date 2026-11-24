# Goji GTA series bible

Prepared 24 November 2026. Existing choices below come from Episode 1 assets;
camera numbers and stricter rendering guidance are proposed production defaults.
This pack contains recovered references, not newly approved turnaround sheets.

## Visual standard

The user's series requirement is **PS2-era GTA San Andreas humans throughout**:
hero, therapist, drivers, passers-by, background NPCs and mirror images share
the same rendering language. Singapore is the setting, not a photoreal backdrop
with a game character pasted on it.

Use angular low-poly silhouettes, simple joint deformation, economical facial
geometry, painted low-resolution texture detail, broad diffuse lighting and
restrained material highlights. Preserve readable adult proportions. Avoid
photographic skin, pores, individual hair strands, glossy modern game materials,
soft toy-like faces or realistic extras. Low-poly is not voxel or pixel art.
Do not request “cinematic photorealism,” “Unreal Engine 5,” or face beautification.

The street reference is the stronger inherited style anchor. The existing
interiors are smoother: use them for identities, clothing and layout, then bring
their people/materials toward the street standard. A warm filter cannot repair
different character topology. A new neutral-light lineup must prove that the
girl, therapist and NPCs belong to one game before becoming the style master.

## Recovered cast

### GG-01 — Goji girl

- Fictional adult player; dark hair in one long ponytail; preserve the selected
  face, skin tone and athletic proportions rather than recasting each shot.
- Maroon sleeveless athletic top and matching fitted leggings; white trainers.
- One structured black handbag with a small gold clasp. Track its state per shot:
  held, put down, on shelf or offscreen. Never duplicate it or silently teleport it.
  The street keyframe shows it in her left hand; earlier prompts conflict on hand
  and prop presence, so the selected shot image and continuity record take precedence.
- Confident swagger outdoors, calm attention indoors. The behaviour is recurring;
  the exact gait can vary with the episode's action.

![Goji girl and inherited Singapore street look](../assets/ep01-street.png)

### GP-01 — Goji physiotherapist

- Fictional adult therapist; short chin-length black bob with visible short nape,
  tucked behind ears; gentle expression. No ponytail or bun.
- Fitted black short-sleeve crew-neck top, black full-length leggings, white shoes.
- Small Goji mark on wearer's left chest only; plain black back, no name badge,
  collar or navy scrubs. Mirrors must respect front/back and handedness.
- Calm, attentive interaction. Any exercise contact needs a plausible guide,
  not text alone. Do not copy a real staff member's identity from outfit references.

![Existing two-character reception reference](../assets/ep01-reception.png)

![Latest corrected plain-back uniform and reflection](../assets/ep01-therapist-back.png)

### NPCs

Create a small reusable roster as the script requires: e.g. NPC-01 commuter,
NPC-02 taxi driver, NPC-03 passer-by. Assign each a silhouette, outfit palette
and reference. They need not share the hero's face; they must share mesh detail,
texture scale, shading and animation style. Distant people remain simple game
NPCs. A scene containing realistic extras fails the style gate even if GG-01 passes.

## Assets to establish before Episode 2 motion

For each recurring lead: front, rear, side and three-quarter full-body views;
neutral face close-up; walking/rest pose. Derive them from the recovered identity,
inspect for cross-view contradictions, then save each view separately. Add a
two-character scale lineup and one three-person hero/therapist/NPC style test.
Keep a single primary face authority; resolve conflicting sheet panels instead
of feeding contradictory faces into the renderer. No such new sheets exist yet.

For each reused place: empty set master, useful reverse angle, simple top-down
layout, entrances, furniture, prop positions, sun/light direction, and camera
marks. Define what is actual-photo-derived and what is fictional staging.
The [Blender staging contract](blender-staging.md) records these as reusable,
versioned assets and separates motion proxies from reviewed appearance references.

## Singapore world and colour

Recurring exterior cues: sheltered walkways and bus stops, HDB surroundings,
tropical roadside trees, concrete kerbs, warm humid haze, SBS-like buses and
blue Comfort-style taxis where needed. Traffic travels on the left; cars have
right-hand driving positions. Distinguish vehicle/world direction from screen
direction. Check signage deliberately; don't invent a claim of surveyed geography.

Lentor Modern and Goji interiors should follow the existing photo-derived
references. Maintain the reception's warm timber, red/cream floor and table
layout. A reverse angle is a different view of the same set, not a newly invented room.

Proposed shared look: muted tropical greens, warm ochre concrete, maroon hero
accents, cyan-leaning sky, moderate contrast and slight atmospheric haze.
Interior light may be warmer while retaining the same material/rendering rules.
Pick a neutral-light reference, match exposure/white balance per shot, then use
one documented final grade. Do not repeatedly colour-match generated tails into
new source images. Retain ungraded originals. Grain is optional and subtle.

## Camera language

Inherited grammar: exterior third-person player/rear chase; interiors staged
cutscenes. Exact numeric presets below are starting proposals, not recovered
camera metadata. Measure and revise against the chosen vertical look frame.

| Preset | Proposed blockout settings | Continuity rule |
|---|---|---|
| PLAYER-A | 9:16, 50° horizontal FOV; 3 m behind, 1.6 m high, aim at upper torso | Fixed follow distance and horizon; no spontaneous orbit or zoom |
| CAR-A | 9:16, 55° horizontal FOV; 6 m behind, 2.2 m high | Hold rear three-quarter side and road heading through action |
| CLINIC-A | 9:16, 40° horizontal FOV; 1.45 m high, static medium two-shot | Record subject marks, eyelines and camera side of action axis |

FOV is horizontal; do not silently reinterpret it as vertical or lens millimetres.
Text prompts approximate these settings. Use a 3D camera/reference motion for
repeatable projection. Record any deliberate change in camera/lens or screen
direction. A cut across the action axis needs an establishing/neutral view or
clear on-screen movement so the viewer can track it.

Keep generation resolution and frame rate stable within a test/scene. Episode 1
generated at 576×1024/24 fps and delivered at 1080×1920/30 fps; that conversion
is history, not a mandatory generation setting. Pick the episode timeline rate
deliberately; check cadence after conforming. Avoid optical-flow smearing of
low-poly hands/limbs. Place HUD and critical action within reviewed IG-safe space.

## Provenance and precedence

Recovered from `gojiphysio/goji` commit
`779152daf04317c762331d19827d62da3e0e2315`, in the still-open Episode 1 PR #256
as inspected on 24 November 2026. The source material is not assumed merged.

- `ep01-street.png`: `marketing/assets/goji-reel-prototype/animation-v6/assets/01-swagger.png`.
- `ep01-reception.png`: `.../animation-v8/assets/07-entry.png`.
- `ep01-therapist-back.png`: `.../final-scene-v9/assets/09-squat-plain-back.png`.
- [Full v8 cut and records](https://github.com/gojiphysio/goji/blob/779152daf04317c762331d19827d62da3e0e2315/marketing/assets/goji-reel-prototype/animation-v8/README.md).
- [v9 final-scene correction](https://github.com/gojiphysio/goji/blob/779152daf04317c762331d19827d62da3e0e2315/marketing/assets/goji-reel-prototype/final-scene-v9/README.md).
- [Prior motion-control lessons](https://github.com/gojiphysio/goji/blob/779152daf04317c762331d19827d62da3e0e2315/marketing/assets/goji-reel-prototype/animation-v6/research/LTX_PLAYBOOK.md).

v9 corrects the therapist's back only in the final clip; it does not create a new
full episode. These three PNGs are byte-for-byte copies, included so the skill
can be installed without depending on another worktree. Hashes are in
[asset-provenance.json](asset-provenance.json).
