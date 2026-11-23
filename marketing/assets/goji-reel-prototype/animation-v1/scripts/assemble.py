from pathlib import Path
import json, subprocess

ROOT=Path(__file__).resolve().parents[1]
FRAMES=Path('/Users/tidepool/Projects/goji-reel-prototype-v5')
EDIT=ROOT/'edit'
EDIT.mkdir(exist_ok=True)
jobs=json.loads((ROOT/'jobs.json').read_text())
def run(args):
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y']+args,check=True)
parts=[]
for job in jobs:
    source=ROOT/'clips'/(job['name']+'.mp4')
    if not source.exists():raise FileNotFoundError(source)
    target=EDIT/(job['name']+'.mp4')
    info=json.loads(subprocess.check_output(['ffprobe','-v','quiet','-show_format','-of','json',str(source)]))
    duration=float(info['format']['duration'])
    if job['name']=='06-marker':
        # Trigger loading once she reaches the cone, before a glass-door intersection.
        duration=min(duration,1.75)
    rate=job['edit_duration']/duration
    vf=f"trim=duration={duration},setpts={rate:.9f}*(PTS-STARTPTS),scale=1080:1920:flags=lanczos,setsar=1,fps=30"
    if job['name']=='04-impact':
        # Hold the approach until 6.22s on the timeline, then compress the bounce.
        vf="setpts='if(lt(T,0.333333),2.16*T,0.72+0.1728*(T-0.333333))/TB',scale=1080:1920:flags=lanczos,setsar=1,fps=30"
        vf+=",crop=1068:1900:x='6+4*sin(80*t)*gte(t,0.72)':y='10+7*sin(100*t)*gte(t,0.72)',scale=1080:1920"
    run(['-i',str(source),'-vf',vf,'-t',str(job['edit_duration']),'-an','-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p',str(target)])
    parts.append(target)
    if job['name']=='06-marker':
        fade=EDIT/'06b-fade-black.mp4'
        # Take the actual final marker frame for a .2s fade, followed by .2s black.
        run(['-sseof','-0.05','-i',str(target),'-vf','tpad=stop_mode=clone:stop_duration=0.4,trim=duration=0.4,setpts=PTS-STARTPTS,fade=t=out:st=0:d=0.2,fps=30','-t','0.4','-an','-c:v','libx264','-crf','18','-pix_fmt','yuv420p',str(fade)])
        parts.append(fade)
concat=EDIT/'concat.txt'
concat.write_text(''.join("file '"+str(p)+"'\n" for p in parts))
base=EDIT/'base.mp4'
run(['-f','concat','-safe','0','-i',str(concat),'-c','copy',str(base)])
silent=ROOT/'goji-20s-silent.mp4'
run(['-i',str(base),'-loop','1','-i',str(FRAMES/'overlays/strength-1080x1920.png'),'-loop','1','-i',str(FRAMES/'overlays/strength-mobility-1080x1920.png'),'-filter_complex',"[0:v][1:v]overlay=0:0:enable='gte(t,18.3)*lt(t,19.1)'[v1];[v1][2:v]overlay=0:0:enable='gte(t,19.1)'[v]",'-map','[v]','-t','20','-an','-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(silent)])
run(['-i',str(silent),'-i',str(ROOT/'audio/goji-sfx-only.wav'),'-map','0:v','-map','1:a','-c:v','copy','-c:a','aac','-b:a','192k','-t','20','-movflags','+faststart',str(ROOT/'goji-20s-sfx-no-music.mp4')])
# Lightweight moving preview renders directly inside GitHub's mobile Markdown view.
run(['-i',str(silent),'-vf','fps=8,scale=216:384:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=96[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3','-loop','0',str(ROOT/'preview.gif')])
print('Assembled 20-second silent and SFX-only reels, plus mobile GIF.')
