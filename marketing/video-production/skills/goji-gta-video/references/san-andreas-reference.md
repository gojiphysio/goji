# San Andreas reference pack — original PS2 target

Research pass: 24 November 2026. Use this alongside the Goji identity bible.
It supplies game references and behaviour design; it is not a reconstructed
Rockstar physics engine or an approved Goji animation library.

## Evidence and platform rules

Use three labels: **observed** for a visible event in inspected footage,
**documented** for a source's technical description, and **Goji proposal** for
our implementation choice. Do not promote one into another. This pass inspected
sampled frames at 2–4 samples/second around interactions, plus wider contact
sheets; it did not review continuous normal-speed playback or measure forces,
accelerations, exact animation durations or camera damping.

The target is the original PS2 rendering/animation language. Record hardware,
release, capture processing and any declared mods/cheats. A title saying “PS2
style,” 4K or 60 fps is insufficient provenance. Upscaled PS2 emulation may help
study a pose but cannot establish original pixel detail or timing. Mobile,
PS3/360 remasters and Definitive Edition are separate visual sources. Rockstar
explicitly describes changed lighting, textures, draw distances and controls for
[Definitive Edition](https://www.rockstargames.com/GTATrilogy).

## Footage to open

### A — original-hardware free roam

[![Open Paulo Cassiano's PS2 capture](https://i.ytimg.com/vi/Z9cD9uj1fb8/hqdefault.jpg)](https://www.youtube.com/watch?v=Z9cD9uj1fb8&t=240s)

[Paulo Cassiano — GTA San Andreas (PS2), Free Roam](https://www.youtube.com/watch?v=Z9cD9uj1fb8).
The creator reports PS2 release 1.03, a real console and DualShock 2. The sampled
opening includes the PS2 boot screen. This supports provenance; disc integrity,
cheats and capture colour processing remain unverified. Use the named car and
scene as an example, not a universal rule for all vehicles.

| Source window | Observed in sampled frames | Useful Goji reference |
|---|---|---|
| [04:00–04:14](https://www.youtube.com/watch?v=Z9cD9uj1fb8&t=240s) | CJ alternates between idle, directional movement and running | Separate locomotion and turn/stop states |
| [04:14–04:24](https://www.youtube.com/watch?v=Z9cD9uj1fb8&t=254s) | Approach, open door, remove occupant, enter; Washington label appears | Distinct two-person carjacking stages |
| [04:44–05:00](https://www.youtube.com/watch?v=Z9cD9uj1fb8&t=284s) | Travel, broad heading change and sideways presentation; camera bearing changes | Separate travel, body yaw and camera orientation |
| [06:04–06:16](https://www.youtube.com/watch?v=Z9cD9uj1fb8&t=364s) | Roadside impact, rollover, overturned car, then CJ on foot | Contact-driven rigid-body stunt and recovery |

Windows include context and are approximate navigation ranges, not animation
frame boundaries. Input buttons are not visible: do not claim which manoeuvre
was commanded or whether a camera rotation was automatic. The overturned exit
is partly obscured and is not a clean normal-exit reference.

### B — labelled PS2 driving-school manoeuvres

[![Open Zodiac's driving-school capture](https://i.ytimg.com/vi/3YtFVP1QhOk/hqdefault.jpg)](https://www.youtube.com/watch?v=3YtFVP1QhOk&t=147s)

[Zodiac — GTA San Andreas (PS2): Driving School [4K]](https://www.youtube.com/watch?v=3YtFVP1QhOk).
The title identifies PS2; hardware/emulator, modifications and upscale process
are unspecified. Treat it as a supporting action reference, not the colour or
resolution authority. Creator chapters identify these exercises:

| Source window | Review status and use |
|---|---|
| [01:10–01:30 — The 360](https://www.youtube.com/watch?v=3YtFVP1QhOk&t=70s) | Broad samples inspected; burnout exercise reference, not a measured suspension test |
| [02:27–02:49 — The 180](https://www.youtube.com/watch?v=3YtFVP1QhOk&t=147s) | Dense samples inspected around 02:30–02:40: approach, sideways yaw, departure and stop |
| [03:35–03:49 — Whip and Terminate](https://www.youtube.com/watch?v=3YtFVP1QhOk&t=215s) | Broad samples only; candidate for closer turn-and-stop review |

### C — platform comparison, for checking source identity

[![Open Digital Foundry's labelled platform comparison](https://i.ytimg.com/vi/UgUiICN8E7I/hqdefault.jpg)](https://www.youtube.com/watch?v=UgUiICN8E7I&t=20s)

[Digital Foundry — PS3 vs Xbox 360 vs Original PS2](https://www.youtube.com/watch?v=UgUiICN8E7I)
is a first-hand platform comparison. Samples every five seconds in 00:00–00:40
were inspected. Use the panel labelled **PS2**, not the adjacent remasters.
[00:20–00:29](https://www.youtube.com/watch?v=UgUiICN8E7I&t=20s) gives cutscene
body/clothing references; [00:30–00:40](https://www.youtube.com/watch?v=UgUiICN8E7I&t=30s)
shows street atmosphere. The sampled PS2 panel is visibly warmer than the other
versions in these scenes. This demonstrates why platform matters; it does not
establish a single colour transform for all weather, times or captures. No
frame-pacing measurement was made from this sparse review.

## What to carry into appearance

**Observed in A:** angular vehicle silhouettes, broad surface shading, coarse
character/clothing detail, cyan sky, earth tones and a readable rear gameplay
view. Capture softness is not proof of a particular texture resolution. These
samples do not establish close-up face topology or a universal orange grade.
Source C adds labelled cutscene comparisons for bodies and clothing; its
three-way crop limits how much fine facial detail can be judged.

**Goji proposal:** keep authored low-poly faces/hair and painted clothing folds;
match detail across leads and NPCs. Use compact car silhouettes, simple wheel
meshes, readable panel seams and restrained highlights. Avoid bare cube people,
voxel bodies, modern PBR clearcoat and photographic extras. Preserve Goji's
canonical identities; CJ is a movement reference, not the replacement cast.
Use location/time-specific lighting under one render standard. Frame the scene
for vertical delivery instead of stretching the original gameplay image.

## Behaviour library to implement in Blender

These are **Goji proposals informed by the references**, not extracted game
animations. The editable [behaviour presets](../assets/behaviour-presets.yaml)
contain starting values and state contracts. They are planning data, not a script
that installs a rig. All numeric choices remain uncalibrated until previewed.

| Preset | Animate | Reject |
|---|---|---|
| GG-WALK | Repeatable walk, deliberate turn/start/stop states; left hand follows bag constraint | Foot skating, bag swapping hands, random torso/face changes |
| NPC-AMBIENT | Simple walk or idle; one readable look/step reaction when relevant | Every extra reacting in sync or performing continuous elaborate gestures |
| GP-GREETING | Hold, small head/torso turn, one arm gesture, return to idle | Constant gesticulation or a new personality each shot |
| SEDAN-CRUISE-STOP | Wheel travel, body response to acceleration/braking, brief settling | Constant bobbing on flat road or wheels spinning while parked |
| SEDAN-SLIDE | Distinct grip-loss, yaw/slip, recovery and straightening phases | Rotating in place during a travelling turn; rubber chassis |
| VEHICLE-ENTRY | Align → reach/open → transfer body into seat → release/close → seated | Door morph, hand reaching through glass, pelvis teleport |
| VEHICLE-TAKEOVER | Separate instigator/occupant tracks; open → removal → cleared doorway → entry | Occupant becomes instigator or both occupy the same seat |
| CAMERA-FOLLOW | Separate camera rig following position/heading with controlled lag | Car body roll automatically tilting the whole camera; arbitrary orbit |

The MTA project's [animation-group catalogue](https://wiki.multitheftauto.com/wiki/Animation_Groups)
documents distinct locomotion/idle/turn states and left/right vehicle alignment,
opening, entry and exit clips, including different vehicle groups. It is a PC
modding reference, not proof of identical PS2 timing. Use it to structure original
Blender actions; no game animation files have been copied or retargeted here.

For neutral walk, ordinary exit and NPC reactions, closer PS2 motion capture
review is still needed. The existing clip contains running and a carjacking;
neither is a measured GG walking cycle or a normal driver-exit demonstration.
Do not label all proposed behaviours “PS2 verified.”

## Vehicle behaviour: useful controls, not guessed game constants

[Project Cerbera's original handling experiments](https://projectcerbera.com/gta/sa/tutorials/handling)
distinguish mass/centre of mass, traction, acceleration, braking, steering,
suspension and vehicle-specific flags. They also describe AI-specific handling
flags and separate vehicle animation groups. The author marks several meanings
as untested; preserve that uncertainty. The MTA project's
[original-handling API](https://wiki.multitheftauto.com/wiki/GetOriginalHandling)
provides a way to inspect stock vehicle parameters in its PC environment. Neither
source establishes a direct Blender-unit conversion or a measured PS2 taxi preset.

**Goji rig design:** separate path/root motion, sprung chassis, wheels and door
pivots. Compute rolling wheel angle from travelled distance and measured radius;
steer the front wheels separately. Let chassis pitch respond to acceleration,
roll to cornering, and heave to road/contact events with a decaying response.
Keep these channels separate from rigid-body airborne tumbling. Use each car's
wheelbase, radius, seat and door anchors rather than scaling one exit blindly.

Cruising, braking, skidding and impact are different states. For a slide, allow
car heading to differ from path tangent, then regain alignment. Keep road contact
and collision timing explicit. Smoke, tyre marks, sparks, dents or loose panels
follow the relevant event; they are not always-on decoration. Background traffic
can use restrained, simpler paths. Do not assume all AI cars share the hero car's
response or transfer PC handling values directly into Blender physics fields.

If exact handling is needed, collect a same-vehicle, same-surface, known-input
PS2 reference and fit the animation to it. This pack provides no claimed PS2
mass, friction coefficient, speed, spring constant or damping time.

## Singapore adaptation and acceptance

Keep left-side traffic and right-hand driving positions. Retarget the action to
the actual right-side door/seat anchors; don't horizontally flip the whole frame,
which would reverse signage, handbag hand and GP's chest mark. A voluntary taxi
handover and a GTA carjacking are different actions: choose explicitly. The
reference's weapons, violence and stunt intensity do not define every Goji scene.

Before accepting a preset, compare reference and preview in seconds: normal
speed, slow contact review, and start/middle/end frames. Record vehicle class,
surface, state, source window and intentional deviations. Check the rigid car,
contacts, wheel motion, silhouette, actor separation, all-human style and camera.
Add deliberate exaggeration only where it serves the chosen scene. The
[production scorecard](production.md#model-comparison-that-measures-production-value)
remains the final take gate. Keep reference-observation confidence separate from
how good an original Goji animation looks.

The [source record](san-andreas-sources.json) preserves URLs, creator metadata,
inspection windows and limitations. Gameplay excerpts used for analysis remain
outside the skill; the pack links to their sources instead of redistributing clips.
