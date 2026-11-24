"""Make a silent, labelled, native-speed private comparison from two raw takes."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

p=argparse.ArgumentParser()
p.add_argument('left',type=Path)
p.add_argument('right',type=Path)
p.add_argument('output',type=Path)
p.add_argument('--title',required=True)
p.add_argument('--left-label',default='Six indexed still guides')
p.add_argument('--right-label',default='Continuous styled video guide')
a=p.parse_args()
if a.output.exists():raise FileExistsError(a.output)
records=[json.loads((path.parent/'run.json').read_text()) for path in [a.left,a.right]]
hashes=[r.get('guide_manifest_sha256') for r in records]
assert hashes[0] and hashes[0]==hashes[1], 'Comparison takes must share the frozen input packet'
probes=[]
for path in [a.left,a.right]:
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_streams','-of','json',str(path)],text=True))['streams'][0]
    assert (int(probe['width']),int(probe['height']))==(576,1024),probe
    assert float(probe['duration'])>=5, 'Do not hold a failed/short take to fake action coverage'
    probes.append(probe)
a.output.parent.mkdir(parents=True,exist_ok=True)
header=a.output.with_suffix('.labels.png')
im=Image.new('RGB',(864,80),'#101820');d=ImageDraw.Draw(im)
font=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf',19)
d.text((432,18),a.title,font=font,fill='white',anchor='mm')
d.text((216,55),a.left_label,font=font,fill='white',anchor='mm')
d.text((648,55),a.right_label,font=font,fill='white',anchor='mm')
im.save(header)
filters='[0:v]fps=24:round=near,trim=duration=5,setpts=PTS-STARTPTS,scale=432:768:flags=lanczos[l];[1:v]fps=24:round=near,trim=duration=5,setpts=PTS-STARTPTS,scale=432:768:flags=lanczos[r];[l][r]hstack=inputs=2[pair];[2:v][pair]vstack=inputs=2[out]'
subprocess.run(['ffmpeg','-v','error','-i',str(a.left),'-i',str(a.right),'-loop','1','-framerate','24','-i',str(header),'-filter_complex',filters,'-map','[out]','-t','5','-an','-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(a.output)],check=True)
subprocess.run(['ffmpeg','-v','error','-i',str(a.output),'-f','null','-'],check=True)
record={'title':a.title,'labels':[a.left_label,a.right_label],'guide_manifest_sha256':hashes[0], 'source_probes':probes,
        'sources':[{'path':str(f.resolve()),'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in [a.left,a.right]],
        'output':str(a.output.resolve()),'output_sha256':hashlib.sha256(a.output.read_bytes()).hexdigest(),
        'conform':'First five seconds at native speed; fps filter repeats/drops frames to 24fps. No optical flow, slowdown or endpoint hold. Individual native files retained.'}
a.output.with_suffix('.json').write_text(json.dumps(record,indent=2))
print(a.output)
