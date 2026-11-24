"""Submit Wan 2.2 VACE Fun sparse/dense control with identical sampler settings."""
import argparse
import hashlib
import json
import shutil
import subprocess
import time
import urllib.request
import urllib.error
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
COMFY=Path('/Users/tidepool/Projects/goji-comfy-control')
p=argparse.ArgumentParser()
p.add_argument('mode',choices=['stills','video'])
p.add_argument('--take',default='01')
a=p.parse_args()
m=json.loads((ROOT/'wan-guide-manifest.json').read_text())
assert hashlib.sha256((ROOT/'guide-manifest.json').read_bytes()).hexdigest()==m['source_guide_manifest_sha256']
dest=ROOT/'results'/f'wan22-vace-{a.mode}-{a.take}'
dest.mkdir(parents=True,exist_ok=False)
def node(typ,**inputs):return {'class_type':typ,'inputs':inputs}
prompt=json.loads((ROOT/'prompts.json').read_text())['comparison']
g={
 '1':node('UnetLoaderGGUF',unet_name='Wan2.2-VACE-Fun-A14B-high-noise-Q4_K_M.gguf'),
 '2':node('CLIPLoaderGGUF',clip_name='umt5-xxl-encoder-Q4_K_M.gguf',type='wan'),
 '3':node('VAELoader',vae_name='wan_2.1_vae.safetensors'),
 '4':node('CLIPTextEncode',clip=['2',0],text=prompt),
 '5':node('CLIPTextEncode',clip=['2',0],text='photorealistic, glossy modern graphics, text overlays, cuts, duplicate vehicles, collision'),
 '6':node('WanVaceToVideo',positive=['4',0],negative=['5',0],vae=['3',0],width=576,height=1024,length=81,batch_size=1,strength=1.0,control_video=['21',0]),
 '7':node('ModelSamplingSD3',model=['31',0],shift=12.0),
 '8':node('KSamplerAdvanced',model=['7',0],positive=['6',0],negative=['6',1],latent_image=['6',2],noise_seed=1017,steps=4,cfg=1.0,sampler_name='uni_pc',scheduler='simple',add_noise='enable',start_at_step=0,end_at_step=3,return_with_leftover_noise='enable'),
 '9':node('VAEDecodeTiled',samples=['34',0],vae=['3',0],tile_size=256,overlap=64,temporal_size=64,temporal_overlap=8),
 '10':node('CreateVideo',images=['9',0],fps=16.0),
 '11':node('SaveVideo',video=['10',0],filename_prefix=f'goji/{dest.name}',format='mp4',**{'format.codec':'h264'}),
}
# Official VACE Fun four-step example uses Seko T2V V1.1, shift 12,
# CFG 1 and noise boundary .875. The shifted four-step grid is
# [1,.973,.923,.8,0], so three high-noise steps and one low-noise step.
# Adapted to native Comfy nodes; UniPC history restarts at the model switch.
g['30']=node('UnetLoaderGGUF',unet_name='Wan2.2-VACE-Fun-A14B-low-noise-Q4_K_M.gguf')
g['31']=node('LoraLoaderModelOnly',model=['1',0],lora_name='goji-wan22-seko-high.safetensors',strength_model=1.0)
g['32']=node('LoraLoaderModelOnly',model=['30',0],lora_name='goji-wan22-seko-low.safetensors',strength_model=1.0)
g['33']=node('ModelSamplingSD3',model=['32',0],shift=12.0)
g['34']=node('KSamplerAdvanced',model=['33',0],positive=['6',0],negative=['6',1],latent_image=['8',0],noise_seed=1017,steps=4,cfg=1.0,sampler_name='uni_pc',scheduler='simple',add_noise='disable',start_at_step=3,end_at_step=4,return_with_leftover_noise='disable')
refs=[]
for kind,number in [('sparse' if a.mode=='stills' else 'dense',20)]+([('mask',22)] if a.mode=='stills' else []):
    item=m['files'][kind];source=Path(item['path'])
    assert hashlib.sha256(source.read_bytes()).hexdigest()==item['sha256']
    name=f'goji-vace-{kind}.mp4';target=COMFY/'input'/name
    if target.exists():assert hashlib.sha256(target.read_bytes()).hexdigest()==item['sha256']
    else:shutil.copy2(source,target)
    g[str(number)]=node('LoadVideo',file=name)
    g[str(number+1)]=node('GetVideoComponents',video=[str(number),0])
    refs.append(item)
if a.mode=='stills':
    g['24']=node('ImageToMask',image=['23',0],channel='red')
    g['6']['inputs']['control_masks']=['24',0]
record={'status':'submitting','mode':a.mode,'started':time.time(),'references':refs,'workflow':g,
        'guide_manifest_sha256':m['source_guide_manifest_sha256'],
        'runtime_commit':subprocess.check_output(['git','-C',str(COMFY),'rev-parse','HEAD'],text=True).strip(),
        'guide_manifest':m,'notes':'Wan 2.2 VACE Fun A14B Q4_K_M high/low, Seko T2V V1.1 four-step LoRA. Native Comfy adaptation of official VACE Fun example; UniPC state restarts at high/low boundary. Not prior Wan 2.2 I2V. Six stills are held in +/-1 native-frame known windows. Dense uses all 81 control frames, full repaint mask. No image interpolation.'}
(dest/'run.json').write_text(json.dumps(record,indent=2))
try:
    request=urllib.request.Request('http://127.0.0.1:8195/prompt',data=json.dumps({'prompt':g}).encode(),headers={'Content-Type':'application/json'})
    record.update(status='queued',receipt=json.load(urllib.request.urlopen(request)))
except urllib.error.HTTPError as e:record.update(status='validation_failed',error=e.read().decode())
(dest/'run.json').write_text(json.dumps(record,indent=2))
print(json.dumps({k:v for k,v in record.items() if k in ['status','receipt','error']}))
