"""Freeze a reviewed styled clip into one paired still/video input packet.

This only prepares media. --review-note must name the actual motion/style checks;
the script cannot infer that a generated guide passed from its encode status.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser()
p.add_argument('source',type=Path)
p.add_argument('--review-note',required=True)
a=p.parse_args()
dest=ROOT/'inputs/styled-frames'
source=a.source.resolve()
probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_streams','-of','json',str(source)],text=True))['streams'][0]
if probe['avg_frame_rate']!='24/1' or int(probe['nb_frames'])<121:
    raise ValueError('Need at least 121 source samples at native 24 fps; do not retime a failed guide')
if (int(probe['width']),int(probe['height'])) != (576,1024):
    raise ValueError('Review the native 576x1024 guide; do not silently resize it')
dest.mkdir(exist_ok=False)
subprocess.run(['ffmpeg','-v','error','-i',str(source),'-frames:v','121','-vf','scale=576:1024','-vsync','0',str(dest/'%04d.png')],check=True)
# ffmpeg filenames start at 1. Rename to explicit zero-based source indices.
for f in sorted(dest.glob('*.png')):f.rename(dest/f'{int(f.stem)-1:04d}.png')
stills=ROOT/'inputs/styled-stills'
stills.mkdir(exist_ok=False)
for f in [0,24,48,72,96,120]:shutil.copy2(dest/f'{f:04d}.png',stills/f'{f:04d}.png')
video=ROOT/'inputs/styled-guide.mp4'
subprocess.run(['ffmpeg','-v','error','-framerate','24','-i',str(dest/'%04d.png'),'-frames:v','121','-c:v','libx264rgb','-crf','0','-pix_fmt','rgb24','-movflags','+faststart',str(video)],check=True)
h3_video=ROOT/'inputs/styled-h3-124.mp4'
subprocess.run(['ffmpeg','-v','error','-i',str(video),'-vf','tpad=stop_mode=clone:stop=3','-frames:v','124','-c:v','libx264rgb','-crf','0','-pix_fmt','rgb24',str(h3_video)],check=True)
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
record={'source':str(source),'source_sha256':sha(source),'source_probe':probe,
 'review_note':a.review_note,'size':[576,1024],'fps':24,'frames':121,
 'source_indices':list(range(121)),'stills':[{'frame_index':f,'time_seconds':f/24,'path':str(stills/f'{f:04d}.png'),'sha256':sha(stills/f'{f:04d}.png')} for f in [0,24,48,72,96,120]],
 'video_path':str(video),'video_sha256':sha(video),
 'h3_video_path':str(h3_video),'h3_video_sha256':sha(h3_video),
 'h3_padding':{'repeat_source_frame':120,'extra_frames':3},
 'note':'Lossless RGB video and stills share source pixels. No interpolation or speed change. H3 appends three repeated terminal frames for its 17k+5 frame grid.'}
(ROOT/'guide-manifest.json').write_text(json.dumps(record,indent=2))
print('Frozen',video)
