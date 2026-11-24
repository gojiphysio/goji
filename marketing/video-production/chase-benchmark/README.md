# Episode 1 taxi chase guidance test

Status: shared guide frozen, H3 paired runs in progress, 24 November 2026. No completed
model ranking yet. The user confirmed the comparison is **timed stills versus a
styled Blender video**, with Episode 1 as the appearance authority.

The scene is one continuous rear-follow shot. A blue Comfort taxi passes a silver
sedan on its right, moves left to pass a white van, then returns to the middle
lane. The two NPC vehicles continue straight. Goji Girl is the right-hand driver;
all visible humans must retain the same painted PS2 appearance. The procedural
set is illustrative Singapore geography, not a reconstruction of Lentor.

## Inputs and gates

- `inputs/episode1-drive.png` and `.mp4`: the actual Episode 1 v8 driving assets.
- `scripts/build_chase.py`: reproducible original Blender layout, 576×1024,
  121 frames at 24 fps. Source frame 1 maps to video index 0. Last sample is t=5;
  displayed duration is 5.0417 seconds.
- `staging/stage.json`: exported camera and per-frame vehicle/camera transforms.
- `staging/motion-anchors.jpg`: six motion-layout samples. Proxies are not cast assets.
- `inputs/look-start-v1.png`: new art-directed opening frame, derived using both
  the layout and the Episode 1 image. Not yet user-approved series canon.

The Blender layout has been inspected at six anchor times. It passes the intended
vehicle order, overtakes and rear camera at those samples. The first look frame
retains the three-vehicle composition and restores the visible driver and Episode
1 texture language. The full H3 conversion completed in 1,868 seconds. Fifteen timed samples against
the blockout preserve both overtakes and the camera. Full decode passed; native
playback remains pending after the browser connection failed. This is a
benchmark-input acceptance, not production or canonical-character approval.

The styled conversion is frozen in `guide-manifest.json`; six images at
0, 1, 2, 3, 4 and 5 seconds and the continuous clip share decoded pixels.
The common guide is 288×512, with the 576×1024 master retained separately. **Both representations must share those pixels.**
If conversion fails, retain the failed take and repair the guide before testing
the other models. No model receives the raw blockout as its appearance reference.

## Verified control distinctions

| Family | Still series | Continuous guide | Local setup |
| --- | --- | --- | --- |
| LTX 2.5 | Repeated images with explicit frame indices | Layout-to-Render IC-LoRA | Existing MLX runtime supports indexed images and IC-LoRA; this specific adapter needs a validation run |
| H3 Ref2VA | Six indexed `MiniMaxH3AddGuide` stills; opening still also supplies appearance | Native reference video conditioning | ComfyUI + GGUF + Ref2VA Turbo; full conversion completed; still/video benchmark queued sequentially |
| Installed H3 FL2VA | First image in current MLX runtime | Unsupported | Prior attractive H3 take does not establish guided-video capability |
| Installed Wan 2.2 A14B I2V | First/last or consecutive context, not six scattered anchors | Unsupported | Do not substitute another first-frame take |
| Wan 2.2 VACE Fun A14B | Six known-frame mask windows | Learned video conditioning | High/low Q4_K_M + Seko V1.1 four-step LoRAs; weights staged after H3 to respect disk budget; not prior I2V weights |

