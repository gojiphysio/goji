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
HOME=Path('/Users/tidepool')
ENGINE=HOME/'Projects/goji-video-engine'
CPP=HOME/'Projects/goji-h3-sdcpp/build/bin/sd-cli'
MODELS=HOME/'Models'
PROMPT='''One continuous five-second rear chase camera shot of a blue Comfort taxi overtaking a silver sedan on its right, then a white van on its left, before returning to the middle lane. Preserve the guide's timing, vehicle count, road layout and following camera. The two NPC vehicles travel straight and fall behind. Original 2004 GTA San Andreas PS2 Singapore gameplay: angular vehicles and humans, painted textures, tropical foliage, grey HDB blocks, warm road, pale cyan sky. The right-hand taxi driver keeps her maroon sleeveless top and black ponytail. Taxi body stays rigid, wheels grounded; no additional vehicles, no collisions, no cut, no camera orbit, no photorealistic humans or HUD.'''

p=argparse.ArgumentParser()
p.add_argument('model',choices=['ltx','h3','wan-vace14'])
p.add_argument('guide',choices=['stills','video'])
p.add_argument('--take',default='01')
p.add_argument('--dry-run',action='store_true')
a=p.parse_args()
if a.model=='wan-vace14' and a.guide=='stills':
    p.error('No validated six-timestamp Wan VACE adapter is installed. Do not substitute first/last or consecutive frames.')
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
    cmd=[str(ENGINE/'.venv/bin/python'),str(HOME/'Projects/goji-reel-animation-v6/scripts/ltx25_community_adapter.py'),
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
elif a.model=='h3':
    model=MODELS/'goji-chase-h3-ref'
    if a.guide=='stills':
        prompt+=' The six pictures are chronological samples: <Picture 1> at 0 seconds, <Picture 2> at 1 second, <Picture 3> at 2 seconds, <Picture 4> at 3 seconds, <Picture 5> at 4 seconds and <Picture 6> at 5 seconds. Animate continuously through these states.'
    else:prompt+=' Follow the continuous motion and appearance in <Video 1>.'
    cmd=[str(CPP),'-M','vid_gen','--diffusion-model',str(model/'minimax_h3_ref2va_pruned-Q4_K_M.gguf'),
         '--llm',str(model/'qwen3vl_32b_minimax_h3-Q4_K_M.gguf'),'--vae',str(model/'vae/minimax_h3_video_vae_fp16.safetensors'),
         '--prompt',prompt,'--width','576','--height','1024','--video-frames','124','--steps','20',
         '--cfg-scale','1','--sampling-method','euler','--rng','cpu','--seed','1017',
         '--backend','te=cpu','--offload-to-cpu','--mmap','--max-vram','40',
         '--flash-attn','off,diffusion=on','--vae-tiling','--output',str(dest/'raw.avi')]
    if a.guide=='stills':
        for f in stills:cmd+=['--ref-image',str(f)]
    else:cmd+=['--ref-video',str(ROOT/'inputs/styled-frames')]
else:
    model=MODELS/'goji-chase-wan-vace14'
    cmd=[str(CPP),'-M','vid_gen','--diffusion-model',str(model/'Wan2.1_14B_VACE-Q4_K_M.gguf'),
         '--t5xxl',str(model/'umt5-xxl-encoder-Q4_K_M.gguf'),'--vae',str(model/'wan_2.1_vae.safetensors'),
         '--prompt',prompt,'--width','576','--height','1024','--video-frames','81','--fps','16',
         '--steps','20','--cfg-scale','6','--sampling-method','euler','--rng','cpu','--seed','1017',
         '--backend','te=cpu','--offload-to-cpu','--mmap','--max-vram','40',
         '--flash-attn','off,diffusion=on','--vae-tiling','--init-img',str(stills[0]),
         '--control-video',str(ROOT/'inputs/styled-wan-16fps.avi'),'--output',str(dest/'raw.avi')]
    refs+=[stills[0]]
record={'model':a.model,'guide':a.guide,'prompt':prompt,'command':cmd,
        'guide_manifest_sha256':hashlib.sha256((ROOT/'guide-manifest.json').read_bytes()).hexdigest(),
        'reference_files':[{'path':str(f),'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in refs],
        'control_semantics':'ordered image refs, timing by prompt only' if (a.model,a.guide)==('h3','stills') else 'see exact command',
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
