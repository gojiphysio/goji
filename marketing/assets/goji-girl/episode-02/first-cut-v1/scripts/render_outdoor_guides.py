"""Continuous original blocking guides, using the frozen bus/street and crowd."""
import bpy,math,json,sys
from pathlib import Path
from mathutils import Vector,Matrix
R=Path(__file__).resolve().parents[1];E=R.parent
sid=sys.argv[-1];variant='-sa-v3' if sid in ['03','10'] else ('-v2' if sid in ['04','05'] else '');dur={'03':3,'04':3,'05':4,'06':5,'07':5,'09':2,'10':4}[sid];N=dur*12+1
exec((R/'scripts/sa_gait.py').read_text())
bpy.ops.wm.open_mainfile(filepath=str(E/'revision-08/blender/route-with-pedestrians.blend'))
s=bpy.context.scene;s.timeline_markers.clear();s.frame_set(1)
source=(E/'revision-07/scripts/build_continuity.py').read_text();exec(source[source.index('M={}'):source.index('# +Y is vehicle forward')])
for ob in bpy.data.objects:
 ob.animation_data_clear()
 if ob.name.startswith(('GG','DRIVER','EXIT','EZLink','ROUTE09','ROUTE10','offscreen')):ob.hide_render=True
 if ob.name.startswith('NPC'):ob.hide_render=sid not in ['07','09','10']
bus=bpy.data.objects['BUS-SOS-01 chassis transform'];bus.location=(-3.65,-28,0);bus.rotation_euler=(0,0,0)
def reveal(p):
 for o in [p.root]+list(p.root.children_recursive):o.hide_render=False
hero=None;driver=None;cops=[]
if sid in ['03','04','05','09','10']:hero=Person('CUT'+sid+' GG01');reveal(hero)
if sid=='03':
 for surface in ['west sidewalk','two-way asphalt']:
  ob=bpy.data.objects[surface];ob.location.y=-5;ob.scale.y=130
 for ty in [-44,-34]:
  segment('home tree trunk',(-8.9,ty,.12),(-8.9,ty,5.8),.22,.14,'trunk')
  ico('home tree crown',(-8.9,ty,6),(2.1,2.2,1.8),'leaf',sub=2)
 for ob in [bus]+list(bus.children_recursive):ob.hide_render=True
 for ob in bpy.data.objects:
  if ob.name.startswith(('neighbourhood shelter','neighbourhood green bin')):ob.hide_render=True
 cube('home doorway left',(-7.6,-48,1.5),(.18,.2,3),'cream')
 cube('home doorway right',(-5.5,-48,1.5),(.18,.2,3),'cream')
 cube('home doorway lintel',(-6.55,-48,3),(2.3,.2,.22),'cream')
 for k,(x,y) in enumerate([(-8.2,-43),(-5.65,-37),(-8.4,-34)]):
  extra=Person('HOME passerby'+str(k),outfit=['cream','teal','blue'][k],hair='short');extra.pose(1,(x,y,.13),0)
if sid=='05':driver=Person('CUT05 driver',outfit='purple',hair='short');reveal(driver)
if sid=='10':
 for k in range(2):
  p=Person('CUT10 officer'+str(k),outfit='navy',hair='short');cube('police cap',(0,0,1.81),(.28,.25,.07),'navy',p.root);cops.append(p)
if sid=='04':
 for k in range(3):
  p=Person('CUT04 cleared passenger'+str(k),outfit=['cream','teal','blue'][k],hair='short');p.pose(1,(-8.6,-25-k*2,.13),math.pi,walk=.7)
# Crowd remains in protected storefront pockets; pose gestures are already present.
# Roadside crash debris is only visible after impact.
for ob in bpy.data.objects:
 if ob.name.startswith(('fixed crash debris','damaged canopy post')):ob.hide_render=sid in ['03','04','05','06']
bpy.ops.object.camera_add();cam=bpy.context.object;cam.name='CUT'+sid+' follow';cam.data.sensor_fit='HORIZONTAL';cam.data.sensor_width=36;cam.data.lens=36/(2*math.tan(math.radians(52)/2));s.camera=cam
s.render.resolution_x=288;s.render.resolution_y=512;s.cycles.samples=8;s.render.fps=12;s.frame_start=1;s.frame_end=N
out=R/'guides'/f'{sid}{variant}-frames';out.mkdir(exist_ok=True)
def lerp(a,b,u):return Vector(a).lerp(Vector(b),u)
def ease(u):return u*u*(3-2*u)
def path(points,u):
 v=min(len(points)-1.00001,max(0,u)*(len(points)-1));i=int(v);return lerp(points[i],points[i+1],v-i)
