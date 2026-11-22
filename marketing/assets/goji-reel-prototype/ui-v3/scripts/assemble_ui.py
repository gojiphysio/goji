from pathlib import Path
import subprocess,json
R=Path(__file__).resolve().parents[1]
BASE=Path('/Users/tidepool/Projects/goji-reel-animation-v2/edit/base.mp4')
def run(args):subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y']+args,check=True)
subprocess.run(['/Users/tidepool/Projects/goji-video-engine/.venv/bin/python',str(R/'scripts/make_sfx.py')],check=True)
filter="[0:v][1:v]overlay=0:0:enable='lt(t,10)'[a];[a][2:v]overlay=0:0:enable='gte(t,10)*lt(t,15.6)'[b];[b][3:v]overlay=0:0:enable='gte(t,24)'[v]"
run(['-i',str(BASE),'-loop','1','-i',str(R/'overlays/gameplay-hud-0852.png'),'-loop','1','-i',str(R/'overlays/gameplay-hud-0853.png'),'-loop','1','-i',str(R/'overlays/body-muscle-popup.png'),'-filter_complex',filter,'-map','[v]','-t','29.5','-an','-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(R/'goji-v3-ui-silent.mp4')])
run(['-i',str(R/'goji-v3-ui-silent.mp4'),'-i',str(R/'audio/goji-sfx-only.wav'),'-map','0:v','-map','1:a','-c:v','copy','-c:a','aac','-b:a','192k','-t','29.5','-movflags','+faststart',str(R/'goji-v3-ui-sfx.mp4')])
run(['-i',str(R/'goji-v3-ui-silent.mp4'),'-vf','fps=8,scale=216:384:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=96[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3','-loop','0',str(R/'preview.gif')])
for name,t in [('gameplay-preview',7),('popup-preview',25.5)]:run(['-ss',str(t),'-i',str(R/'goji-v3-ui-silent.mp4'),'-frames:v','1',str(R/(name+'.jpg'))])
(R/'overlay-timing.json').write_text(json.dumps({'canvas':[1080,1920],'duration':29.5,'layers':[{'file':'gameplay-hud-0852.png','in':0,'out':10},{'file':'gameplay-hud-0853.png','in':10,'out':15.6},{'file':'body-muscle-popup.png','in':24,'out':29.5}],'popup_text':"Body Muscle - Upgraded. You're well-toned. Keep this up and your attacks will inflict more damage."},indent=2))
print('UI cut complete')
