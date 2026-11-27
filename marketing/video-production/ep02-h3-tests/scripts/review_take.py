"""Review helpers for a generated take (private footage stays outside the repo).

python3 review_take.py TAKE [--times 0,1.5,3.4] [--slow START END]
- Scene-change scores per frame (ffmpeg scdet); frames scoring above 12 are
  candidate unplanned cuts, listed with timecodes.
- A strip of (guide, take) pairs, unlabelled, in --times order (this ffmpeg has no drawtext) at the given times, written to
  <private>/<take>/review-<n>.jpg.
- --slow writes every frame between START and END seconds as a 6-wide grid,
  for checking contacts and seams.
"""
import json, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIV = Path('/Users/tidepool/Projects/goji-ep02-runtime/takes')
take = sys.argv[1]
args = sys.argv[2:]
rec = json.loads((ROOT / 'takes' / f'{take}.json').read_text())
mp4 = PRIV / take / f'{take}.mp4'
scene = rec['settings']['scene']
variant = rec['settings']['variant']
gkey = 't03/layout-cont' if variant == 'CONT' else f'{scene}/layout'
guide = ROOT / json.loads((ROOT / 'guides.json').read_text())[gkey]['path']

out = subprocess.run(['ffmpeg', '-hide_banner', '-i', str(mp4), '-vf', 'scdet=threshold=8', '-f', 'null', '-'],
                     capture_output=True, text=True).stderr
cuts = [(float(m.group(2)), float(m.group(1))) for m in re.finditer(r'lavfi.scd.score: ([\d.]+), lavfi.scd.time: ([\d.]+)', out)]
print('scene-change candidates (t s, score):', [(round(t, 3), s) for t, s in cuts])

times = [float(x) for x in args[args.index('--times') + 1].split(',')] if '--times' in args else [0, 1, 2, 3, 4, 5, 6, 7, 7.9]
tiles = []
for i, t in enumerate(times):
    f = PRIV / take / f'_t{i}.png'
    fr = round(t * 24)
    for src, tag in [(guide, 'g'), (mp4, 'o')]:
        subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-i', str(src), '-vf',
                        f"select=eq(n\\,{fr}),scale=288:512",
                        '-frames:v', '1', '-fps_mode', 'passthrough', str(f).replace('.png', f'{tag}.png')], check=True)
    tiles += [str(f).replace('.png', 'g.png'), str(f).replace('.png', 'o.png')]
n = len(times)
inputs = sum([['-i', p] for p in tiles], [])
cols = min(n, 5) * 2
rows = -(-n * 2 // cols)
layout = '|'.join(f'{(k % cols) * 288}_{(k // cols) * 512}' for k in range(len(tiles)))
dst = PRIV / take / f'review-{"-".join(str(t) for t in times)}.jpg'
subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', *inputs, '-filter_complex',
                f"{''.join(f'[{k}]' for k in range(len(tiles)))}xstack=inputs={len(tiles)}:layout={layout}:fill=black",
                '-frames:v', '1', str(dst)], check=True)
for p in tiles:
    Path(p).unlink()
print(dst)
if '--slow' in args:
    a, b = (float(x) for x in args[args.index('--slow') + 1:args.index('--slow') + 3])
    dst2 = PRIV / take / f'slow-{a}-{b}.jpg'
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-i', str(mp4), '-vf',
                    f"select=between(n\\,{round(a * 24)}\\,{round(b * 24)}),scale=192:-2,"
                    f"tile=8x{-(-(round(b * 24) - round(a * 24) + 1) // 8)}",
                    '-frames:v', '1', '-fps_mode', 'passthrough', str(dst2)], check=True)
    print(dst2)
