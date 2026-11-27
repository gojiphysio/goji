# MiniMax-H3 operating guide

How to drive H3 for this series, written 27 November 2026 from the official
guides, the installed ComfyUI nodes and our own takes, then corrected the same
day from the Episode 2 hard-scene tests. Each rule is tagged:

- **[official]** stated by MiniMax, Comfy-Org or the adapter authors
- **[ours]** measured or verified in Goji's runtime
- **[untested]** documented upstream but not yet run on Tidepool

Recheck the dated items (adapters, node behaviour) on the exact runtime before
reuse. Sources are listed at the end.

## Runtime we use

- ComfyUI 0.46 in `~/Projects/goji-comfy-control`, with leejet's ComfyUI-GGUF and
  the local [loader patch](../../../chase-benchmark/scripts/comfy-gguf-native-h3.patch).
  Text encoder on MPS in BF16, PyTorch SDPA attention, FP32 VAE compute. **[ours]**
- Weights: `leejet/MiniMax-H3-GGUF` Ref2VA pruned Q4_K_M, Qwen3-VL 32B Q4_K_M, and
  the Comfy-Org FP16 video VAE. Hashes and revisions are in
  [`h3-weights.json`](../../../chase-benchmark/h3-weights.json). **[ours]**
- Q4_K_M is the best GGUF quantisation published for H3. Comfy-Org's
  `int8_convrot` and NVFP4 files rely on CUDA kernels, so they are not a Mac
  upgrade path. mlx-gen's 8-bit package runs on Mac but has no Ref2VA. **[official]**
- 4-bit H3 is measurably softer than 8-bit in mlx-gen's measurements. Treat fine
  texture loss as a known cost of this route, not a prompt problem. **[official]**
- Licence: the H3 community licence excludes some territories. Keep generated H3
  footage on the private review page, as the chase benchmark does. **[ours]**

## Choose the route per shot

| Need | Route | Status |
|---|---|---|
| Path, timing, contacts or camera move matter | Ref2VA with the Blender clip as `<Video 1>` | Default. **[ours]** |
| Simple action, fixed or easy camera | Ref2VA with chained `MiniMaxH3AddGuide` stills | Valid for simpler shots. **[ours]** |
| Exact geometry or body pose from Blender | Fun ControlNet Union with a Blender depth pass, plus cast/look references | Loads and runs with the Ref2VA Q4_K_M GGUF on MPS. With three reference images and Turbo 4-step: strength 1.0 ignored the depth layout; 2.0 held the layout but lost the girl's ponytail, the set's look and the bag's shape. Not a replacement for the video reference while cast and set references must hold. **[ours]**, one seed each |
| Continue an accepted take | `MiniMaxH3AddGuide` with the last 22 frames of the take at `frame_idx` 0; also connect ≥2 s of the take as a reference video if the prompt names it, and the next Blender range as a second reference video | The anchored frames reproduce the source and the seam showed no pose, light or camera jump. The anchor also carries forward any defect already in the tail. End the tail before the first defect frame, checked frame by frame. A clean-tail retry joined to its source gave 9.13 s of continuous action; the squat scene still drifted to a different gym ~5.8 s into the continuation. **[ours]**, one source take |
| Longer than 15 s | `MiniMaxH3ContextWindows` (windows on the 17-frame grid) or planned cuts | **[untested]** |

The video-reference route carries the guide's appearance as well as its motion.
That is why the chase needed a 31-minute style conversion before the guided
takes. Fun ControlNet takes structure only (depth, pose, canny, HED, MLSD), but
on Tidepool it either lost to the references or overrode them (above), so it has
not replaced the conversion. The 27 November tests used the raw Blender clip as
`<Video 1>` with cast and set reference images instead: subjects that have a
reference image lost their proxy look; text-only subjects did not (see Labels).
Results: [Episode 2 hard-scene tests](../../../ep02-h3-tests/README.md).

## Canvas, duration and frame grid

- Native canvas: short edge 768, both sides multiples of 32, area no larger
  than 1344×768. For this series, **768×1344** is the native 9:16 size. **[official]**
- Our measured route is 576×1024 with 288×512 guides. Treat it as the draft
  canvas. **[ours]**
- Frames sit on a **17k+5** grid at 24 fps. 124 frames is about 5 s and 362 about
  15 s; the trained range is roughly 124–362. **[official]**
- Author Blender guides at a grid length (124, 192, 362 and so on) instead of 121
  plus padding. A clip that is not on the grid is silently cropped (121 became
  107 in the chase). **[ours]**
- At the draft recipe, 192-frame (8 s) takes held structure whenever the guide
  was valid. The one native 362-frame (15 s) take broke at 4.75 s: a duplicate
  person faded in, then the scene dissolved into a different gym. Treat 8 s as
  the measured draft length and test any longer take before planning around it.
  **[ours]**, one seed at 15 s
