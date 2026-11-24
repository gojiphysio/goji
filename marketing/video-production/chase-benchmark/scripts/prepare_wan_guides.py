"""Prepare 16fps VACE guides from the frozen 24fps source, without interpolation.

Sparse guides contain exactly six distinct source images. Each is held for at
most three native frames so its known-frame mask survives VACE's temporal
compression. This is a +/-62.5ms window, not a hard single-frame timestamp.
"""
import hashlib
import json
import math
import subprocess
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
m = json.loads((ROOT / 'guide-manifest.json').read_text())
out = ROOT / 'inputs/wan-guides'
out.mkdir(exist_ok=False)
anchors = [0, 16, 32, 48, 64, 80]
windows = {f: list(range(max(0, f-1), min(81, f+2))) for f in anchors}
known = {i: f for f, window in windows.items() for i in window}
sampled = [min(120, math.floor(i * 24 / 16 + 0.5)) for i in range(81)]
for kind in ['dense', 'sparse', 'mask']:
    (out / kind).mkdir()
for i in range(81):
    Image.open(ROOT / 'inputs/styled-frames' / f'{sampled[i]:04d}.png').save(out / 'dense' / f'{i:04d}.png')
    if i in known:
        img = Image.open(ROOT / 'inputs/styled-stills' / f'{known[i]*24//16:04d}.png')
    else:
        img = Image.new('RGB', (576, 1024), (128,128,128))
    img.save(out / 'sparse' / f'{i:04d}.png')
    Image.new('RGB', (576, 1024), (0,0,0) if i in known else (255,255,255)).save(out / 'mask' / f'{i:04d}.png')
files = {}
for kind in ['dense', 'sparse', 'mask']:
    target = out / f'{kind}.mp4'
    subprocess.run(['ffmpeg','-v','error','-framerate','16','-i',str(out/kind/'%04d.png'),'-frames:v','81','-c:v','libx264rgb','-crf','0','-pix_fmt','rgb24',str(target)],check=True)
    files[kind] = {'path':str(target.resolve()),'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
# Exact nearest-exact source indices used by the native 81 -> 21 mask reduction.
latent_indices = [math.floor((i + .5)*81/21) for i in range(21)]
effective = {f:[i for i in latent_indices if i in window] for f,window in windows.items()}
assert all(effective.values()), effective
record = {'fps':16,'frames':81,'size':[576,1024], 'dense_source_indices':sampled,
          'sparse_native_anchor_indices':anchors,'known_windows':windows,
          'mask_polarity':'0 known/retain; 1 regenerate',
          'latent_mask_source_indices':latent_indices,'effective_anchor_mask_samples':effective,
          'files':files,'source_guide_manifest_sha256':hashlib.sha256((ROOT/'guide-manifest.json').read_bytes()).hexdigest()}
(ROOT/'wan-guide-manifest.json').write_text(json.dumps(record,indent=2))
print(json.dumps(record,indent=2))
