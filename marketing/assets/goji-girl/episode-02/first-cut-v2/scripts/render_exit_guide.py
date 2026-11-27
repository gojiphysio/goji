"""Contact-driven original rolled-bus climb; no vertically translated stand pose."""
import bpy,math,json,sys
from pathlib import Path
from mathutils import Vector,Matrix
R=Path(__file__).resolve().parents[1];E=R.parent
bpy.ops.wm.open_mainfile(filepath=str(R/'guides/07-full-motion-v1-motion.blend'))
s=bpy.context.scene;s.frame_set(61);bpy.context.view_layer.update()
for o in bpy.data.objects:
 o.animation_data_clear()
 if o.name.startswith(('GG','DRIVER','EXIT','EZLink','ROUTE','CUT','offscreen')):o.hide_render=True
bus=bpy.data.objects['BUS-SOS-01 chassis transform'];T=bus.matrix_world.copy()
source=(E/'revision-07/scripts/build_continuity.py').read_text();exec(source[source.index('M={}'):source.index('# +Y is vehicle forward')])
p=Person('V2 contact exit');card=cube('V2 transit card',(0,0,0),(.075,.01,.045),'blue')
def point(x,y,z):return T@Vector((x,y,z))
# Sill, card reader, and outer floor edge are all in the ONE bus frame.
sill=point(-1.32,4.4,.56);reader=point(-1.08,4.062,1.60);outer=point(-1.30,4.4,.40)
B=bus.location.x;Z=sill.z
# Each mark: seconds, pelvis x/z, torso lean, heading degrees,
# left/right palms x/z, left/right ankles x/z. Y stays within actual door.
marks=[
 (0,   (B+1.0,Z-.60),45,90, (sill.x,Z),(sill.x,Z), (B+1.2,Z-1.18),(B+.95,Z-1.18)),
 (.4,  (B+1.0,Z-.60),45,90, (sill.x,Z),(sill.x,Z), (B+1.2,Z-1.18),(B+.95,Z-1.18)),
 (1.1, (B+.85,Z-.13),60,90, (sill.x,Z),(sill.x,Z), (B+.70,Z+.07),(B+1.1,Z-.78)),
 (1.8, (B+.70,Z+.02),65,90, (sill.x,Z),(sill.x,Z), (B+.55,Z+.07),(B+1.05,Z-.38)),
 (2.35,(B+.85,Z-.07),65,-90,(sill.x,Z),(B+1.15,Z+.18),(B+.55,Z+.07),(B+.85,Z+.07)),
 (2.8, (B+.85,Z-.07),65,-90,(sill.x,Z),(reader.x,reader.z),(B+.55,Z+.07),(B+.85,Z+.07)),
 (3.1, (B+.85,Z-.07),65,-90,(sill.x,Z),(reader.x,reader.z),(B+.55,Z+.07),(B+.85,Z+.07)),
 (3.6, (B+.45,Z+.02),35,-90,(sill.x,Z),(sill.x,Z),(B+.25,Z+.07),(B+.65,Z+.07)),
 (4.25,(B-.08,Z-.12),25,-90,(outer.x,Z),(outer.x,Z),(B-.2,Z-.55),(B+.45,Z+.02)),
 (5.0, (B-.30,Z-.55),15,-90,(outer.x,Z),(outer.x,Z),(B-.37,Z-1.28),(B+.35,Z-.98)),
 (5.8, (B+.05,Z-.75),0,-90,(outer.x,Z),(outer.x,Z),(B-.3,Z-1.50),(B+.35,Z-1.56)),
 (6.15,(B+.05,Z-.75),0,-90,(outer.x,Z),(outer.x,Z),(B-.3,Z-1.50),(B+.35,Z-1.56)),
 (6.58,(B-.85,1.00),12,-90,(B-.55,1.53),(B-.55,1.53),(B-.85,.23),(B-.85,.23)),
 (6.78,(B-.85,.79),22,-90,(B-.55,1.18),(B-.55,1.18),(B-.85,.23),(B-.85,.23)),
 (7.25,(B-.85,1.01),0,-90,(B-.7,1.0),(B-.7,1.0),(B-.85,.23),(B-.85,.23)),
 (8.0, (B-.85,1.01),0,0,(B-1.15,.97),(B-.55,.97),(B-.97,.23),(B-.73,.23)),
]
def interp(t):
 for a,b in zip(marks,marks[1:]):
  if a[0]<=t<=b[0]:
   u=(t-a[0])/(b[0]-a[0]);u=u*u*(3-2*u)
   if a[0]==6.15:u=((t-a[0])/(b[0]-a[0]))**2
   return [t]+[tuple(x+(y-x)*u for x,y in zip(aa,bb)) if isinstance(aa,tuple) else aa+(bb-aa)*u for aa,bb in zip(a[1:],b[1:])]
 return marks[-1]
