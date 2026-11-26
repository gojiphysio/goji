"""Reuse tested local H3 Ref2VA route; freeze requests and collect per take."""
import argparse,json,hashlib,time,urllib.request,urllib.error,math,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1];URL='http://127.0.0.1:8196'
p=argparse.ArgumentParser();p.add_argument('shot');p.add_argument('--take',default='01');p.add_argument('--collect',action='store_true');p.add_argument('--job-file',default='shots.json');a=p.parse_args()
D=R/'takes'/f'{a.shot}-{a.take}';D.mkdir(parents=True,exist_ok=True)
def get(path):return json.load(urllib.request.urlopen(URL+path,timeout=60))
if a.collect:
 r=json.loads((D/'run.json').read_text());pid=r['receipt']['prompt_id'];h=get('/history/'+pid)
 if pid not in h:print('running or queued');raise SystemExit
 h=h[pid];(D/'history.json').write_text(json.dumps(h,indent=2));r['status']='generated_unreviewed' if h['status']['status_str']=='success' else 'failed';r['completed_at']=time.time()
 r['outputs']=h.get('outputs',{});(D/'run.json').write_text(json.dumps(r,indent=2));print(json.dumps({'status':r['status'],'outputs':r['outputs']}));raise SystemExit
if (D/'run.json').exists():raise RuntimeError('Take already submitted')
job=json.loads((R/a.job_file).read_text())[a.shot];n=5+17*math.ceil((math.ceil(job['duration']*24)-5)/17)
def node(t,**kw):return {'class_type':t,'inputs':kw}
g={'1':node('UnetLoaderGGUF',unet_name='minimax_h3_ref2va_pruned-Q4_K_M.gguf'),'2':node('CLIPLoaderGGUF',clip_name='qwen3vl_32b_minimax_h3-Q4_K_M.gguf',type='minimax'),'3':node('VAELoader',vae_name='minimax_h3_video_vae_fp16.safetensors'),'4':node('LoraLoaderModelOnly',model=['1',0],lora_name='minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors',strength_model=1.0),'5':node('MiniMaxH3SigmaShift',model=['4',0],shift_video=12.0,shift_audio=3.0),'6':node('MiniMaxH3ReferenceToVideo',clip=['2',0],vae=['3',0],prompt=job['prompt'],width=576,height=1024,length=n,ref_image_size='match'),'7':node('BasicGuider',model=['5',0],conditioning=['6',0]),'8':node('RandomNoise',noise_seed=job.get('seed',2026112600+int(a.shot)+int(a.take)*100)),'9':node('KSamplerSelect',sampler_name='euler'),'10':node('BasicScheduler',model=['5',0],scheduler='simple',steps=4,denoise=1.0),'11':node('SamplerCustomAdvanced',noise=['8',0],guider=['7',0],sampler=['9',0],sigmas=['10',0],latent_image=['6',1]),'12':node('VAEDecodeTiled',samples=['11',0],vae=['3',0],tile_size=256,overlap=64,temporal_size=64,temporal_overlap=8),'13':node('CreateVideo',images=['12',0],fps=24.0),'14':node('SaveVideo',video=['13',0],filename_prefix=f'{a.shot}-{a.take}/raw',format='mp4',**{'format.codec':'h264'}),'20':node('LoadImage',image=job.get('appearance',a.shot+'-appearance.png'))}
g['6']['inputs']['ref_images.ref_image_0']=['20',0];refs=[R/'inputs'/job.get('appearance',f'{a.shot}-appearance.png')]
if job['mode']=='video':
 v=R/'inputs'/job.get('guide_filename',f'{a.shot}-guide.mp4');assert v.exists();refs.append(v)
 g['21']=node('LoadVideo',file=v.name);g['22']=node('GetVideoComponents',video=['21',0]);g['6']['inputs']['ref_videos.ref_video_0']=['22',0]
else:
 g['30']=node('MiniMaxH3AddGuide',positive=['6',0],latent=['6',1],vae=['3',0],image=['20',0],frame_idx=0);g['7']['inputs']['conditioning']=['30',0]
if job.get('end_guide'):
 end=R/'inputs'/job['end_guide'];assert end.exists();refs.append(end)
 g['30']=node('MiniMaxH3AddGuide',positive=['6',0],latent=['6',1],vae=['3',0],image=['20',0],frame_idx=0)
 g['31']=node('LoadImage',image=end.name)
 g['32']=node('MiniMaxH3AddGuide',positive=['30',0],latent=['6',1],vae=['3',0],image=['31',0],frame_idx=n-1)
 g['7']['inputs']['conditioning']=['32',0]
if job.get('anchors'):
 previous=['6',0]
 for i,anchor in enumerate(job['anchors']):
  im=R/'inputs'/anchor['image'];assert im.exists();refs.append(im)
  loader=str(40+i*2);guide=str(41+i*2)
  g[loader]=node('LoadImage',image=im.name)
  g[guide]=node('MiniMaxH3AddGuide',positive=previous,latent=['6',1],vae=['3',0],image=[loader,0],frame_idx=anchor['frame'])
  previous=[guide,0]
 g['7']['inputs']['conditioning']=previous
r={'shot':a.shot,'take':a.take,'status':'submitting','started':time.time(),'recipe':'H3 Ref2VA GGUF Q4 + native Turbo 4-step; 576x1024 24fps','native_frames':n,'edit_seconds':job['duration'],'guidance':job['mode'],'prompt':job['prompt'],'workflow':g,'inputs':[{'path':str(f),'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in refs],'audio':'Separate original procedural SFX in edit; video VAE only','runtime_commit':subprocess.check_output(['git','-C','/Users/tidepool/Projects/goji-comfy-control','rev-parse','HEAD'],text=True).strip()}
(D/'run.json').write_text(json.dumps(r,indent=2))
try:
 payload={'prompt':g}
 if 'queue_number' in job:payload['number']=job['queue_number']
 req=urllib.request.Request(URL+'/prompt',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'});r['receipt']=json.load(urllib.request.urlopen(req,timeout=60));r['status']='queued'
except urllib.error.HTTPError as e:r.update(status='validation_failed',error=e.read().decode())
(D/'run.json').write_text(json.dumps(r,indent=2));print(json.dumps({k:r[k] for k in ['shot','status','receipt','error'] if k in r}))
