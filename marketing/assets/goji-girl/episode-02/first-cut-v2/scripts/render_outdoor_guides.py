"""Continuous original blocking guides, using the frozen bus/street and crowd."""
import bpy,math,json,sys
from pathlib import Path
from mathutils import Vector,Matrix
R=Path(__file__).resolve().parents[1];E=R.parent
sid=sys.argv[-1];variant='-grip-motion-v2' if sid in ['03','04','09','10'] else '-full-motion-v1';dur={'03':3,'04':3,'05':4,'06':5,'07':5,'09':2,'10':4}[sid];N=dur*12+1
exec((R/'scripts/sa_gait.py').read_text())
exec((R/'scripts/stunt_motion.py').read_text())
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
# Expand the chase road. Neighbourhood shots use their own local origin, mapped
# to world Y-200; moving that pocket preserves the reviewed 04/05 appearance.
if sid in ['06','07','09','10']:
 for ob in bpy.data.objects:
  if ob.name.startswith(('neighbourhood','HDB window')):ob.location.y-=200
 for name in ['two-way asphalt','west sidewalk','east sidewalk']:
  ob=bpy.data.objects[name];ob.location.y=-100;ob.scale.y=320
 for yy in range(-200,-40,6):
  cube('v2 fast-flow centre dash',(0,yy,.016),(.10,3,.02),'white')
  for xx in [-5.04,-4.88,4.88,5.04]:cube('v2 long edge stripe',(xx,yy,.016),(.055,5.98,.02),'yellow')
 for yy in range(-180,-40,18):
  segment('v2 roadside tree',(-7.7,yy,.12),(-7.7,yy,6),.22,.14,'trunk')
  ico('v2 roadside crown',(-7.7,yy,6),(2.1,2.4,1.8),'leaf',sub=2)
 for yy in range(-165,-40,35):
  cube('v2 HDB block',(-15,yy,13),(7,18,26),'cream')
  for zz in range(2,25,3):
   for dy in [-6,-3,0,3,6]:cube('v2 HDB window',(-11.45,yy+dy,zz),(.04,1.4,1.6),'glass')
# Breakable canopy supports: their impact response is visible, not a static prop.
crash_posts=[]
if sid in ['07','09']:
 for ob in bpy.data.objects:
  if ob.name.startswith(('damaged canopy post','fixed crash debris')):ob.hide_render=True
 for ob in list(bpy.data.objects):
  if ob.name.startswith('canopy post') and ob.location.y<=3:
   pos=ob.location.copy();hinge=empty('v2 breakable canopy hinge',(pos.x,pos.y,.10))
   ob.parent=hinge;ob.location=(0,0,1.77);crash_posts.append((hinge,pos.y))
 impact_post=empty('v2 end-impact support',(-5.62,6.2,.10))
 cube('v2 end support',(0,0,1.77),(.18,.18,3.54),'silver',impact_post)
 crash_posts.append((impact_post,6.2))
 # The struck canopy bay buckles up at its wall hinge, clearing the exit.
 roof=bpy.data.objects['silver canopy roof'];roof.location.y=10.6;roof.scale.y=5.0
 roof_hinge=empty('v2 struck roof hinge',(-9.95,1.6,3.65))
 cube('v2 buckled canopy bay',(2.2,0,0),(4.4,11,.14),'silver',roof_hinge)
 # Empty mall-side bay: move the bin out of the slide/exit corridor.
 bpy.data.objects['fixed green bin'].location=(-8.9,-2,.65)
 for ob in bpy.data.objects:
  if ob.name.startswith(('bollard','chevron')) and ob.location.y<6:ob.hide_render=True
if sid=='09':
 for hinge,yy in crash_posts:hinge.rotation_euler.x=-math.radians(78)
 roof_hinge.rotation_euler.y=-math.radians(65)
# Keep the approach tree outside both the vehicle slide and follow-camera route.
if sid in ['06','07','09','10']:
 for ob in bpy.data.objects:
  if ob.name.startswith(('tree trunk','tree crown')) and ob.location.y<0:ob.location.x-=5
