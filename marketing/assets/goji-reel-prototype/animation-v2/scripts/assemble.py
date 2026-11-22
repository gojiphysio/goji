from pathlib import Path
import json, subprocess
ROOT=Path(__file__).resolve().parents[1]
FRAMES=Path('/Users/tidepool/Projects/goji-reel-prototype-v5')
EDIT=ROOT/'edit';EDIT.mkdir(exist_ok=True)
jobs=json.loads((ROOT/'jobs.json').read_text())
def run(args):subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y']+args,check=True)
parts=[];timeline=[];cursor=0
for job in jobs:
 source=ROOT/'clips'/(job['name']+'.mp4');target=EDIT/source.name
 info=json.loads(subprocess.check_output(['ffprobe','-v','quiet','-show_format','-of','json',str(source)]))
 duration=float(info['format']['duration']);start=job.get('source_start',0)
 duration=min(duration-start,job.get('source_duration',duration))
 if job['name']=='06-marker':duration=min(duration,1.75)
 rate=job['edit_duration']/duration
 vf=f'trim=start={start}:duration={duration},setpts={rate:.9f}*(PTS-STARTPTS),scale=1080:1920:flags=lanczos,setsar=1,fps=30'
 if job['name']=='04-impact':vf+=",crop=1068:1900:x='6+4*sin(80*t)*gte(t,0.4)':y='10+7*sin(100*t)*gte(t,0.4)',scale=1080:1920"
 run(['-i',str(source),'-vf',vf,'-t',str(job['edit_duration']),'-an','-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p',str(target)])
 parts.append(target);timeline.append(dict(shot=job['name'],start=round(cursor,3),duration=job['edit_duration'],source_duration=duration,speed=round(1/rate,3)))
 cursor+=job['edit_duration']
 if job['name']=='06-marker':
  fade=EDIT/'06b-fade-black.mp4'
  run(['-sseof','-0.05','-i',str(target),'-vf','tpad=stop_mode=clone:stop_duration=0.4,trim=duration=0.4,setpts=PTS-STARTPTS,fade=t=out:st=0:d=0.2,fps=30','-t','0.4','-an','-c:v','libx264','-crf','18','-pix_fmt','yuv420p',str(fade)])
  parts.append(fade);timeline.append(dict(shot='black-transition',start=round(cursor,3),duration=.4));cursor+=.4
D=round(cursor,3);(ROOT/'edit-timeline.json').write_text(json.dumps(dict(duration=D,shots=timeline),indent=2))
concat=EDIT/'concat.txt';concat.write_text(''.join("file '"+str(p)+"'\n" for p in parts))
base=EDIT/'base.mp4';run(['-f','concat','-safe','0','-i',str(concat),'-c','copy',str(base)])
silent=ROOT/'goji-v2-silent.mp4';a=D-2.0;b=D-1.0
run(['-i',str(base),'-loop','1','-i',str(FRAMES/'overlays/strength-1080x1920.png'),'-loop','1','-i',str(FRAMES/'overlays/strength-mobility-1080x1920.png'),'-filter_complex',f"[0:v][1:v]overlay=0:0:enable='gte(t,{a})*lt(t,{b})'[v1];[v1][2:v]overlay=0:0:enable='gte(t,{b})'[v]",'-map','[v]','-t',str(D),'-an','-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(silent)])
subprocess.run(['/Users/tidepool/Projects/goji-video-engine/.venv/bin/python',str(ROOT/'scripts/make_sfx.py')],check=True)
run(['-i',str(silent),'-i',str(ROOT/'audio/goji-sfx-only.wav'),'-map','0:v','-map','1:a','-c:v','copy','-c:a','aac','-b:a','192k','-t',str(D),'-movflags','+faststart',str(ROOT/'goji-v2-sfx-no-music.mp4')])
run(['-i',str(silent),'-vf','fps=8,scale=216:384:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=96[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3','-loop','0',str(ROOT/'preview.gif')])
print('Assembled',D,'seconds')
