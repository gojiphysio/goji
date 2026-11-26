import argparse,json,subprocess,hashlib,re
from pathlib import Path
R=Path(__file__).resolve().parents[1];p=argparse.ArgumentParser();p.add_argument('--animatic',action='store_true');p.add_argument('--review',action='store_true');p.add_argument('--review-name',default='review-checkpoint-01');a=p.parse_args();shots=json.loads((R/'shots.json').read_text())
assert re.fullmatch(r'review-checkpoint-\d+',a.review_name),'Use a numbered review-checkpoint name'
name='timing-animatic' if a.animatic else (a.review_name if a.review else 'episode-02-first-cut-v2');tmp=R/'deliverables'/('edit-'+name);tmp.mkdir(exist_ok=True)
if a.review and (R/'deliverables'/(name+'.mp4')).exists():raise RuntimeError('Keep published review checkpoints unchanged; choose a new --review-name')
selected={} if a.animatic else json.loads((R/'selected.json').read_text());records=[]
for sid,job in shots.items():
 out=tmp/(sid+'.mp4');duration=job['duration']
 board=a.animatic or (a.review and sid not in selected)
 if board:
  src=R/'inputs'/f'{sid}-appearance.png';args=['-loop','1','-i',str(src)]
 else:
  item=selected[sid];src=R/item['path'];args=['-ss',str(item.get('start',0)),'-i',str(src)]
 extra='' if board else item.get('video_filter','')
 vf=(extra+',' if extra else '')+'scale=576:1024:force_original_aspect_ratio=decrease,pad=576:1024:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=24'
 if board and a.review:
  args+=['-i',str(R/'overlays/review-pending.png')]
  filtering=['-filter_complex',f'[0:v]{vf}[base];[1:v]scale=576:1024[badge];[base][badge]overlay=0:0[v]','-map','[v]']
 else:filtering=['-vf',vf]
 if not out.exists():subprocess.run(['ffmpeg','-v','error',*args,'-t',str(duration),*filtering,'-an','-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p',str(out)],check=True)
 records.append({'shot':sid,'source':str(src.relative_to(R)),'kind':'storyboard hold' if board else 'animated take','start_seconds':sum(x['duration'] for x in records),'duration':duration,'source_start_frame':0 if board else round(item.get('start',0)*24),'source_frames_used':1 if board else round(duration*24),'source_fps':None if board else 24,'video_filter':extra,'sha256':hashlib.sha256(src.read_bytes()).hexdigest()})
listing=tmp/'concat.txt';listing.write_text(''.join("file '"+str((tmp/(sid+'.mp4')).resolve())+"'\n" for sid in shots))
base=tmp/'picture.mp4'
subprocess.run(['ffmpeg','-y','-v','error','-f','concat','-safe','0','-i',str(listing),'-c','copy',str(base)],check=True)
out=R/'deliverables'/(name+'.mp4')
filters="[1:v]scale=576:1024[cal];[2:v]scale=576:1024[safe];[0:v][cal]overlay=0:0:enable='between(t,3,5)'[v1];[v1][safe]overlay=0:0:enable='between(t,43.5,48)'[v]"
subprocess.run(['ffmpeg','-y','-v','error','-i',str(base),'-loop','1','-framerate','24','-t','49','-i',str(R/'overlays/calendar-reminder.png'),'-loop','1','-framerate','24','-t','49','-i',str(R/'overlays/safehouse-popup.png'),'-i',str(R/'audio/sfx-mix.wav'),'-filter_complex_threads','1','-filter_complex',filters,'-map','[v]','-map','3:a','-t','49','-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-movflags','+faststart',str(out)],check=True)
probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(out)],text=True))
subprocess.run(['ffmpeg','-v','error','-xerror','-err_detect','explode','-i',str(out),'-f','null','-'],check=True)
(R/'deliverables'/(name+'-record.json')).write_text(json.dumps({'kind':'static storyboard timing animatic' if a.animatic else ('mixed animated/storyboard review checkpoint' if a.review else 'first animated cut'),'shot_ranges':records,'overlays':{'calendar':[3,5],'safehouse':[43.5,48]},'audio':'SFX only, original procedural synthesis','probe':probe,'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'full_decode_verified':True},indent=2)+'\n')
print(out)