# Contact solver only uses structural body/tyre bounds; mirrors are breakable.
bpy.context.view_layer.update()
contact_points=[]
inv=bus.matrix_world.inverted()
for ob in bus.children_recursive:
 if ob.type=='MESH' and ob.name.startswith(('wheel','roof','rear bulkhead','front lower nose','floor','driver right lower side','left front corner')):
  contact_points += [inv@(ob.matrix_world@Vector(v)) for v in ob.bound_box]
def ground_bus(x,y,yaw,roll):
 rot=Matrix.Rotation(yaw,3,'Z')@Matrix.Rotation(roll,3,'Y')
 points=[rot@v for v in contact_points]
 z=max((.13 if x+v.x<-5.2 else 0)-v.z for v in points)
 bus.location=(x,y,max(0,z));bus.rotation_euler=(0,roll,yaw)
 return bus.location.copy()
wheel_spokes=[]
for xx in [-1.455,1.455]:
 for yy in [-4.2,-2.8,3.15]:
  hub=empty('v2 wheel-spin hub',(xx,yy,.51),bus)
  cube('v2 rim spoke',(0,0,0),(.015,.62,.045),'silver',hub)
  cube('v2 rim spoke',(0,0,0),(.015,.045,.62),'silver',hub)
  wheel_spokes.append(hub)

# Crowd remains in protected storefront pockets; pose gestures are already present.
# Roadside crash debris is only visible after impact.
for ob in bpy.data.objects:
 if ob.name.startswith(('fixed crash debris','damaged canopy post')):ob.hide_render=True
bpy.ops.object.camera_add();cam=bpy.context.object;cam.name='CUT'+sid+' follow';cam.data.sensor_fit='HORIZONTAL';cam.data.sensor_width=36;cam.data.lens=36/(2*math.tan(math.radians(52)/2));s.camera=cam
s.render.resolution_x=288;s.render.resolution_y=512;s.cycles.samples=8;s.render.fps=12;s.frame_start=1;s.frame_end=N
out=R/'guides'/f'{sid}{variant}-frames';out.mkdir(exist_ok=True)
def lerp(a,b,u):return Vector(a).lerp(Vector(b),u)
def ease(u):return u*u*(3-2*u)
def path(points,u):
 v=min(len(points)-1.00001,max(0,u)*(len(points)-1));i=int(v);return lerp(points[i],points[i+1],v-i)
