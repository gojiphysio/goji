"""Collect completed local takes without declaring them visually accepted."""
from pathlib import Path
import json,time,urllib.request,subprocess,hashlib,math
R=Path(__file__).resolve().parents[1]
for p in sorted((R/'takes').glob('*/run.json')):
 r=json.loads(p.read_text())
 if r['status'] not in ['queued','submitting']:continue
 pid=r['receipt']['prompt_id']
 with urllib.request.urlopen('http://127.0.0.1:8195/history/'+pid,timeout=30) as f:h=json.load(f)
 if pid not in h:continue
 h=h[pid];(p.parent/'history.json').write_text(json.dumps(h,indent=2));r['status']='generated_unreviewed' if h.get('status',{}).get('status_str')=='success' else 'failed';r['collected_at']=time.time();r['outputs']=h.get('outputs',{});r['videos']=[]
 stamps={event:data.get('timestamp',0)/1000 for event,data in h.get('status',{}).get('messages',[]) if event in ['execution_start','execution_success','execution_error']}
 r['execution_started_at']=stamps.get('execution_start');r['completed_at']=stamps.get('execution_success',stamps.get('execution_error'))
 r['render_wall_seconds']=r['completed_at']-r['execution_started_at'] if r['completed_at'] and r['execution_started_at'] else None
 if r['status']=='generated_unreviewed':
  for entries in h.get('outputs',{}).get('14',{}).values():
   if not isinstance(entries,list):continue
   for e in entries:
    if not isinstance(e,dict) or not e.get('filename','').endswith('.mp4'):continue
    video=R/'takes'/e.get('subfolder','')/e['filename'];assert video.exists(),video
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(video)],text=True));subprocess.run(['ffmpeg','-v','error','-xerror','-err_detect','explode','-i',str(video),'-f','null','-'],check=True)
    r['videos'].append({'path':str(video.relative_to(R)),'sha256':hashlib.sha256(video.read_bytes()).hexdigest(),'probe':probe,'full_decode_verified':True})
    q=p.parent/'review';q.mkdir(exist_ok=True)
    count=max(1,round(float(probe['format']['duration'])*2));cols=min(6,count);rows=math.ceil(count/cols)
    subprocess.run(['ffmpeg','-v','error','-i',str(video),'-vf',f'fps=2,scale=180:320,tile={cols}x{rows}','-frames:v','1',str(q/'contact-sheet.png')],check=True)
  assert r['videos'],'Success without output video'
 p.write_text(json.dumps(r,indent=2)+'\n');print(r['shot'],r['take'],r['status'],flush=True)
state=[]
for p in sorted((R/'takes').glob('*/run.json')):
 r=json.loads(p.read_text());state.append({'shot':r['shot'],'take':r['take'],'status':r['status'],'started':r['started'],'videos':r.get('videos',[])})
(R/'render-status.json').write_text(json.dumps({'updated':time.time(),'takes':state},indent=2)+'\n')
print('Status:',{s:sum(x['status']==s for x in state) for s in sorted({x['status'] for x in state})})