- Reference videos are read as 24 fps with no metadata, 2–15 s each, up to three.
  Up to nine reference images. **[official]**
- Crop guides and keyframes to 9:16 before loading. Off-aspect frames are
  stretched or centre-cropped depending on the node. **[official]**

## Sampler and adapter settings

All H3 checkpoints are CFG-distilled: keep CFG 1, with no negative branch. **[official]**

| Use | Recipe | Status |
|---|---|---|
| Draft (current) | Ref2V Turbo 4-step **v0.1** (544p-trained), 4 steps, euler, simple, shifts video 12 / audio 3, `ref_image_size: match`, 576×1024 | 13–17 min per 5 s take with one reference image. 25–31 min per 8 s take with three reference images and a 288×512, 192-frame guide (19 takes); 75 min for a 362-frame take (859 s per step); 45 min for a 192-frame continuation with two reference videos and a 22-frame anchor. **[ours]** |
| Final candidate A | Ref2V Turbo **8-step v1.1 768p**, 8 steps, euler, simple, shifts 12 / 3, 768×1344 | The shift is inferred, not published: lightx2v's Ref2VA example workflow covers only 4-step v0.1 (12 / 3); their 8-step 768p Ref2V v1.0 post gives 12 / 3; their v1.1 post says the new shift 6 is for FL2V, not Ref2V. About 692 s per step, ~100 min per 8 s take. On T02 (two seeds) the action and contacts held and detail was sharper, but both takes rebuilt the set from the reference picture (added furniture, a glass entrance, the logo wall gone), which the 576 draft held on the same seeds. People kept the same smooth look. Not adopted yet. **[ours]** |
| Final candidate B | No adapter, 20–25 steps, shifts 12 / 3, 768×1344 | Comfy's advice when references must hold; Turbo weakens reference and audio adherence. Expect roughly an hour or more per take here. **[untested]** |

- Use `ref_image_size: match` with Turbo adapters, which were trained that way.
  `max` (2048 px short edge) is better for identity on full-step runs but much
  slower. **[official]**
- Style LoRAs compete with references; if one is ever used, run it near 0.5. **[official]**
- Equal seeds are only reproducible in a fixed runtime. Changing the number of
  reference tokens changes the noise. **[ours]**

## Prompt format

H3 expects its own structured prompt. For Ref2VA, write six sections in this
order, in English. A filled Goji example is in
[`h3-ref2va-prompt-template.md`](../assets/h3-ref2va-prompt-template.md). **[official]**

1. `subject_definitions` — one line per reusable item: each cast member,
   vehicle, location, and the source video's motion or camera structure.
2. `summary` — one paragraph opening with a task tag, usually
   `[reference generation]`, or `[keyframe completion]` when a picture is a frame
   anchor, or `[video continuation]` when extending a take.
3. `retention_analysis` — one line per label with a fixed marker:
   `fully_preserved`, `partially_preserved`, `attribute_transfer` or
   `weak_reference`.
4. `detailed_description` — one or two style sentences first, then `[Shot 1]`
   with no timestamp. Usually 350–500 words for a generation task.
5. `overall_soundscape` — 1–4 sentences of ambience and physical sound.
6. `non_diegetic_music` — instrumentation, tempo and dynamics, or `N/A`.

Base modes (T2VA, I2VA, FL2VA) use three fields instead:
`integrated_multimodal_description`, `overall_soundscape`, `non_diegetic_music`.
Keyframe modes open with the alignment line, for example
`For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.`
**[official]**

### Labels and roles

- Input tags follow node order: `ref_image_0` is `<Picture 1>`; images come first,
  then videos, then audio. **[official]**
- `<Subject N>` is the reusable thing (Goji girl, the taxi, the HDB street, the
  PS2 look). A cast image that only defines a character is cited inside its
  Subject line, not used as a standalone `<Picture N>`. **[official]**
- Use a standalone `<Picture N>` only when the image is a frame anchor, keyframe
  or storyboard. **[official]**
- `<Video N>` is for whole-clip structure: camera path, timing, rhythm, or the
  clip being continued. A person or vehicle seen in the video is still a Subject.
  **[official]**
- For a Blender motion guide, mark it `<Video 1> (motion, layout and camera path):
  attribute_transfer` and state plainly that its surfaces are placeholders and
  the look comes from the look Subject. This targets proxy appearance leaking
  into the output. **[official]** guidance. **[ours]**: it worked for every
  subject that also has a reference image (leads, sets, props). Subjects
  described only in text kept their proxy colours and box heads (NPCs, 2 of 2
  takes). Rendering those proxies as neutral grey clay in the guide fixed it
  (2 of 2). Give a text-only subject clay in the guide or its own reference image.
- Pictures connected only to `MiniMaxH3AddGuide` are invisible to the text
  encoder. Also connect them to `ref_images` if the prompt names them. **[official]**
