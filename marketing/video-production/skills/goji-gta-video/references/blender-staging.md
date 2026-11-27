# Blender staging contract

Use this when making or reusing 3D assets and control exports for Goji episodes.
The user prefers low-poly staging. The conventions below are proposed working
defaults; they do not turn the current benchmark proxies into approved cast.
For game-specific motion, use the [San Andreas reference pack](san-andreas-reference.md)
and [behaviour presets](../assets/behaviour-presets.yaml). The presets are original
Goji planning data with uncalibrated artistic starting values, not an installed
Blender rig or imported game physics. Select only those relevant to the shot.

## Build one small production kit

Keep reusable assets separate from shot-specific animation. Give each an ID,
revision, reference authority and review state. Save the `.blend`, any external
textures and the build script where one exists; pack dependencies or verify
relative paths before handoff. A change to a library asset must not silently
change an already selected take: pin the asset revision or save a frozen copy.

| Asset | First useful deliverable | Check before reuse |
|---|---|---|
| GG-01 | Maroon outfit, ponytail, white shoes, separate left-hand bag | Same adult silhouette and face in front, rear and three-quarter views |
| GP-01 | Black outfit, bob, small left-chest mark, plain back | Distinct identity; no logo or hair contradiction in reverse/mirror view |
| NPC roster | Only the driver/commuters required by the scene | Different people with the leads' mesh, texture and shading standard |
| Exterior set | One stretch of road/walkway, entrance and useful reverse angle | Fixed kerb, traffic direction, entrance and occluding objects |
| Interior set | Reception and one treatment area from existing references | Shared floor plan across camera angles; fixed furniture and prop surface |
| Action props | Separate handbag and, when needed, rigid vehicle/door parts | Stable dimensions, contact anchors and correct pivot/handedness |

Use the [series bible](series-bible.md) as identity authority. Do not invent exact
heights, polygon counts or texture budgets and call them inherited facts. Establish
relative scale in one neutral lineup, then record chosen dimensions and detail
budgets. Faces can be simplified while preserving identity. PS2 style requires
painted detail and coherent silhouettes as well as low polygon counts; bare
primitive figures only establish blocking. Keep extra facial refinement consistent
across leads and nearby NPCs. Avoid unrelated per-character face enhancement.

## Keep three visual roles explicit

- **Motion blockout:** proves composition, timing, contacts and camera movement.
  Label proxy faces, generic geography and approximate animation honestly.
- **Look frame:** fixes the intended cast, textures, light and framing. Derive it
  from the same staged view; check that stylisation did not move the door, limbs,
  prop or camera. A pretty frame with contradictory geometry fails this role.
- **Finished render:** either direct Blender output or a generated take. It must
  complete the required action and pass the production review, regardless of route.

For first-frame image-to-video, the look frame is the appearance input. With only
a blockout input, label the result a proxy test. For guided generation, send only
the controls the exact runtime accepts. A `.blend` or depth sequence on disk does
not mean the model received it. Keep the direct 3D animatic beside the generated
take so reviewers can distinguish errors already in the guide from new ones.

## Fix coordinates and the camera

Use metres with Z up as a working scene convention. Give the set a stable origin;
record each asset's forward axis and each shot's action axis. Do not infer world
directions from the screen. Singapore vehicle drivers sit on the car's right;
traffic lane direction, car heading and camera side are separate fields.

For each camera record projection, transform, lens, sensor size, sensor fit,
shift, output size, pixel aspect and any animation. Generate this metadata from
the actual scene when exporting, rather than duplicating hardcoded values.
Save the camera target/subject marks as named scene objects if using them.

