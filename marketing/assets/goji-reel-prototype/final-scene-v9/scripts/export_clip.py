from pathlib import Path
import subprocess,json
R=Path(__file__).resolve().parents[1];V=R.parent/'goji-reel-animation-v8'
def run(a):subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y']+a,check=True)
run(['-i',str(R/'clips/09-squat.mp4'),'-loop','1','-i',str(V/'overlays/body-muscle-popup.png'),'-ss','24.8','-i',str(V/'audio/goji-sfx-only.wav'),'-filter_complex',"[0:v]setpts=0.993103448*(PTS-STARTPTS),scale=1080:1920:flags=lanczos,setsar=1,fps=30[b];[b][1:v]overlay=0:0:enable='gte(t,0.5)'[v]",'-map','[v]','-map','2:a','-t','6','-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-movflags','+faststart',str(R/'goji-final-squat-plain-black.mp4')])
run(['-i',str(R/'goji-final-squat-plain-black.mp4'),'-vf','fps=8,scale=216:384:flags=lanczos,split[a][b];[a]palettegen=max_colors=96[p];[b][p]paletteuse=dither=bayer:bayer_scale=3','-loop','0',str(R/'preview.gif')])
run(['-i',str(R/'goji-final-squat-plain-black.mp4'),'-vf','fps=2,scale=270:480,tile=6x2','-frames:v','1',str(R/'qa/contact-sheet.jpg')])
p=R/'goji-final-squat-plain-black.mp4';info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(p)]));v=next(s for s in info['streams'] if s['codec_type']=='video')
assert (v['width'],v['height'],v['r_frame_rate'],v['nb_frames'])==(1080,1920,'30/1','180')
assert abs(float(info['format']['duration'])-6)<.05
subprocess.run(['ffmpeg','-v','error','-i',str(p),'-f','null','-'],check=True)
(R/'qa/validation.json').write_text(json.dumps({'duration':6,'frames':180,'width':1080,'height':1920,'fps':30,'full_decode':'passed','scope':'Only final squat clip rendered; original reel unchanged.','popup_start':.5,'sound':'Same original SFX slice as v8 final scene, no music'},indent=2))
print('Single final clip exported and validated')
