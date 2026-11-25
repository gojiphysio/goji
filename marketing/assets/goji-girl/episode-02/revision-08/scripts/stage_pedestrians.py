"""Add fixed, separated crowd marks to the approved route; proxies only."""
import bpy,math,json
from pathlib import Path
from mathutils import Vector
R=Path(__file__).resolve().parents[1];E=R.parent
bpy.ops.wm.open_mainfile(filepath=str(R/'blender/route-09-10.blend'))
s=bpy.context.scene
source=(E/'revision-07/scripts/build_continuity.py').read_text()
exec(source[source.index('M={}'):source.index('# +Y is vehicle forward')])
roster=[('NPC01 blue-shirt man','blue','short',(-8.6,8,.13),'hands raised, recoiling toward storefront'),('NPC02 cream-shirt woman','cream','bob',(-8.7,12,.13),'turning back in alarm, stepping toward storefront'),('NPC03 teal-shirt man','teal','short',(-8.8,28.4,.13),'startled backward step beyond clinic doorway'),('NPC04 white-shirt woman','white','bob',(-6.0,30.5,.13),'turning away along pavement, looking back')]
actors=[]
for name,outfit,hair,pos,reaction in roster:
 p=Person(name,outfit=outfit,hair=hair);p.pose(1,pos,math.pi,walk=.4)
 # Simple raised forearms for a readable startled proxy.
 for side in [-1,1]:
  shoulder=(side*.235,0,1.35);elbow=(side*.40,.06,1.25);wrist=(side*.38,.12,1.62)
  move_segment(p.parts[(side,'upperarm')],shoulder,elbow,1);move_segment(p.parts[(side,'forearm')],elbow,wrist,1)
  p.parts[(side,'hand')].location=wrist;p.parts[(side,'hand')].keyframe_insert('location',frame=1)
 actors.append(p)
s.frame_set(1)
for p in actors:
 for o in [p.root]+list(p.root.children_recursive):o.animation_data_clear()
# Route clearance: 0.55m pedestrian envelope + 0.65m player/bag envelope.
route=[Vector(p) for p in [(-6.3,5.4,0),(-6.35,10,0),(-6.6,16,0),(-7.15,22.1,0),(-9.58,25.3,0)]]
def distance(p,a,b):
 t=max(0,min(1,(p-a).dot(b-a)/(b-a).length_squared));return (p-(a+t*(b-a))).length
checks=[]
for name,_,_,pos,reaction in roster:
 p=Vector((pos[0],pos[1],0));gap=min(distance(p,a,b) for a,b in zip(route,route[1:]))-1.2
 # Conservative impact exclusion extends to x=-6.0, beyond wreck bounds.
 impact_gap=-6.0-(pos[0]+.55) if pos[1]<20 else pos[1]-20-.55
 assert gap>.6 and impact_gap>1.0,(name,gap,impact_gap)
 checks.append({'id':name,'position':pos,'reaction':reaction,'player_route_envelope_clearance_m':gap,'impact_exclusion_clearance_m':impact_gap})
record={'role':'static crowd marks; NOT validated finished movement','crowd':checks,'invariant':'No pedestrian contact with bus, debris, player or pursuing officers. Retreat toward storefront or farther along sidewalk; never cross sprint corridor.','animation_review':'Keep these protected pockets through motion; inspect continuous H3 result. No ragdolls, falls, injured people or bodies in road.'}
(R/'blender/pedestrian-record.json').write_text(json.dumps(record,indent=2)+'\n')
old=json.loads((E/'revision-07/blender/continuity-record.json').read_text());c7=next(x['camera'] for x in old['shots'] if x['id']=='07')
bpy.ops.object.camera_add(location=c7['position']);cam=bpy.context.object;cam.name='CROWD07 camera';cam.rotation_euler=c7['rotation'];cam.data.sensor_fit='HORIZONTAL';cam.data.sensor_width=36;cam.data.lens=c7['lens_mm']
for sid in ['07','09','10']:
 for ob in bpy.data.objects:
  if ob.name.startswith('ROUTE09'):ob.hide_render=sid!='09'
  if ob.name.startswith('ROUTE10'):ob.hide_render=sid!='10'
 s.camera=cam if sid=='07' else bpy.data.objects['ROUTE '+sid+' player camera']
 s.render.resolution_x=540;s.render.resolution_y=960;s.cycles.samples=16
 s.render.filepath=str(R/'frames'/f'{sid}-crowd-direct.png');bpy.ops.render.render(write_still=True)
bpy.ops.wm.save_as_mainfile(filepath=str(R/'blender/route-with-pedestrians.blend'))
print('Crowd marks and route clearances passed',checks)
