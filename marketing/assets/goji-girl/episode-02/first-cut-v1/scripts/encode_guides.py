from pathlib import Path
import json,math,subprocess,hashlib
R=Path(__file__).resolve().parents[1];shots=json.loads((R/'shots.json').read_text());records=[]
for sid,j in shots.items():
 if j['mode']!='video':continue
 n=5+17*math.ceil((j['duration']*24-5)/17);frames=R/'guides'/f'{sid}-frames';expected=j['duration']*12+1
 assert (frames/f'{expected:04}.png').exists(),sid
 out=R/'inputs'/f'{sid}-guide.mp4'
 if not out.exists():subprocess.run(['ffmpeg','-v','error','-framerate','12','-i',str(frames/'%04d.png'),'-vf','fps=24,tpad=stop_mode=clone:stop_duration=1','-frames:v',str(n),'-c:v','libx264','-crf','16','-pix_fmt','yuv420p','-movflags','+faststart',str(out)],check=True)
 records.append({'shot':sid,'fps':24,'source_fps':12,'source_frames':expected,'encoded_frames':n,'padded_seconds':n/24-j['duration'],'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'role':'continuous Blender motion/layout guidance, not final appearance'})
(R/'guides/manifest.json').write_text(json.dumps(records,indent=2)+'\n');print('Encoded and recorded all continuous guides')
