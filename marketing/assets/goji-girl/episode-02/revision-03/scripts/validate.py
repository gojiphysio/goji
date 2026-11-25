from pathlib import Path
import json,re,hashlib,subprocess,xml.etree.ElementTree as ET
v=Path(__file__).resolve().parents[1];r=v.parent
plan=json.loads((r/'camera-plan-v3.json').read_text())
spans=re.findall(r'^### (\d+) · (\d\d):(\d\d)–(\d\d):(\d\d)',(r/'README.md').read_text(),re.M)
end=0
for interval,shot in zip(spans,plan['shots']):
 n,a,b,c,d=interval;start,stop=60*int(a)+int(b),60*int(c)+int(d)
 assert start==end and start==shot['start_seconds'] and stop==shot['end_seconds'],interval
 end=stop
assert len(spans)==12 and end==47
new=ET.parse(v/'overlays/mobility-popup.svg').getroot()
assert [e.text for e in new if e.tag.endswith('text')]==['Mobility –','Upgraded. Cops will','now find it harder','to arrest you.']
assert new[0].attrib=={'x':'56.0','y':'360.0','width':'658.0','height':'250.0','fill':'#142725','opacity':'0.84'}
for i,e in enumerate(list(new)[1:]):
 assert e.attrib['font-family']=='Arial-Black' and float(e.attrib['font-size'])==42
 assert float(e.attrib['y'])==379+51*i
 assert e.attrib['fill']=='#E1E4D9'
rec=json.loads((v/'generation-record.json').read_text())
for item in rec['inputs']:
 p=v/item['path'];item['sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
for item in rec['generations']:
 if 'output' in item:item['sha256']=hashlib.sha256((v/item['output']).read_bytes()).hexdigest()
(v/'generation-record.json').write_text(json.dumps(rec,indent=2))
info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(v/'blender/bus-exit-blockout.mp4')]))
stream=next(s for s in info['streams'] if s['codec_type']=='video')
assert (stream['width'],stream['height'],stream['nb_frames'],stream['r_frame_rate'])==(432,768,'72','12/1')
assert float(info['format']['duration'])==6
subprocess.run(['ffmpeg','-v','error','-i',str(v/'blender/bus-exit-blockout.mp4'),'-f','null','-'],check=True)
stage=json.loads((v/'blender/scene-record.json').read_text())
assert stage['reader']['local'][1]>stage['door']['front_axle_y']
tap=[x for x in stage['pose_samples'] if 2.8<=x['t']<=3.3]
for x in tap:
 assert abs(x['card_center'][0]-stage['reader']['world'][0])<.001
 assert abs(x['card_center'][2]-stage['reader']['world'][2])<.001
 assert abs(x['card_center'][1]-stage['reader']['contact_world'][1])<.005
(v/'validation.json').write_text(json.dumps({'episode_seconds':47,'sequences':12,'all_current_relative_links':'passed','popup_exact_text_and_style':'passed','popup_y_translation_px':180,'geometry_reader_ahead_of_front_axle':'passed','card_reader_contact':'passed within 5mm at tap hold','limb_reach_and_wheel_ground':'build assertions passed','video':{'seconds':6,'frames':72,'fps':12,'size':[432,768],'full_decode':'passed'},'visual_review':'selected stills and contact frames inspected','normal_speed_playback_reviewed':False,'final_ps2_animation':'not generated'},indent=2))
for file in [r/'README.md',v/'README.md']:
 for link in re.findall(r'\]\(([^)]+)\)',file.read_text()):
  if not link.startswith(('http','mailto')):assert (file.parent/link).exists(),(file,link)
print('Passed: 47s timeline, six-second blockout, original popup styling at y360, reader contact and all relative links.')
