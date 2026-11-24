# Local taxi-scene pilot — 24 November 2026

This is a practical Apple Silicon workflow comparison, not a general model
leaderboard. It uses original procedural **blockout proxies**, not approved
replacements for Goji Girl or the physiotherapist. The scene is inspired by
Episode 1's taxi interaction, where door geometry and movement continuity were
expensive to repair.

## Required action

A maroon-clad woman with a ponytail and one black handbag opens the stationary
taxi's near-side front door. A separate grey-clad driver gets out and walks
alongside the taxi. A black-clad physiotherapist remains at the entrance and
an orange-clad pedestrian walks in the background. All humans keep the same
low-poly rendering. The camera, vehicle and location stay fixed.

The Blender guide is 193 frames at 24 fps. Its first five seconds contain the
whole interaction. The later three seconds test continued separation of the
cast. It is an animatic: simple limbs, approximate contact/seat mechanics and
proxy faces are visible limitations. Model output must not be mistaken for a
test of approved face likeness from this input.

## Controlled inputs and intentional differences

- Common input: `staging/frame-0001.png`; the same prompt and seed label 1017.
  Equal seeds across model families do not mean equal initial latent noise.
- First-frame track: LTX 2.5 distilled, Wan 2.2 I2V A14B Lightning,
  Wan 2.2 TI2V 5B, MiniMax H3 Turbo 544p.
- Extra-control track: LTX with six Blender images at source frames
  1, 25, 49, 73, 97 and 121. Later images have strength 0.9. This measures a
  change in conditioning; it is not a fair first-frame-only model ranking.
- Approximately five seconds per initial take. Wan A14B's recommended
  81-frame shot is retained at 16 fps; LTX and Wan 5B use 121 at 24 fps;
  H3 uses its 124-frame default at 24 fps. No speed-up or optical-flow
  interpolation may hide those differences in the comparison.
- Native practical canvases: LTX 576×1024, Wan target 480×832 (actual
  source-aspect canvas recorded by the runtime), H3 544×960. All source
  framing is preserved. This compares usable local recipes, not identical
  pixel budgets or maximum-quality full-precision models.
- LTX distilled: 8+3 denoising steps. Wan A14B: matching high/low I2V
  Lightning adapters, 4 steps, CFG 1/1, flow shift 5. Wan 5B: 25 steps,
  guidance 5, shift 3. H3: mixed q4 conditioner/q6 transformer package,
  544p Turbo adapter, 8 steps. H3's package name does not mean its
  transformer is four-bit.
- No hosted generation or API spend. Local time, storage and energy still
  have costs. Timings include loading/encoding/decoding, not weight download.
  First LTX take overlaps the final CPU-only Blender rendering and is
  therefore not an isolated speed benchmark.

## Reproduce

`scripts/build_scene.py` creates the original scene from primitives in Blender
5.3; no external meshes or textures are required. Run Blender in background
with that script, then run `scripts/run_take.py PROFILE --take ID`. Profiles and
the exact prompt live in the runner. The runner refuses an existing take
directory, records input SHA-256s, full command, time, RSS, output hash and
ffprobe metadata, and keeps every failed take. Runtime logs are retained.
Paths in commands describe this host; adjust them on another machine.

Pinned runtimes: `ltx-pipelines-mlx` 0.18.0, engine commit
`747b30ef10e92a011e85b2aa0f6c4ee86ced5218`; `mlx-gen` 0.40.1,
commit `8e3c5043f472f1ad273e27e9773467d4081daddb`.
MLX versions are 0.32.2 and 0.32.4 respectively. Host: M5 Pro, 64 GB unified
memory. Wan download revisions are copied into the result provenance.

## Interpretation and limits

Score complete actions, not rescued fragments. Inspect person count, attire,
bag ownership, door hinge, seat-to-pavement motion, background NPC style,
camera drift, and the last usable continuous frame. Keep the guide visible
beside outputs so inherited blockout faults are distinguishable from new
model faults. A single seed is a pilot, not a reliable estimate of failure
rate. Do not choose a production winner solely from beauty or file duration.

H3 access and a repository-only read token were explicitly approved for this
Singapore-based test. Its weights and output have territorial license terms;
H3 footage is kept out of the public GitHub review bundle. No credentials are
stored in this repository.

## Sources for the recipes

- [MLX-Gen Wan guidance](https://github.com/lpalbou/mlx-gen/blob/8e3c5043f472f1ad273e27e9773467d4081daddb/docs/wan-video.md)
- [Wan Lightning model and limitations](https://huggingface.co/lightx2v/Wan2.2-Lightning)
- [MLX-Gen H3 guidance](https://github.com/lpalbou/mlx-gen/blob/8e3c5043f472f1ad273e27e9773467d4081daddb/docs/minimax-h3.md)
- [H3 compact package](https://huggingface.co/AbstractFramework/minimax-h3-4bit)
- [H3 license](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/LICENSE)

The broader Reddit-informed continuity research is in the versioned
[production skill](../skills/goji-gta-video/references/research-2026-11-24.md).
