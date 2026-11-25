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
runtime=json.loads((ROOT/'ltx-runtime.json').read_text())
pipeline=ENGINE/'packages/ltx-pipelines-mlx/src/ltx_pipelines_mlx/ic_lora.py'
assert hashlib.sha256(pipeline.read_bytes()).hexdigest()==runtime['python_pipeline_sha256']
stills=[Path(x['path']) for x in manifest['stills']]
video=Path(manifest['video_path'])
for item in manifest['stills']:
    assert hashlib.sha256(Path(item['path']).read_bytes()).hexdigest()==item['sha256']
assert hashlib.sha256(video.read_bytes()).hexdigest()==manifest['video_sha256']
dest=ROOT/'results'/f'{a.model}-{a.guide}-{a.take}'
env=dict(os.environ,PYTHONUNBUFFERED='1')
refs=stills if a.guide=='stills' else [video]
prompt=PROMPT
cmd=[str(ENGINE/'.venv/bin/python'),str(ROOT/'scripts/ltx_single_stage.py'),a.guide,str(dest/'raw.mp4')]
env['LTX2_COMPUTE_DTYPE']='float16'
env['LTX2_LORA_MODE']='unfused'
if a.guide=='video':
    adapter=MODELS/'goji-chase-ltx-layout/ltx-2.5-22b-ic-lora-layout-to-render-1.0.safetensors'
    if not adapter.is_file():raise FileNotFoundError(adapter)
    refs+=[stills[0]]
record={'model':a.model,'guide':a.guide,'prompt':prompt,'command':cmd,
        'runtime':runtime,
        'guide_manifest_sha256':hashlib.sha256((ROOT/'guide-manifest.json').read_bytes()).hexdigest(),
        'reference_files':[{'path':str(f),'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in refs],
        'recipe':{'pipeline':'ICLoraPipeline Python API','single_stage':True,'steps':8,'width':576,'height':1024,'frames':121,'fps':24,'seed':1017,'task_adapter':'Layout-to-Render strength 1' if a.guide=='video' else None},
        'runner_sha256':hashlib.sha256((ROOT/'scripts/ltx_single_stage.py').read_bytes()).hexdigest(),
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
if r.returncode==0:
    raw=dest/'raw.mp4'
    record['output_probe']=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_streams','-of','json',str(raw)],text=True))['streams'][0]
    subprocess.run(['ffmpeg','-v','error','-i',str(raw),'-f','null','-'],check=True)
    record['full_decode_verified']=True
    record['output_sha256']=hashlib.sha256(raw.read_bytes()).hexdigest()
    (dest/'run.json').write_text(json.dumps(record,indent=2))
print(json.dumps({'status':record['status'],'wall_seconds':record['wall_seconds']}))
