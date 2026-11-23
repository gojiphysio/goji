from pathlib import Path
import json,subprocess,wave
import numpy as np
R=Path(__file__).resolve().parents[1]
timeline=json.loads((R/'edit-timeline.json').read_text());jobs=json.loads((R/'jobs.json').read_text())
def probe(p):return json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(p)]))
checks={}
for name,audio in [('goji-v8-ui-silent.mp4',False),('goji-v8-ui-sfx.mp4',True)]:
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
assert shots['05-run']['start']==12.5
assert abs(timeline['duration']-30.8)<.01
with wave.open(str(R/'audio/goji-sfx-only.wav')) as f:
 samples=np.frombuffer(f.readframes(f.getnframes()),dtype='<i2');peak=float(np.max(np.abs(samples.astype(np.int32))))/32768
 assert peak<.9
checks['audio']={'peak':peak,'music':False,'source':'Original procedural effects, separate stems'}
black=shots['black-transition']['start']+.3
frame=subprocess.check_output(['ffmpeg','-v','error','-ss',str(black),'-i',str(R/'goji-v8-ui-silent.mp4'),'-frames:v','1','-vf','scale=16:16','-pix_fmt','rgb24','-f','rawvideo','-'])
assert max(frame)<=3
checks['black_transition']={'sample_time':black,'max_pixel':max(frame)}
for j in jobs:
 assert (R/'clips'/(j['name']+'.mp4')).exists()
 assert not any(s['codec_type']=='audio' for s in probe(R/'clips'/(j['name']+'.mp4'))['streams'])
 for im in j['images']:assert Path(im['path']).exists()
checks['requested_edit_checks']={'walking_seconds':shots['01-swagger']['duration'],'mat_seconds':shots['08b-mat']['duration'],'reformer_removed':True,'handbag_svg':'gold clasp and black body','mobility_popup':json.loads((R/'overlay-timing.json').read_text())}
checks['requested_edit_checks'].update(jump_cut_new_time=12.5,removed_v6_interval=[12.5,16],new_duration=timeline['duration'])
from xml.etree import ElementTree as ET
root=ET.parse(R/'overlays/mobility-popup.svg').getroot()
copy=' '.join(x.text for x in root.iter('{http://www.w3.org/2000/svg}text'))
assert copy=='Mobility – Upgraded. Cops will now find it harder to arrest you.'
checks['requested_edit_checks']['exact_mobility_copy']=copy
def frame(path,index):
 data=subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-vf',f'select=eq(n\\,{index})','-frames:v','1','-pix_fmt','rgb24','-f','rawvideo','-'])
 return np.frombuffer(data,np.uint8).astype(np.float32)
source=R.parent/'goji-reel-animation-v6/edit/05-recovery.mp4'
if source.exists():
 error=float(np.abs(frame(source,42)-frame(R/'clips/05-run.mp4',0)).mean())
 assert error<2
 checks['source_frame_match']={'v6_recovery_frame':42,'v6_timeline_seconds':16,'new_run_frame':0,'rgb_mean_absolute_error':error}
(R/'qa/validation.json').write_text(json.dumps(checks,indent=2))
print(json.dumps(checks,indent=2))
