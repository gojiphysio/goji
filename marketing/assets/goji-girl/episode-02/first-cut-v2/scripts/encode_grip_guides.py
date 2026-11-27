from pathlib import Path
import json,math,subprocess,hashlib,sys
R=Path(__file__).resolve().parents[1];jobs=json.loads((R/'revision-jobs.json').read_text());records=[]
for sid in sys.argv[1:]:
 j=jobs[sid];d=j['duration'];n=5+17*math.ceil((d*24-5)/17);frames=R/'guides'/f'{sid}-grip-motion-v2-frames';assert (frames/f'{d*12+1:04}.png').exists(),sid
 out=R/'inputs'/j['guide_filename'];assert not out.exists(),'Keep frozen guide inputs unchanged: '+str(out)
 subprocess.run(['ffmpeg','-v','error','-framerate','12','-i',str(frames/'%04d.png'),'-vf','fps=24,tpad=stop_mode=clone:stop_duration=1','-frames:v',str(n),'-c:v','libx264','-crf','16','-pix_fmt','yuv420p','-movflags','+faststart',str(out)],check=True)
 records.append({'shot':sid,'path':str(out.relative_to(R)),'fps':24,'frames':n,'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'role':'motion and contact guide; grip-local bag orientation, no billboarding'})
p=R/'guides/grip-guide-manifest.json';old=json.loads(p.read_text()) if p.exists() else [];p.write_text(json.dumps(old+records,indent=2)+'\n');print('Encoded',','.join(sys.argv[1:]))
