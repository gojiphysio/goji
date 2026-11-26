"""Continuous original blocking guides, using the frozen bus/street and crowd."""
import bpy,math,json,sys
from pathlib import Path
from mathutils import Vector
R=Path(__file__).resolve().parents[1];E=R.parent
sid=sys.argv[-1];dur={'04':3,'05':4,'06':5,'07':5,'09':2,'10':4}[sid];N=dur*12+1
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
if sid in ['04','05','09','10']:hero=Person('CUT'+sid+' GG01');reveal(hero)
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
 if ob.name.startswith(('fixed crash debris','damaged canopy post')):ob.hide_render=sid in ['04','05','06']
bpy.ops.object.camera_add();cam=bpy.context.object;cam.name='CUT'+sid+' follow';cam.data.sensor_fit='HORIZONTAL';cam.data.sensor_width=36;cam.data.lens=36/(2*math.tan(math.radians(52)/2));s.camera=cam
s.render.resolution_x=288;s.render.resolution_y=512;s.cycles.samples=8;s.render.fps=12;s.frame_start=1;s.frame_end=N
out=R/'guides'/f'{sid}-frames';out.mkdir(exist_ok=True)
def lerp(a,b,u):return Vector(a).lerp(Vector(b),u)
def ease(u):return u*u*(3-2*u)
def path(points,u):
 v=min(len(points)-1.00001,max(0,u)*(len(points)-1));i=int(v);return lerp(points[i],points[i+1],v-i)
def face(v):return math.atan2(-v.x,v.y)
marks=[]
for f in range(1,N+1):
 t=(f-1)/12;u=t/dur
 if sid=='04':
  pts=[(-6.55,-27.5,.13),(-6.55,-23.0,.13),(-5.6,-21.0,.13),(-3.7,-20.9,.13),(-1.85,-22.85,.13)];p=path(pts,u);d=path(pts,min(1,u+.02))-path(pts,max(0,u-.02));angle=face(d);hero.pose(f,p,angle,walk=t*12)
  direction=Vector((-math.sin(angle),math.cos(angle),0));cp=p-direction*3.6+Vector((0,0,2.1));target=p+direction+Vector((0,0,1.2))
 elif sid=='05':
  if t<.8:hp=Vector((-1.85,-22.85,0));dp=Vector((-2.72,-22.85,.63));re=(.1,.4,1.77)
  elif t<2.2:
   v=ease((t-.8)/1.4);hp=lerp((-1.85,-22.85,0),(-1.0,-22.8,0),v);dp=lerp((-2.72,-22.85,.63),(-.30,-23.4,0),v);re=(.1,.4,1.4)
  else:
   v=ease(min(1,(t-2.2)/1.5));hp=lerp((-1.0,-22.8,0),(-2.72,-22.85,.63),v);dp=lerp((-.30,-23.4,0),(.5,-24.3,0),v);re=(.1,.3,1.3)
  hero.pose(f,hp,math.pi/2,walk=t*8 if t>2.2 else 0,seated=max(0,min(1,(t-3.2)/.5)),reach=re);driver.pose(f,dp,-math.pi/2,walk=t*8 if t>1 else 0,seated=max(0,1-t/1.2));p=hp
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
  bus.location=(-5.1,0,1.45);bus.rotation_euler=(0,math.pi/2,0);pts=[(-6.55,14,.13),(-7.15,22.1,.13),(-9.58,25.3,.13)];p=path(pts,u);d=path(pts,min(1,u+.02))-path(pts,max(0,u-.02));hero.pose(f,p,face(d),walk=t*12)
  for k,c in enumerate(cops):c.pose(f,p+Vector((-.8 if k==0 else 1.25,-3.2-k*.3,0)),face(d),walk=t*12+k*2)
  cp=p+Vector((.65,-4.8,1.97));target=p+Vector((-1.1,2.5,1.27))
 if sid in ['04','05','06','07']:
  for prop in ['location','rotation_euler']:bus.keyframe_insert(prop,frame=f)
 cam.location=cp;cam.rotation_euler=(target-cp).to_track_quat('-Z','Y').to_euler()
 for prop in ['location','rotation_euler']:cam.keyframe_insert(prop,frame=f)
 s.frame_set(f);s.render.filepath=str(out/f'{f:04}.png');bpy.ops.render.render(write_still=True)
 marks.append({'frame':f,'time':t,'player_or_bus':list(p),'camera':list(cp)})
(R/'guides'/f'{sid}-motion.json').write_text(json.dumps({'fps':12,'frames':N,'duration':dur,'role':'original procedural motion control, not finished appearance','marks':marks},indent=2))
bpy.ops.wm.save_as_mainfile(filepath=str(R/'guides'/f'{sid}-motion.blend'))
print('Finished guide',sid)