- Multi-panel character sheets are allowed as their own `<Picture N>` when each
  shot names the panel. Never put a sheet in a first-frame slot. **[official]**

### Writing rules

- **No ban lists.** At CFG 1 a phrase such as "no extra cars" adds cars to the
  conditioning. State what exists: "Only these three vehicles appear; the sedan
  and van keep driving straight in their lanes." **[official]**
- Describe the PS2 look concretely in the style sentences and the look Subject:
  angular low-poly meshes, flat painted textures, diffuse shading, early-2000s
  draw distance. Avoid photographic phrases (shallow depth of field, volumetric
  god rays), which pull toward realism. **[official]** for the photographic-term
  risk, **[untested]** for low-poly specifically.
- Text does not override the reference images' rendering. Anchoring the look
  Subject to the street reference instead of all three pictures left the
  interior takes unchanged (same seed, near-identical frames, two seeds). The
  Episode 1 interior references produce smooth modern 3D people; interiors need
  a reviewed PS2 interior look frame before final renders. **[ours]**
- Name a picture by its role inside a Subject line. A prose prompt that called
  `<Picture 1>` "the appearance reference for the whole shot" reproduced its
  composition for the first second, then dissolved into the guide (1 of 2
  takes), and duplicated a wall logo (1 of 2). Six-section prompts did neither
  in 17 takes. **[ours]**
- Camera moves are natural sentences with type, amplitude and speed: "The camera
  follows behind the taxi at constant distance and pans left with small amplitude
  at slow speed." Leave out medium amplitude and normal speed. **[official]**
- A new `[Shot N] At MM:SS.mmm, …` only for a deliberate cut. A continuous take
  stays in `[Shot 1]` and describes the action in order. **[official]**
- Keep the cast and look descriptions word-for-word identical across every shot
  of an episode. **[ours]**, as a continuity habit.
- MiniMax's open `h3-prompt-writing` skill rewrites rough briefs into this format.
  Use it, or follow its reference files directly, rather than inventing a format. **[official]**

## Audio

- H3 always generates joint audio. Leaving the audio VAE unconnected skips audio
  decode; our edits replace audio with original SFX anyway. **[ours]**
- If audio may be used, fill both audio fields. `N/A` in `overall_soundscape`
  only for true silence. Unwanted speech or music usually means a field was left
  vague. **[official]**
- Turbo adapters soften audio as well as motion. **[official]**

## Review checks specific to H3

- H3's "nearly static" warning averages the whole frame. A locked background can
  trigger it during visible action; inspect the action region. **[ours]**
- Indexed guides and a reference video do not guarantee exact timing or path.
  Inspect frames between anchors. **[ours]**
- Known weak points: hands, microtext, distant small figures, gradual face
  softening along chains, colour drift on continuations. Composite exact signs
  and HUD separately. Community reports, so treat them as things to check, not
  facts. **[untested]**
- Generated extras can fade in from a faint trace over several frames. Check a
  contrast-boosted crop of empty floor or foreground before accepting a tail,
  and do not rely on `ffmpeg scdet` alone: it does not flag dissolves. **[ours]**

## Sources (checked 27 November 2026)

- [MiniMax-H3 model card](https://huggingface.co/MiniMaxAI/MiniMax-H3): modes,
  reference limits, Context-IR rewriter.
- [h3-prompt-writing skill](https://github.com/MiniMax-AI/MiniMax-H3/tree/main/skills/h3-prompt-writing):
  `references/ref-en.txt` (Ref2VA, six sections) and `references/base-en.txt`.
- [Local deployment guide](https://platform.minimax.io/docs/guides/local-deploy-h3):
  canvas limits, frame grid, 50-step reference sampler, precision notes.
- Comfy-Org docs: [native workflows](https://docs.comfy.org/tutorials/video/minimax/minimax-h3-native),
  [prompt guide](https://docs.comfy.org/tutorials/video/minimax/minimax-h3-prompt-guide),
  [multiframe guides](https://docs.comfy.org/tutorials/video/minimax/minimax-h3-multiframe),
  [Fun ControlNet Union](https://docs.comfy.org/tutorials/video/minimax/minimax-h3-fun-controlnet).
- [MiniMax-H3 Turbo](https://github.com/ModelTC/Minimax-H3-Turbo) and its
  [weights](https://huggingface.co/lightx2v/Minimax-h3-Turbo): adapter training
  resolutions and shifts.
- [mlx-gen H3 memory and quantisation](https://github.com/lpalbou/mlx-gen/blob/main/docs/minimax-h3-memory.md):
  the only measured 4-bit vs 8-bit comparison found.
- Installed node definitions: `comfy_extras/nodes_minimax_h3.py` and
  `nodes_context_windows.py` in the ComfyUI checkout.
