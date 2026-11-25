from pathlib import Path
import json,re,hashlib,math,xml.etree.ElementTree as ET
R=Path(__file__).resolve().parents[1];E=R.parent
route=json.loads((R/'blender/route-record.json').read_text())
old=json.loads((E/'revision-07/blender/continuity-record.json').read_text())
assert route['wreck_matrix']==next(s['bus_matrix_world'] for s in old['shots'] if s['id']=='09')
assert route['wreck_depth_from_camera10']['max']<0
assert route['girl10'][1]>route['girl09'][1]
assert math.dist(route['girl10'],route['clinic_door'])<math.dist(route['girl09'],route['clinic_door'])
assert all(route['checks'].values())
cal=ET.parse(R/'overlays/calendar-reminder.svg').getroot();group=list(cal)[1]
assert group.attrib['font-size']=='33' and len(list(group))==3
assert all('font-size' not in t.attrib for t in group)
swift=(R/'scripts/compose_calendar.swift').read_text()
assert re.findall(r'\("[^"\n]+",(\d+),\d+\)',swift)==['33','33','33']
# Clean source reuse is deterministic proof that native stars were not retained.
for n in ['05','06','08']:
 assert (R/'frames'/f'{n}-look.png').read_bytes()==(E/'revision-07/frames'/f'{n}-look-clean.png').read_bytes()
plan=json.loads((E/'camera-plan-v8.json').read_text());end=0
for sh in plan['shots']:
 assert sh['start_seconds']==end;end=sh['end_seconds'];assert (E/sh['frame_image']).exists()
assert len(plan['shots'])==12 and end==47
assert plan['shots'][1]['calendar_reminder']['font_size_all_lines']==33
assert 'surprise' in plan['shots'][1]['blocking']['end']
assert plan['wanted_level_artwork']=='none; wanted indicator added later in post'
spans=re.findall(r'^### (\d+) · (\d\d):(\d\d)–(\d\d):(\d\d)',(E/'README.md').read_text(),re.M)
assert len(spans)==12
for span,sh in zip(spans,plan['shots']):
 _,a,b,c,d=span;assert 60*int(a)+int(b)==sh['start_seconds'];assert 60*int(c)+int(d)==sh['end_seconds']
crowd=json.loads((R/'blender/pedestrian-record.json').read_text())
assert all(p['player_route_envelope_clearance_m']>.6 and p['impact_exclusion_clearance_m']>1 for p in crowd['crowd'])
for take in json.loads((R/'generation-record.json').read_text())+json.loads((R/'crowd-generation-record.json').read_text()):
 for f,h in take['input_hashes'].items():assert hashlib.sha256(Path(f).read_bytes()).hexdigest()==h
for p in [E/'README.md',R/'README.md']:
 for link in re.findall(r'\]\(([^)]+)\)',p.read_text()):
  if link!='validation.json' and not link.startswith(('http','mailto')):assert (p.parent/link.split('#')[0]).exists(),(p,link)
report={'route':route['checks'],'wanted_stars':'05,06,08 match clean sources byte-for-byte;07 crowd edit visually reviewed; all12 panels visually inspected without wanted stars','calendar_font':'33px all lines in native composition and editable SVG','scene02':'surprise visually reviewed','scene04':'running stride visually reviewed','timing_seconds':47,'motion_status':'staged stills and route checks; no continuous episode video','hashes':{str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in R.rglob('*') if p.is_file() and p.suffix in ['.png','.blend','.svg','.swift','.py']}}
(R/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
print('Passed: frozen wreck, forward route, wreck behind camera10, uniform font, clean sources,47second timing, input hashes and links.')