def arc_path(points,u):
 lengths=[(Vector(b)-Vector(a)).length for a,b in zip(points,points[1:])];distance=max(0,min(1,u))*sum(lengths)
 for a,b,length in zip(points,points[1:],lengths):
  if distance<=length:return lerp(a,b,distance/length)
  distance-=length
 return Vector(points[-1])
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
  pts=[(-6.55,-27.5,.13),(-7.3,-24.5,.13),(-7.3,-22,.13),(-6.8,-20.2,.13),(-5,-20.2,.13),(-3.7,-20.9,.13),(-1.8,-20.9,.13),(-1.85,-22.85,.13)];p=arc_path(pts,u);d=arc_path(pts,min(1,u+.02))-arc_path(pts,max(0,u-.02));angle=face(d)
  speed=sum((Vector(b)-Vector(a)).length for a,b in zip(pts,pts[1:]))/dur
  sa_run_pose(hero,f,p,angle,t,move_segment,speed=speed)
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
  xy,yaw,roll=chase_pose(t);p=ground_bus(*xy,yaw,roll)
  lagxy,_,_=chase_pose(max(0,t-.12));cp=Vector((lagxy[0],p.y-12,4.3));target=Vector((p.x,p.y+2,1.9))
  for hub in wheel_spokes:hub.rotation_euler.x=-22*t/.5;hub.keyframe_insert('rotation_euler',frame=f)
  for name,offset,phase,power in [('offscreen blue pursuer',(-3,-6,-2.5),0,6000),('offscreen red pursuer',(3,-10,-2.5),1.9,3500)]:
   light=bpy.data.objects.get(name)
   if light:light.hide_render=False;light.location=cp+Vector(offset);light.data.energy=power*(.05+.95*max(0,math.sin(t*9+phase))**4);light.data.keyframe_insert('energy',frame=f);light.keyframe_insert('location',frame=f)
 elif sid=='07':
  xy,yaw,roll,phase=crash_pose(t);p=ground_bus(*xy,yaw,roll)
  lagxy,_,_,_=crash_pose(max(0,t-.12));centre=2.1*math.sin(roll);cp=Vector((lagxy[0]+centre,p.y-12,4.3));target=Vector((p.x+centre,p.y+2,1.9))
  # A short impulse after impact, not a camera orbit or a rolled horizon.
  if 3.15<t<3.55:cp+=Vector((.07*math.sin(t*75),0,.045*math.cos(t*90)))*(1-(t-3.15)/.4)
  for hub in wheel_spokes:hub.rotation_euler.x=-22*min(t,1.95)/.5-(max(0,t-1.95)*7);hub.keyframe_insert('rotation_euler',frame=f)
  roof_hinge.rotation_euler.y=-math.radians(65)*ease(max(0,min(1,(t-2.9)/.45)));roof_hinge.keyframe_insert('rotation_euler',frame=f)
  for hinge,yy in crash_posts:
   hit={-3:2.90,0:3.05,3:3.15,6.2:3.33}.get(yy,3.15)
   hinge.rotation_euler.x=-math.radians(78)*ease(max(0,min(1,(t-hit)/.18)));hinge.keyframe_insert('rotation_euler',frame=f)
 elif sid=='09':
  ground_bus(WRECK_X,WRECK_Y,0,WRECK_ROLL);p=Vector((-7.35,4.4+max(0,t-1.3)*2,.13));hero.pose(f,p,0,walk=0 if t<1.3 else t*12,reach=(.05,-.07,1.45) if t<1.3 else None);cp=p+Vector((-.4,-4.1,1.87));target=p+Vector((.2,0,1.12))
 else:
  ground_bus(WRECK_X,WRECK_Y,0,WRECK_ROLL);pts=[(-6.55,14,.13),(-6.55,22.1,.13),(-9.58,25.3,.13)];p=path(pts,u);d=path(pts,min(1,u+.02))-path(pts,max(0,u-.02));speed=d.length/((min(1,u+.02)-max(0,u-.02))*dur)
  sa_run_pose(hero,f,p,face(d),t,move_segment,speed=speed)
  a0=face(Vector(pts[1])-Vector(pts[0]));a1=face(Vector(pts[2])-Vector(pts[1]));ca=a0+(a1-a0)*ease(max(0,min(1,(t-1.8)/.5)));cr=Matrix.Rotation(ca,3,'Z')
  for k,c in enumerate(cops):
   # Continuous flanking chase arcs keep the player visible during the turn.
   chase=p+cr@Vector((-.55 if k==0 else .95,-2.0-k*.3,0))
   sa_run_pose(c,f,chase,ca,t,move_segment,speed=speed,phase_offset=k*.3)
  cp=p+cr@Vector((.15,-3.6,1.97));target=p+cr@Vector((0,.8,1.2))
 if sid=='09':
  hero.bag.rotation_euler=(0,0,math.pi/2);hero.bag.keyframe_insert('rotation_euler',frame=f)
 if sid in ['04','05','06','07']:
  for prop in ['location','rotation_euler']:bus.keyframe_insert(prop,frame=f)
 cam.location=cp;cam.rotation_euler=(target-cp).to_track_quat('-Z','Y').to_euler()
 for prop in ['location','rotation_euler']:cam.keyframe_insert(prop,frame=f)
 s.frame_set(f);s.render.filepath=str(out/f'{f:04}.png');bpy.ops.render.render(write_still=True)
 marks.append({'frame':f,'time':t,'player_or_bus':list(p),'camera':list(cp),'bus_rotation':list(bus.rotation_euler),'phase':phase if sid=='07' else None})
(R/'guides'/f'{sid}{variant}-motion.json').write_text(json.dumps({'fps':12,'frames':N,'duration':dur,'role':'original procedural motion control, not finished appearance','marks':marks},indent=2))
bpy.ops.wm.save_as_mainfile(filepath=str(R/'guides'/f'{sid}{variant}-motion.blend'))
print('Finished guide',sid)
