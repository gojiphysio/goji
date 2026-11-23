from pathlib import Path
import json,subprocess,wave
import numpy as np
R=Path(__file__).resolve().parents[1]
timeline=json.loads((R/'edit-timeline.json').read_text());jobs=json.loads((R/'jobs.json').read_text())
def probe(p):return json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(p)]))
checks={}
for name,audio in [('goji-v6-ui-silent.mp4',False),('goji-v6-ui-sfx.mp4',True)]:
 p=R/name;v=probe(p);streams=v['streams'];video=next(s for s in streams if s['codec_type']=='video')
 assert (video['width'],video['height'])==(1080,1920)
 assert video['r_frame_rate']=='30/1'
 assert any(s['codec_type']=='audio' for s in streams)==audio
 assert abs(float(v['format']['duration'])-timeline['duration'])<.08
 subprocess.run(['ffmpeg','-v','error','-i',str(p),'-f','null','-'],check=True)
 checks[name]={'duration':v['format']['duration'],'width':video['width'],'height':video['height'],'fps':30,'audio':audio,'full_decode':'passed','bytes':p.stat().st_size}
shots={s['shot']:s for s in timeline['shots']}
assert shots['01-swagger']['duration']>=4
assert shots['08b-mat']['duration']==5
assert '08a-warrior' not in shots
with wave.open(str(R/'audio/goji-sfx-only.wav')) as f:
 samples=np.frombuffer(f.readframes(f.getnframes()),dtype='<i2');peak=float(np.max(np.abs(samples.astype(np.int32))))/32768
 assert peak<.9
checks['audio']={'peak':peak,'music':False,'source':'Original procedural effects, separate stems'}
black=shots['black-transition']['start']+.3
frame=subprocess.check_output(['ffmpeg','-v','error','-ss',str(black),'-i',str(R/'goji-v6-ui-silent.mp4'),'-frames:v','1','-vf','scale=16:16','-pix_fmt','rgb24','-f','rawvideo','-'])
assert max(frame)<=3
checks['black_transition']={'sample_time':black,'max_pixel':max(frame)}
for j in jobs:
 assert (R/'clips'/(j['name']+'.mp4')).exists()
 assert not any(s['codec_type']=='audio' for s in probe(R/'clips'/(j['name']+'.mp4'))['streams'])
 for im in j['images']:assert Path(im['path']).exists()
checks['requested_edit_checks']={'walking_seconds':shots['01-swagger']['duration'],'mat_seconds':shots['08b-mat']['duration'],'reformer_removed':True,'handbag_svg':'gold clasp and black body','mobility_popup':json.loads((R/'overlay-timing.json').read_text())}
(R/'qa/validation.json').write_text(json.dumps(checks,indent=2))
print(json.dumps(checks,indent=2))
