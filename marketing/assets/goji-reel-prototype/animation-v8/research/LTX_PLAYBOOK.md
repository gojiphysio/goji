# LTX continuity and motion control for the Goji reel

Long sequences need continuity of motion as well as matching images. For this reel, use short, focused actions, preserve approved footage, and carry video context across continuous shots. Use explicit motion guides when the path or body mechanics must be repeatable. A stronger prompt alone does not provide those constraints.

## What the earlier version actually did

The previous impact-to-tumble handoff used an extracted final frame as the next clip's opening image. Driving-to-impact used a separately generated reference. The pull and seat-entry clip used opening and ending stills. This preserved some appearance but supplied no incoming velocity at the still-image handoffs. The visible rear-seat position was also present in the crash reference; the video model was being asked to correct contradictory geometry while animating it.

## Choose the control for the job

| Need | Control | Practical limit |
|---|---|---|
| Character, clothing and framing | Image conditioning | A still does not specify velocity or the path between poses. |
| Continue an existing moving shot | Video continuation with carried frames | The local distilled extension mode is experimental and sees only the recent tail. |
| Aim an object along a path | Motion Control IC-LoRA | Sparse trajectories guide motion; inspect the guide before rendering. |
| Fix camera and object layout through time | Layout to Render IC-LoRA | Requires a matching blockout video and art-directed first frame. |
| Control human posture | Pose/depth reference video through a compatible control adapter | Guide quality and model compatibility matter. |
| Correct only a damaged region | Inpainting with a mask video | More suitable for a local clothing fault than reimagining the entire action. |

LTX's official motion workflow uses sparse trajectories; it recommends starting with a few trajectory points and keeping their paths physically plausible. Its layout workflow uses a viewport animation to guide framing and object movement, paired with a look frame made from the same geometry. These provide spatial control that prose cannot supply. [Motion Control](https://docs.ltx.io/open-source-model/feature-guides/structural-control/motion-control) · [Layout to Render](https://docs.ltx.io/open-source-model/vfx-post-production/layout-to-render) · [Inpainting](https://docs.ltx.io/open-source-model/feature-guides/editing-effects/in-outpainting)

## Continue motion rather than restart it

The installed MLX implementation's `extend --distilled` carries the last **25 decoded-frame equivalents**, about one second at 24 fps, as pinned latent context in both generation stages. New-frame image anchors are soft guides. The model does not see the full earlier story, so identity hidden during that tail can drift. This is stronger continuity input than a lone last image, but does not guarantee successful mechanics. [Implementation](https://github.com/dgrauet/ltx-2-mlx/blob/main/packages/ltx-pipelines-mlx/src/ltx_pipelines_mlx/extend_distilled.py) · [Maturity and limitations](https://github.com/dgrauet/ltx-2-mlx/blob/main/docs/PIPELINE_MATURITY.md)

For this reel: trim the drive before the orientation glitch; extend that clean moving tail; review the seam and the new action before accepting the extension. Preserve approved source footage because an extension's encode/decode can slightly change the old frames. Do not treat a reused seed as a continuity mechanism.

## Use keyframes deliberately

Image guides and latent replacement are different operations. Guides can target arbitrary pixel-frame positions; replacement is restricted to causal latent starts. At the prior runtime defaults, frame zero was replaced while later images were guides, even with strength 1. These were not exact pixel locks. Generated keyframe slots are different again: they add temporal capacity for fast motion, rather than supplying an authored pose. [Official conditioning reference](https://github.com/Lightricks/LTX-2/blob/main/packages/ltx-pipelines/docs/conditioning.md)

Our production rule: use start/end poses only when camera, geometry, contact points and action direction agree. Add a mid-pose to resolve a specific ambiguity, not to force several incompatible actions into one clip. Keep handbags and other secondary props out of the motion prompt unless the action depends on them.

## Keep action and timing manageable

LTX recommends flowing action descriptions, present-tense verbs, clear camera movement and a focused scene. For image-to-video, describe what changes rather than repeating every visible detail. The official first/last-frame workflow is an interpolation tool, not a physics simulator. [Prompting guide](https://docs.ltx.io/open-source-model/usage-guides/prompting-guide) · [Image-to-video guide](https://docs.ltx.io/open-source-model/usage-guides/image-to-video)

For Goji, pull the driver out and cut before seat entry. Continue the clean drive into the approach. Bail out through the door before the pole, then use the approved tumble/recovery where its framing fits. The mat shot has one slow downward-left assisted movement; the squat remains unchanged. These are editorial decisions based on observed failures, not universal LTX duration limits.

The local runtime also supports Prompt Relay to gate separate action descriptions to timeline intervals. It can help schedule beats, but does not constrain geometry. Retake regenerates a time range; it is not a guaranteed semantic repair tool. Distilled generation does not use ordinary CFG, so increasing CFG or merely adding a negative prompt is not a valid fix on that path. [Runtime pipeline guide](https://github.com/dgrauet/ltx-2-mlx/blob/main/docs/PIPELINES.md)

## Review before spending on finishing

Check rough motion at native resolution before upscaling: car orientation, wheel movement, stationary landmarks, hand contact, clothing attachment, doorway passage, and the direction of assisted stretching. Review dense frames around transitions, not just a few attractive keyframes. Keep seeds, prompts, model version and accepted frame ranges. Add HUD, text and SFX after picture selection.