The bible's proposed FOVs are **horizontal**. For repeatable square-pixel
perspective presets, explicitly choose horizontal sensor fit and sensor width.
Then `lens_mm = sensor_width_mm / (2 * tan(horizontal_fov / 2))`, with the angle
converted to radians. A 36 mm sensor width at 50° gives approximately 38.6 mm.
This is a proposed calibration, not a description of the benchmark camera.
Blender's Auto fit depends on image resolution; recording only “30 mm” is
insufficient to reproduce a portrait view. See the official
[camera sensor-fit API](https://docs.blender.org/api/5.0/bpy.types.Camera.html)
and [camera manual](https://docs.blender.org/manual/en/3.6/render/cameras.html).

Judge the actual 9:16 frame: readable faces, visible contact points, space for
the full action, and room for later HUD. Presets are starting points, not reasons
to keep empty foreground or tiny actors. Preview the whole movement before
locking a camera. Record intentional deviations; avoid spontaneous lens changes.

## Animate causes and consequences

Break a complex action into observable events: approach, contact, transfer/open,
release, departure and settle. For each, record its time/frame range, participating
objects and required end state. Keep secondary NPC movement simple enough that
the primary action remains readable. Test foreground occlusions deliberately.

For a bag placement, track the hand–handle attachment, then the bag–surface
contact and release. For a door, use its real hinge and rigid motion; check the
door sweep against the person and vehicle. For a vehicle exit, check seat height,
foot clearance, standing room and the character's route. A well-shaped still
does not prove these transitions. Use IK/constraints or keyed animation as useful;
the invariant is plausible contact and no unexplained change of ownership.

Review foot planting, hand reach, penetration and proportion changes through
the action at normal speed and slowly near contact changes. Do not ask the
generator to repair a visibly invalid guide. Use deliberate coverage or direct
3D output if the desired action cannot remain readable in one camera.
Record the selected behaviour preset/version, reference window and any overrides
in the shot packet. Verify foot placement against root travel, and wheel rotation
against travelled distance and radius. Parent the follow camera to a separate
target/rig so suspension movement need not shake or roll the whole view.

## Export a small, traceable shot packet

Copy [shot-template.yaml](../assets/shot-template.yaml) when no existing shot
format captures the same information. Keep the original animation frame numbers
and declare how they map to zero-based video frame indices. A clip containing
frames 1–121 at 24 fps has 121 displayed frames (about 5.04 seconds); its first
and last sample timestamps are 0 and 5 seconds. Distinguish these when aligning
native model durations or choosing an endpoint image.

Export the actual inputs needed for the selected route:

| Route | Minimum useful packet | What it cannot promise |
|---|---|---|
| Direct 3D | Frozen scene/assets, clean frame sequence, preview MP4 | A proxy automatically has final cast quality |
| First-frame I2V | Reviewed opening look frame, action/camera prompt | Exact middle/end poses or a door hinge lock |
| Sparse keyframes | Supported look frames at declared indices and strengths | Hard geometry constraints unless runtime guarantees them |
| Video/depth/pose guide | Matching timed sequence and documented input convention | Every model accepts the same pass or preserves every motion |
| Continuation | Actual retained moving tail, source indices, original identity references | Motion continuity from a lone final still |

All aligned passes use the same camera, crop, resolution, sample times and frame
range. Save clean colour renders without HUD, subtitles or a final grade. Record
engine/version, colour-management settings, lighting and any intentional blur.
Keep a separate display-ready review copy. Freeze the chosen sun/world/material
settings for a location and revise them as a version, not by eye on each shot.

Depth, normals, masks and pose are data, not beauty images. Preserve raw source
passes and record the receiving runtime's expected range, polarity, axes,
normalisation and occlusion convention before conversion. Do not apply a beauty
grade to control data or independently auto-normalise each depth frame. Export
only the useful passes; a full render-pass catalogue is not required for I2V.

Hash exported inputs, list missing/extra frames, and check that the opening
image, guide and declared camera describe the same view. Inspect contact frames
and the actual end pose. Retain rejected renders and reasons in the take log.
The [production protocol](production.md) owns scoring, retries and final handoff.
