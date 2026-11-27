from pathlib import Path
import json,re,hashlib,subprocess,xml.etree.ElementTree as ET
v=Path(__file__).resolve().parents[1];r=v.parent
plan=json.loads((r/'camera-plan-v4.json').read_text())
spans=re.findall(r'^### (\d+) · (\d\d):(\d\d)–(\d\d):(\d\d)',(r/'README.md').read_text(),re.M)
end=0
for interval,shot in zip(spans,plan['shots']):
 n,a,b,c,d=interval;start,stop=60*int(a)+int(b),60*int(c)+int(d)
 assert start==end and start==shot['start_seconds'] and stop==shot['end_seconds'],interval
 end=stop
assert len(spans)==12 and end==47
new=ET.parse(v/'overlays/safehouse-popup.svg').getroot()
assert [e.text for e in new if e.tag.endswith('text')]==['Safehouse unlocked.','Save your game.','Lose the heat.','Repeat as necessary.']
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
(v/'validation.json').write_text(json.dumps({'episode_seconds':47,'sequences':12,'popup_copy':'passed','popup_previous_style_and_y360':'passed','concept_visual_review':['05 nose/driver-side reverse angle; bag left forearm','06 diffuse road/body spill; no blue bus emitter','07/08 roof toward mall, wheels toward road; correct reverse-angle landmarks','12 popup legible and clear of faces'],'normal_speed_playback_reviewed':False,'new_motion_rendered':False},indent=2))
for file in [r/'README.md',v/'README.md']:
 for link in re.findall(r'\]\(([^)]+)\)',file.read_text()):
  if not link.startswith(('http','mailto')):assert (file.parent/link.split('#')[0]).exists(),(file,link)
print('Passed: 47-second script, safehouse text/style/placement, asset hashes and current relative links.')
