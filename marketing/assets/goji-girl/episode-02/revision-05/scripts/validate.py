from pathlib import Path
import json,re,hashlib,xml.etree.ElementTree as ET
R=Path(__file__).resolve().parents[1];E=R.parent
record=json.loads((R/'blender/continuity-record.json').read_text());shots={s['id']:s for s in record['shots']}
assert shots['04']['bus_matrix_world']==shots['05']['bus_matrix_world']
assert shots['07']['bus_matrix_world']==shots['08']['bus_matrix_world']==shots['09']['bus_matrix_world']
for s in shots.values():
 assert s['bus_bounds']['max'][0]<0 and s['bus_bounds']['min'][0]>=-5.22
 assert s['matrix_determinant']>0 and abs(s['forward_world'][1]-1)<.0001
assert record['driver_window']['width_y']==1.10 and record['driver_window']['height_z']==.82
assert record['driver_window']['centre_y']==5.15
root=ET.parse(R/'overlays/safehouse-popup.svg').getroot()
lines=[e.text for e in root if e.tag.endswith('text')]
assert ' '.join(lines)=='You can save your game and lose the police at a safehouse.'
assert root[0].attrib=={'x':'56.0','y':'360.0','width':'658.0','height':'250.0','fill':'#142725','opacity':'0.84'}
for i,e in enumerate(list(root)[1:]):
 assert e.attrib['font-family']=='Arial-Black' and float(e.attrib['font-size'])==42
 assert float(e.attrib['y'])==379+51*i
plan=json.loads((E/'camera-plan-v5.json').read_text());end=0
for s in plan['shots']:
 assert s['start_seconds']==end;end=s['end_seconds']
assert len(plan['shots'])==12 and end==47
spans=re.findall(r'^### (\d+) · (\d\d):(\d\d)–(\d\d):(\d\d)',(E/'README.md').read_text(),re.M)
assert len(spans)==12
for interval,s in zip(spans,plan['shots']):
 _,a,b,c,d=interval;assert 60*int(a)+int(b)==s['start_seconds'];assert 60*int(c)+int(d)==s['end_seconds']
files=[p for p in R.rglob('*') if p.is_file() and p.suffix in ['.blend','.png','.svg','.py','.swift']]
report={'checks':record['checks'],'popup':'continuous prose, inherited styling at y360','duration_seconds':47,'review':'Direct stills, road/livery views and popup inspected; no new continuous animation reviewed','art_status':'proxy geometry staging; PS2 appearance pass and clinic background bus replacement pending','hashes':{str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
(R/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
for p in [E/'README.md',R/'README.md']:
 for link in re.findall(r'\]\(([^)]+)\)',p.read_text()):
  if not link.startswith(('http','mailto')):assert (p.parent/link.split('#')[0]).exists(),(p,link)
print('Passed: shared poses, left lane, forward heading, no mirroring, paragraph/style, 47-second timing and local links.')
