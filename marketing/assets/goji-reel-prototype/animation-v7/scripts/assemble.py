from pathlib import Path
import json,subprocess
R=Path(__file__).resolve().parents[1];E=R/'edit';E.mkdir(exist_ok=True)
def run(args):subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y']+args,check=True)
jobs=json.loads((R/'jobs.json').read_text());parts=[];cursor=0;timeline=[]
for j in jobs:
 source=R/'clips'/(j['name']+'.mp4');target=E/source.name
 info=json.loads(subprocess.check_output(['ffprobe','-v','quiet','-show_format','-of','json',str(source)]));duration=float(info['format']['duration']);start=j.get('source_start',0);duration=min(duration-start,j.get('source_duration',duration))
 if j['name']=='06-marker':duration=min(duration,1.75)
 vf=f'trim=start={start}:duration={duration},setpts={j["edit_duration"]/duration:.9f}*(PTS-STARTPTS),scale=1080:1920:flags=lanczos,setsar=1,fps=30'
 if j.get('edit_crop'):vf=j['edit_crop']+','+vf
 run(['-i',str(source),'-vf',vf,'-t',str(j['edit_duration']),'-an','-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p',str(target)])
 timeline.append(dict(shot=j['name'],start=round(cursor,3),duration=j['edit_duration'],source_start=start,source_duration=duration));cursor+=j['edit_duration'];parts.append(target)
 if j['name']=='06-marker':
  fade=E/'06b-black.mp4';run(['-sseof','-0.05','-i',str(target),'-vf','tpad=stop_mode=clone:stop_duration=0.4,trim=duration=0.4,setpts=PTS-STARTPTS,fade=t=out:st=0:d=0.2,fps=30','-t','0.4','-an','-c:v','libx264','-crf','18','-pix_fmt','yuv420p',str(fade)]);parts.append(fade);timeline.append(dict(shot='black-transition',start=round(cursor,3),duration=.4));cursor+=.4
D=round(cursor,3);data=dict(duration=D,shots=timeline);(R/'edit-timeline.json').write_text(json.dumps(data,indent=2))
cut=next(x['start'] for x in timeline if x['shot']=='black-transition');pop=D-5.5
mat=next(x for x in timeline if x["shot"]=="08b-mat");mob=mat["start"]+.5;mobout=mat["start"]+mat["duration"]
concat=E/'concat.txt';concat.write_text(''.join("file '"+str(p)+"'\n" for p in parts));base=E/'base.mp4';run(['-f','concat','-safe','0','-i',str(concat),'-c','copy',str(base)])
f=f"[0:v][1:v]overlay=0:0:enable='lt(t,10)'[a];[a][2:v]overlay=0:0:enable='gte(t,10)*lt(t,{cut})'[b];[b][3:v]overlay=0:0:enable='gte(t,{pop})'[c];[c][4:v]overlay=0:0:enable='gte(t,{mob})*lt(t,{mobout})'[v]"
silent=R/'goji-v7-ui-silent.mp4'
run(['-i',str(base),'-loop','1','-i',str(R/'overlays/gameplay-hud-0852.png'),'-loop','1','-i',str(R/'overlays/gameplay-hud-0853.png'),'-loop','1','-i',str(R/'overlays/body-muscle-popup.png'),'-loop','1','-i',str(R/'overlays/mobility-popup.png'),'-filter_complex',f,'-map','[v]','-t',str(D),'-an','-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(silent)])
subprocess.run(['/Users/tidepool/Projects/goji-video-engine/.venv/bin/python',str(R/'scripts/make_sfx.py')],check=True)
run(['-i',str(silent),'-i',str(R/'audio/goji-sfx-only.wav'),'-map','0:v','-map','1:a','-c:v','copy','-c:a','aac','-b:a','192k','-t',str(D),'-movflags','+faststart',str(R/'goji-v7-ui-sfx.mp4')])
run(['-i',str(silent),'-vf','fps=8,scale=216:384:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=96[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3','-loop','0',str(R/'preview.gif')])
(R/'overlay-timing.json').write_text(json.dumps(dict(hud_out=cut,popup_in=pop,popup_out=D,mobility_in=mob,mobility_out=mobout),indent=2));print('Assembled',D,'seconds')
