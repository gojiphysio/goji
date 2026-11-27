"""Use one full-resolution, eight-step LTX pipeline for both control modes.

The library supports empty task-LoRA/video lists for indexed-image generation;
the CLI requires --lora, so call the documented Python pipeline directly.
"""
import argparse
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser()
p.add_argument('mode', choices=['stills', 'video'])
p.add_argument('output')
a = p.parse_args()
adapter = Path('/Users/tidepool/Projects/goji-reel-animation-v6/scripts/ltx25_community_adapter.py')
spec = importlib.util.spec_from_file_location('goji_ltx_adapter', adapter)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.apply_patches()

from ltx_pipelines_mlx.ic_lora import ICLoraPipeline

m = json.loads((ROOT / 'guide-manifest.json').read_text())
images = [(i['path'], i['frame_index'], 1.0) for i in m['stills']]
loras, videos = [], []
if a.mode == 'video':
    loras = [('/Users/tidepool/Models/goji-chase-ltx-layout/ltx-2.5-22b-ic-lora-layout-to-render-1.0.safetensors', 1.0)]
    videos = [(m['video_path'], 1.0)]
    images = images[:1]
pipe = ICLoraPipeline('/Users/tidepool/Models/ltx-2.5-mlx-q8', lora_paths=loras, low_memory=True)
pipe.verbose = True
pipe.generate_and_save(
    prompt=json.loads((ROOT / 'prompts.json').read_text())['comparison'],
    output_path=a.output, video_conditioning=videos, images=images,
    height=1024, width=576, num_frames=121, frame_rate=24.0, seed=1017,
    stage1_steps=8, single_stage=True,
)