def vec(xz,y):return Vector((xz[0],y,xz[1]))
violations=[];records=[]
def limb(a,b,length,bend,label,t):
 d=b-a;dist=d.length
 if dist>length*2+.035:violations.append({'time':t,'limb':label,'reach':dist,'max':length*2})
 unit=d.normalized();pole=Vector(bend);pole=(pole-unit*pole.dot(unit)).normalized()
 return (a+b)*.5+pole*math.sqrt(max(0,length*length-min(dist,length*2)**2/4))
bpy.ops.object.camera_add();cam=bpy.context.object;s.camera=cam;cam.data.sensor_fit='HORIZONTAL';cam.data.sensor_width=36;cam.data.lens=36/(2*math.tan(math.radians(62)/2))
s.render.resolution_x=288;s.render.resolution_y=512;s.render.fps=12;s.cycles.samples=8;s.frame_start=1;s.frame_end=97
out=R/'guides/08-grip-motion-v2-frames';out.mkdir(exist_ok=True)
for f in range(1,98):
 t=(f-1)/12;_,pel,lean,heading,lh,rh,lf,rf=interp(t)
 rot=Matrix.Rotation(math.radians(heading),3,'Z')@Matrix.Rotation(math.radians(-lean),3,'X')
 pelvis=vec(pel,4.4);root=pelvis-rot@Vector((0,0,.88));p.pose(f,root);p.root.rotation_euler=rot.to_euler();p.root.keyframe_insert('rotation_euler',frame=f)
 inv=rot.transposed()
 for side,hand,foot in [(-1,lh,lf),(1,rh,rf)]:
  # Sideways spread lies along bus length while facing east/west; return to
  # normal x-spread only once both feet have landed and she turns north.
  spread=Vector((side*.13,0,0));spread=Matrix.Rotation(math.radians(heading),3,'Z')@spread
  ankle=vec(foot,4.4)+Vector((0,spread.y,0))
  if side==1 and 1.8<t<4.25:
   weight=min(1,(t-1.8)/.55,max(0,(4.25-t)/.65));ankle.y+=(3.75-ankle.y)*weight
  wrist=vec(hand,4.4+(-side*.22 if heading<0 else side*.22))
  if 2.8<=t<=3.1 and side==1:wrist=reader.copy()
  if t>=7.25:
   u=(t-7.25)/.75;wrist=vec(hand,4.4)+Vector((0,spread.y*1.6,0))
  hip=root+rot@Vector((side*.115,0,.88));shoulder=root+rot@Vector((side*.235,0,1.35))
  forward=rot@Vector((0,1,0));knee=limb(hip,ankle,.46,forward,'leg'+str(side),t);elbow=limb(shoulder,wrist,.34,Vector((0,side,0)),'arm'+str(side),t)
  for name,a,b in [('thigh',hip,knee),('calf',knee,ankle),('upperarm',shoulder,elbow),('forearm',elbow,wrist)]:move_segment(p.parts[(side,name)],inv@(a-root),inv@(b-root),f)
  shoe=p.parts[(side,'shoe')];shoe.location=inv@(ankle-root);shoe.rotation_euler=(Matrix.Rotation(math.radians(heading),3,'Z').inverted()@rot).inverted().to_euler()
  for prop in ['location','rotation_euler']:shoe.keyframe_insert(prop,frame=f)
  h=p.parts[(side,'hand')];h.location=inv@(wrist-root);h.keyframe_insert('location',frame=f)
  if side==-1:
   p.bag.location=inv@(wrist-root);p.bag.rotation_euler=(inv@Matrix.Rotation(math.radians(heading)+math.pi/2,3,'Z')).to_euler()
   for prop in ['location','rotation_euler']:p.bag.keyframe_insert(prop,frame=f)
  else:
   card.location=wrist;card.hide_render=not (2.35<t<3.3)
   for prop in ['location','hide_render']:card.keyframe_insert(prop,frame=f)
 cp=Vector((-8.9,7.8,4.0));target=Vector((B+.55,4.4,1.9))
 cam.location=cp;cam.rotation_euler=(target-cp).to_track_quat('-Z','Y').to_euler()
 s.frame_set(f);s.render.filepath=str(out/f'{f:04}.png')
 if '--audit' not in sys.argv and ('--preview' not in sys.argv or f in [1,14,23,34,46,61,72,80,88,97]):bpy.ops.render.render(write_still=True)
 records.append({'time':t,'pelvis':list(pelvis),'hands':[list(vec(lh,4.18)),list(vec(rh,4.62))],'phase':'braced climb' if t<2.35 else 'supported card tap' if t<3.3 else 'climb down' if t<6.15 else 'drop and landing' if t<7.25 else 'recover'})
(R/'guides/08-contact-audit.json').write_text(json.dumps({'sill':list(sill),'reader':list(reader),'bus_pose':list(bus.location),'violations':violations,'marks':records},indent=2))
bpy.ops.wm.save_as_mainfile(filepath=str(R/'guides/08-grip-exit.blend'));print('CONTACT VIOLATIONS',len(violations))
