"""Run a control test only from a reviewed, frozen guide manifest.

No automatic fallback to first-frame I2V. Unsupported modes remain unsupported.
"""
import argparse
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
HOST_ROOT=Path('/Users/tidepool')
ENGINE=HOST_ROOT/'Projects/goji-video-engine'
MODELS=HOST_ROOT/'Models'
PROMPT=json.loads((ROOT/'prompts.json').read_text())['comparison']

p=argparse.ArgumentParser()
p.add_argument('model',choices=['ltx'])
p.add_argument('guide',choices=['stills','video'])
p.add_argument('--take',default='01')
p.add_argument('--dry-run',action='store_true')
a=p.parse_args()
manifest=json.loads((ROOT/'guide-manifest.json').read_text())
stills=[Path(x['path']) for x in manifest['stills']]
video=Path(manifest['video_path'])
for item in manifest['stills']:
    assert hashlib.sha256(Path(item['path']).read_bytes()).hexdigest()==item['sha256']
assert hashlib.sha256(video.read_bytes()).hexdigest()==manifest['video_sha256']
dest=ROOT/'results'/f'{a.model}-{a.guide}-{a.take}'
env=dict(os.environ,PYTHONUNBUFFERED='1')
refs=stills if a.guide=='stills' else [video]
prompt=PROMPT
if a.model=='ltx':
    cmd=[str(ENGINE/'.venv/bin/python'),str(HOST_ROOT/'Projects/goji-reel-animation-v6/scripts/ltx25_community_adapter.py'),
         'generate' if a.guide=='stills' else 'ic-lora','--model',str(MODELS/'ltx-2.5-mlx-q8'),
         '--prompt',prompt,'--width','576','--height','1024','--frames','121','--frame-rate','24',
         '--seed','1017','--no-audio','--output',str(dest/'raw.mp4')]
    env['LTX2_COMPUTE_DTYPE']='float16'
    if a.guide=='stills':
        cmd+=['--distilled']
        for item in manifest['stills']:cmd+=['--image',item['path'],str(item['frame_index']),'1']
    else:
        adapter=MODELS/'goji-chase-ltx-layout/ltx-2.5-22b-ic-lora-layout-to-render-1.0.safetensors'
        if not adapter.is_file():raise FileNotFoundError(adapter)
        env['LTX2_LORA_MODE']='unfused'
        cmd+=['--single-stage','--stage1-steps','8','--lora',str(adapter),'1','--video-conditioning',str(video),'1','--image',str(stills[0]),'0','1']
        refs+=[stills[0]]
record={'model':a.model,'guide':a.guide,'prompt':prompt,'command':cmd,
        'guide_manifest_sha256':hashlib.sha256((ROOT/'guide-manifest.json').read_bytes()).hexdigest(),
        'reference_files':[{'path':str(f),'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in refs],
        'control_semantics':'six indexed image anchors' if a.guide=='stills' else 'Layout-to-Render continuous guide plus opening image',
        'env':{k:v for k,v in env.items() if k.startswith('LTX2_')}}
if a.dry_run:print(json.dumps(record,indent=2));raise SystemExit
dest.mkdir(parents=True,exist_ok=False)
record.update(status='running',started=time.time())
(dest/'run.json').write_text(json.dumps(record,indent=2))
with (dest/'inference.log').open('w') as log:r=subprocess.run(cmd,env=env,stdout=log,stderr=subprocess.STDOUT)
record.update(exit_code=r.returncode,wall_seconds=time.time()-record['started'],status='generated_unreviewed' if r.returncode==0 else 'inference_failed')
(dest/'run.json').write_text(json.dumps(record,indent=2))
if r.returncode==0 and (dest/'raw.avi').exists():
    subprocess.run(['ffmpeg','-v','error','-i',str(dest/'raw.avi'),'-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart','-an',str(dest/'raw.mp4')],check=True)
print(json.dumps({'status':record['status'],'wall_seconds':record['wall_seconds']}))
