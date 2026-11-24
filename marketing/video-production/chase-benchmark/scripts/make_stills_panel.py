"""Compare the same six source stills across all three native control recipes."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

p = argparse.ArgumentParser()
p.add_argument('ltx', type=Path)
p.add_argument('h3', type=Path)
p.add_argument('wan', type=Path)
p.add_argument('output', type=Path)
a = p.parse_args()
paths = [a.ltx, a.h3, a.wan]
records = [json.loads((f.parent/'run.json').read_text()) for f in paths]
hashes = [r.get('guide_manifest_sha256') for r in records]
assert hashes[0] and len(set(hashes)) == 1
assert not a.output.exists()
probes = []
for file in paths:
    probe = json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_streams','-of','json',str(file)], text=True))['streams'][0]
    assert (probe['width'], probe['height']) == (576, 1024)
    assert float(probe['duration']) >= 5
    probes.append(probe)
a.output.parent.mkdir(parents=True, exist_ok=True)
header = a.output.with_suffix('.labels.png')
im = Image.new('RGB', (864, 80), '#101820')
d = ImageDraw.Draw(im)
font = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf', 17)
d.text((432,18), 'Same six source stills — native control workflows', font=font, fill='white', anchor='mm')
labels = ['LTX 2.5 Q8 · indexed', 'H3 Ref2VA Q4 · indexed', 'Wan 2.2 VACE Q4 · windows']
for i, label in enumerate(labels):
    d.text((144+288*i,55), label, font=font, fill='white', anchor='mm')
im.save(header)
filters = ';'.join(f'[{i}:v]fps=24:round=near,trim=duration=5,setpts=PTS-STARTPTS,scale=288:512:flags=lanczos[v{i}]' for i in range(3))
filters += ';[v0][v1][v2]hstack=inputs=3[row];[3:v][row]vstack=inputs=2[out]'
cmd = ['ffmpeg','-v','error']
for file in paths:
    cmd += ['-i',str(file)]
cmd += ['-loop','1','-framerate','24','-i',str(header),'-filter_complex',filters,'-map','[out]','-t','5','-an','-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(a.output)]
subprocess.run(cmd, check=True)
subprocess.run(['ffmpeg','-v','error','-i',str(a.output),'-f','null','-'], check=True)
a.output.with_suffix('.json').write_text(json.dumps({
    'guide_manifest_sha256':hashes[0], 'labels':labels, 'source_probes':probes,
    'sources':[{'path':str(f.resolve()),'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in paths],
    'conform':'First five seconds at native speed. Wan 16fps repeats frames to the 24fps panel; no interpolation or endpoint hold. Different recipes and quantization; H3-styled master may favor H3.',
    'output_sha256':hashlib.sha256(a.output.read_bytes()).hexdigest(),
}, indent=2))
print(a.output)
