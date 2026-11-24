"""Submit an immutable H3 Ref2VA ComfyUI job; poll its history separately."""
import argparse
import hashlib
import json
import shutil
import time
import urllib.request
import urllib.error
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
COMFY=Path('/Users/tidepool/Projects/goji-comfy-control')
URL='http://127.0.0.1:8195'
p=argparse.ArgumentParser()
p.add_argument('mode',choices=['smoke','conversion','stills','video'])
p.add_argument('--take',default='01')
a=p.parse_args()
dest=ROOT/'results'/f'h3-comfy-{a.mode}-{a.take}'
dest.mkdir(parents=True,exist_ok=False)
def node(typ,**inputs):return {'class_type':typ,'inputs':inputs}
smoke=a.mode=='smoke'
w,h,n=(256,448,22) if smoke else (576,1024,124)
if a.mode in ['conversion','smoke']:
    source=json.loads((ROOT/'prompts.json').read_text())
    prompt=source['conversion'] if not smoke else 'The blue taxi from <Picture 1> drives forward on the Singapore street. Original PS2 GTA San Andreas game rendering.'
else:
    manifest=json.loads((ROOT/'guide-manifest.json').read_text())
    prompt=json.loads((ROOT/'prompts.json').read_text())['comparison']
    for item in manifest['stills']:
        assert hashlib.sha256(Path(item['path']).read_bytes()).hexdigest()==item['sha256']
    assert hashlib.sha256(Path(manifest['h3_video_path']).read_bytes()).hexdigest()==manifest['h3_video_sha256']
g={
 '1':node('UnetLoaderGGUF',unet_name='minimax_h3_ref2va_pruned-Q4_K_M.gguf'),
 '2':node('CLIPLoaderGGUF',clip_name='qwen3vl_32b_minimax_h3-Q4_K_M.gguf',type='minimax'),
 '3':node('VAELoader',vae_name='minimax_h3_video_vae_fp16.safetensors'),
 '4':node('LoraLoaderModelOnly',model=['1',0],lora_name='minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors',strength_model=1.0),
 '5':node('MiniMaxH3SigmaShift',model=['4',0],shift_video=12.0,shift_audio=3.0),
 '6':node('MiniMaxH3ReferenceToVideo',clip=['2',0],vae=['3',0],prompt=prompt,width=w,height=h,length=n,ref_image_size='match'),
 '7':node('BasicGuider',model=['5',0],conditioning=['6',0]),
 '8':node('RandomNoise',noise_seed=1017),
 '9':node('KSamplerSelect',sampler_name='euler'),
 '10':node('BasicScheduler',model=['5',0],scheduler='simple',steps=1 if smoke else 4,denoise=1.0),
 '11':node('SamplerCustomAdvanced',noise=['8',0],guider=['7',0],sampler=['9',0],sigmas=['10',0],latent_image=['6',1]),
 '12':node('VAEDecodeTiled',samples=['11',0],vae=['3',0],tile_size=256,overlap=64,temporal_size=64,temporal_overlap=8),
 '13':node('CreateVideo',images=['12',0],fps=24.0),
 '14':node('SaveVideo',video=['13',0],filename_prefix=f'goji/{dest.name}',format='mp4',**{'format.codec':'h264'}),
}
refs=[]
def input_link(path,name):
    path=path.resolve();target=COMFY/'input'/name
    if target.is_symlink() and target.resolve()==path:target.unlink()
    if not target.exists():shutil.copy2(path,target)
    elif hashlib.sha256(target.read_bytes()).digest()!=hashlib.sha256(path.read_bytes()).digest():raise RuntimeError('Input name already contains different pixels')
    refs.append({'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    return name
if a.mode in ['conversion','smoke']:
    name=input_link(ROOT/'inputs/look-start-v1.png','goji-look-start.png')
    g['20']=node('LoadImage',image=name);g['6']['inputs']['ref_images.ref_image_0']=['20',0]
if a.mode in ['conversion','video']:
    path=ROOT/('staging/layout-h3-124.mp4' if a.mode=='conversion' else 'inputs/styled-h3-124.mp4')
    name=input_link(path,f'goji-{a.mode}-124.mp4')
    g['21']=node('LoadVideo',file=name);g['22']=node('GetVideoComponents',video=['21',0])
    g['6']['inputs']['ref_videos.ref_video_0']=['22',0]
    if a.mode=='video':g['6']['inputs']['prompt']+=' Follow <Video 1> continuously, including its timing and camera path.'
if a.mode=='stills':
    for i,item in enumerate(manifest['stills']):
        name=input_link(Path(item['path']),f'goji-still-{i}.png')
        key=str(20+i);g[key]=node('LoadImage',image=name)
        g['6']['inputs'][f'ref_images.ref_image_{i}']=[key,0]
    g['6']['inputs']['prompt']+=' Pictures 1 through 6 are chronological guides at 0, 1, 2, 3, 4 and 5 seconds. Animate continuously through their states.'
record={'status':'submitting','mode':a.mode,'started':time.time(),'references':refs,'workflow':g,
 'runtime':{'comfy_commit':__import__('subprocess').check_output(['git','-C',str(COMFY),'rev-parse','HEAD'],text=True).strip(),'gguf_commit':__import__('subprocess').check_output(['git','-C',str(COMFY/'custom_nodes/ComfyUI-GGUF'),'rev-parse','HEAD'],text=True).strip(),'local_patch_sha256':hashlib.sha256((ROOT/'scripts/comfy-gguf-native-h3.patch').read_bytes()).hexdigest()},
 'notes':'H3 Ref2VA pruned Q4_K_M, Qwen Q4_K_M, FP32 VAE compute, Ref2VA Turbo 4-step v0.1. Ordered still references use prompt timestamps, not hard locks. Video has three repeated final frames to meet 124-frame H3 grid.'}
(dest/'run.json').write_text(json.dumps(record,indent=2))
try:
 req=urllib.request.Request(URL+'/prompt',data=json.dumps({'prompt':g}).encode(),headers={'Content-Type':'application/json'})
 receipt=json.load(urllib.request.urlopen(req));record.update(status='queued',receipt=receipt)
except urllib.error.HTTPError as e:
 record.update(status='validation_failed',error=e.read().decode())
(dest/'run.json').write_text(json.dumps(record,indent=2))
print(json.dumps({k:v for k,v in record.items() if k in ['status','receipt','error']}))