Sources checked on 24 November 2026:
[LTX adapter card](https://huggingface.co/Lightricks/LTX-2.5-22b-IC-LoRA-Layout-To-Render),
[H3 official modes](https://huggingface.co/MiniMaxAI/MiniMax-H3),
[H3 sd.cpp reference support](https://github.com/leejet/stable-diffusion.cpp/blob/3b12781/docs/models/minimax_h3.md),
[Wan local modes](https://github.com/lpalbou/mlx-gen/blob/main/docs/wan-video.md),
[Wan sd.cpp control routes](https://github.com/leejet/stable-diffusion.cpp/blob/3b12781/docs/models/wan.md).

The installed ComfyUI has a stronger H3 still route than the initial sd.cpp
plan: the official [multiframe workflow](https://github.com/Comfy-Org/docs/blob/main/tutorials/video/minimax/minimax-h3-multiframe.mdx)
chains Add Guide nodes on Ref2VA at explicit frame indices. The H3 still runner
uses indices 0/24/48/72/96/120, with the first image also sent to its text/vision
encoder. Six ordered reference pictures alone would only offer prompt timing;
that weaker route is not the planned benchmark input. Indexed conditioning is
still subject to output-fidelity review.

## Runtime preparation

H3 Ref2VA was built with Metal in `/Users/tidepool/Projects/goji-h3-sdcpp`, commit
`3b12781`. New weights are `leejet/MiniMax-H3-GGUF` Ref2VA pruned Q4_K_M and
Qwen3VL 32B Q4_K_M, with the original Comfy-Org FP16 video VAE. The smaller
curve-table/pruned variant and quantization differ from the prior MLX FL2VA take;
any output must be labelled accordingly. A one-step, 22-frame, 256×448 diagnostic
successfully encoded an image reference, sampled and decoded. This diagnostic is
not a visual-quality result and is not included in a benchmark panel.

The first full sd.cpp conversion was stopped during slow reference encoding;
it produced no quality result. ComfyUI `da8bd08` with leejet's ComfyUI-GGUF now
completes the same small image-reference diagnostic in 45 seconds. The local
[loader patch](scripts/comfy-gguf-native-h3.patch) recognizes this specific
HF-keyed encoder GGUF and restores its flattened 5D vision convolution shape.
It does not change weights. The first three Comfy attempts retain validation or
loader failures; diagnostic 04 generated successfully. Full conversion uses
the official [Ref2VA Turbo four-step recipe](https://github.com/ModelTC/Minimax-H3-Turbo),
not the FL2VA Turbo adapter.

The first full Comfy conversion was also stopped before completing its first
sampling step: its CPU text encoder and default subquadratic attention caused
long preparation and heavy swap. From diagnostic 05, the encoder runs on MPS
with BF16 compute and attention uses PyTorch SDPA, following the
[documented H3 MPS attention requirement](https://github.com/yshenaw/ComfyUI-SolAttn-MPS#minimax-h3-launch-requirements).
No sparse attention plugin is active. FP32 VAE compute is retained. Diagnostic
05 completed in 68 seconds; full conversion 02 completed in 1,868 seconds. These are setup
measurements, not cross-model quality scores. The optional MPS loader setting
is `GOJI_TEXT_ENCODER_MPS=1`; the checked-in patch applies with
`git apply --ignore-whitespace` to the recorded upstream revision.

H3's native video grid is `17k + 5`: a 121-frame reference would be cropped to
107 by this reference node. Append three copies of frame 120 to reach 124;
compare only the original 0–5 second action. This is endpoint padding, not
speed interpolation. Source FPS remains 24.

The standard `WanVaceToVideo` node matches the official VACE mask reduction:
81 pixel frames become 21 mask samples with nearest-exact interpolation.
Single-frame masks at 0/16/32/48/64/80 do not all survive that reduction. Any
sparse adapter must record the actual known-frame windows and verify the latent
mask; do not call six loaded PNGs six effective timestamp constraints.

LTX Layout-to-Render model access was accepted with the user's explicit approval.
The existing HF token is scoped to H3, and the browser download failed. Permission
to add this single repository to the token is pending. Never save credentials in
this repository or broaden the token to unrelated models.

## Evaluation

Compare each family's still-guided and video-guided takes within that family.
Use the same 288×512 source guide pixels for all models, while requesting
576×1024 outputs. The 576×1024 styled master is retained separately. Lossless RGB
video decoding must match every source PNG, including H3's endpoint padding.
H3 uses indexed guides; Wan uses known-frame windows rather than single-frame locks. Record
checkpoint, quantization, adapters, seed, resolved canvas, native cadence,
steps, input hashes and wall time for every take, including setup failures.
No cross-model ranking can isolate model architecture when these settings differ.

Inspect between guide timestamps: taxi body rigidity, NPC count/lane direction,
relative passing order, ground contact, steering/body-roll consistency, camera
following, driver silhouette and PS2 appearance. Keep generated H3 footage on the
private review Page; this public repository contains scripts and source assets.

Private mobile review: [taxi chase guidance comparison](https://chatgpt.com/space/page_20b6fae76cf88191a398cb70dc0ec479).
The Page contains source media and the private Blender/H3 conversion comparison.
The still/video model panels remain in progress.

## Wan 2.2 VACE preparation

Use the newer Wan 2.2 VACE Fun A14B instead of the initial Wan 2.1 draft. The
[official VACE Fun four-step workflow](https://github.com/aigc-apps/VideoX-Fun/blob/main/comfyui/wan2_2_vace_fun/v1/wan2.2_vace_fun_chunked_loading_workflow_subjects_4steps_lora.json)
explicitly uses Seko T2V V1.1 adapters, CFG 1, shift 12 and boundary 0.875.
The native Comfy adaptation uses three high-noise and one low-noise UniPC steps.
Solver history restarts at the model boundary; this is a recorded runtime
adaptation, not a claim of bit-identical official execution. Both control modes
use the same adaptation. `wan22-weights.json` pins all six file hashes.

This is not an independent architecture benchmark: the H3-styled master can
favor H3 appearance. Compare sparse versus dense guidance within each family;
report cross-family impressions with that limitation.