def face(v):return math.atan2(-v.x,v.y)
def window_pose(actor,f,centre,tilt,facing,seated=0,reach=None):
 rot=Matrix.Rotation(tilt,3,'Y')@Matrix.Rotation(facing,3,'Z')
 root=Vector(centre)-rot@Vector((0,0,.9))
 actor.pose(f,root,facing,seated=seated,reach=reach)
 actor.root.rotation_euler=rot.to_euler();actor.root.keyframe_insert('rotation_euler',frame=f)
 return root
marks=[]
for f in range(1,N+1):
 t=(f-1)/12;u=t/dur
 if sid=='03':
  p=Vector((-6.55,-47.7+3.75*t,.13));sa_run_pose(hero,f,p,0,t,move_segment)
  distance=1.5+1.3*ease(min(1,t/.6));cp=p+Vector((0,-distance,1.95));target=p+Vector((0,.4,1.1))
 elif sid=='04':
  pts=[(-6.55,-27.5,.13),(-6.55,-23.0,.13),(-5.6,-21.0,.13),(-3.7,-20.9,.13),(-1.85,-22.85,.13)];p=path(pts,u);d=path(pts,min(1,u+.02))-path(pts,max(0,u-.02));angle=face(d);hero.pose(f,p,angle,walk=t*12)
  # A naive rear offset enters the bus during the tight turn. Stage the chase
  # camera outside the rigid vehicle footprint throughout the nose crossing.
  cp=path([(-7.8,-31,2.8),(-8.5,-24,2.8),(-6,-17,2.8),(-1.2,-17.5,2.8),(1.9,-20.4,2.8)],u)
  target=p+Vector((0,0,1.15))
 elif sid=='05':
  # Cross the small opening at sill height. The previous upright proxy moved
  # through the lower body panel and encouraged H3 to invent a full-height door.
  if t<.45:dc=Vector((-2.72,-22.85,1.53));dt=0
  elif t<.95:
   v=ease((t-.45)/.5);dc=lerp((-2.72,-22.85,1.53),(-2.6,-22.85,2.18),v);dt=math.pi/2*v
  elif t<1.55:dc=lerp((-2.6,-22.85,2.18),(-.9,-22.85,2.18),ease((t-.95)/.6));dt=math.pi/2
  elif t<2:
   v=ease((t-1.55)/.45);dc=lerp((-.9,-22.85,2.18),(-.3,-23.4,.9),v);dt=math.pi/2*(1-v)
  else:dc=lerp((-.3,-23.4,.9),(.5,-24.3,.9),min(1,(t-2)/1.2));dt=0
  window_pose(driver,f,dc,dt,-math.pi/2,seated=max(0,1-t/.7))
  if t<2:hc=Vector((-1.85,-22.85,.9));ht=0;seat=0
  elif t<2.65:
   v=ease((t-2)/.65);hc=lerp((-1.85,-22.85,.9),(-1.7,-22.85,2.18),v);ht=-math.pi/2*v;seat=0
  elif t<3.35:hc=lerp((-1.7,-22.85,2.18),(-3.35,-22.85,2.18),ease((t-2.65)/.7));ht=-math.pi/2;seat=0
  else:
   v=ease(min(1,(t-3.35)/.65));hc=lerp((-3.35,-22.85,2.18),(-2.72,-22.85,1.53),v);ht=-math.pi/2*(1-v);seat=v
  p=window_pose(hero,f,hc,ht,math.pi/2,seated=seat,reach=(.1,.4,1.77) if t<2 else (.1,.3,1.3))
  pane=bpy.data.objects.get('intact driver side glass');pane.hide_render=t>.5;pane.keyframe_insert('hide_render',frame=f)
  cp=Vector((1,-20,2.8));target=Vector((-2.0,-23,1.4))
 elif sid=='06':
  x=-3.65+1.8*math.sin(math.pi*u)**2;bus.location=(x,-28+16*u,0);bus.rotation_euler=(0,.025*math.sin(2*math.pi*u),-.12*math.sin(2*math.pi*u));p=bus.location.copy();cp=p+Vector((0,-12,4.5));target=p+Vector((0,2,1.8))
  for name,offset,phase,power in [('offscreen blue pursuer',(-3,-6,-2.5),0,6000),('offscreen red pursuer',(3,-10,-2.5),1.9,3500)]:
   light=bpy.data.objects.get(name)
   if light:light.hide_render=False;light.location=cp+Vector(offset);light.data.energy=power*(.05+.95*max(0,math.sin(t*9+phase))**4);light.data.keyframe_insert('energy',frame=f);light.keyframe_insert('location',frame=f)
 elif sid=='07':
  slide=ease(min(1,u/.86));roll=ease(max(0,min(1,(u-.16)/.54)));bus.rotation_euler=(0,math.pi/2*roll,.18*math.sin(math.pi*min(1,u/.75)));bus.location=(-3.65-1.45*slide,-12+12*slide,1.45*roll)
  # Ground the body during the roll using its actual transformed bounds.
  if 0<roll<1:
   rot=bus.rotation_euler.to_matrix();zmin=min((rot@(o.matrix_local@Vector(v))).z for o in bus.children if o.type=='MESH' for v in o.bound_box);bus.location.z=max(0,-zmin)
  p=bus.location.copy();cp=lerp((-3.65,-24,4.5),(-.5,-14,6.5),slide);target=p+Vector((2.3,0,0))
 elif sid=='09':
  bus.location=(-5.1,0,1.45);bus.rotation_euler=(0,math.pi/2,0);p=Vector((-6.3,5.4+max(0,t-1.3)*2,.13));hero.pose(f,p,0,walk=0 if t<1.3 else t*12,reach=(.05,-.07,1.45) if t<1.3 else None);cp=p+Vector((-.4,-4.1,1.87));target=p+Vector((.2,0,1.12))
 else:
  bus.location=(-5.1,0,1.45);bus.rotation_euler=(0,math.pi/2,0);pts=[(-6.55,14,.13),(-7.15,22.1,.13),(-9.58,25.3,.13)];p=path(pts,u);d=path(pts,min(1,u+.02))-path(pts,max(0,u-.02));speed=d.length/((min(1,u+.02)-max(0,u-.02))*dur)
  sa_run_pose(hero,f,p,face(d),t,move_segment,speed=speed)
  lengths=[(Vector(pts[i+1])-Vector(pts[i])).length for i in range(2)]
  hero_distance=lengths[0]*u*2 if u<.5 else lengths[0]+lengths[1]*(u*2-1)
  for k,c in enumerate(cops):
   follow=hero_distance-3.2-k*.3
   if follow<0:chase=Vector(pts[0])+(Vector(pts[1])-Vector(pts[0])).normalized()*follow
   elif follow<lengths[0]:chase=lerp(pts[0],pts[1],follow/lengths[0])
   else:chase=lerp(pts[1],pts[2],(follow-lengths[0])/lengths[1])
   tangent=(p-chase).normalized();sideways=Vector((tangent.y,-tangent.x,0))
   chase+=sideways*(-.55 if k==0 else .55)
   chase_direction=p-chase
   sa_run_pose(c,f,chase,face(chase_direction),t,move_segment,speed=speed,phase_offset=k*.3)
  cp=p+Vector((.65,-4.8,1.97));target=p+Vector((-1.1,2.5,1.27))
 if sid in ['04','05','06','07']:
  for prop in ['location','rotation_euler']:bus.keyframe_insert(prop,frame=f)
 cam.location=cp;cam.rotation_euler=(target-cp).to_track_quat('-Z','Y').to_euler()
 for prop in ['location','rotation_euler']:cam.keyframe_insert(prop,frame=f)
 s.frame_set(f);s.render.filepath=str(out/f'{f:04}.png');bpy.ops.render.render(write_still=True)
 marks.append({'frame':f,'time':t,'player_or_bus':list(p),'camera':list(cp)})
(R/'guides'/f'{sid}{variant}-motion.json').write_text(json.dumps({'fps':12,'frames':N,'duration':dur,'role':'original procedural motion control, not finished appearance','marks':marks},indent=2))
bpy.ops.wm.save_as_mainfile(filepath=str(R/'guides'/f'{sid}{variant}-motion.blend'))
print('Finished guide',sid)
