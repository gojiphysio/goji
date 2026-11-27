"""Original geometry/motion blockout. Proxy cast, not final PS2 appearance."""
import bpy, math, json, sys, hashlib
from pathlib import Path
from mathutils import Vector
OUT=Path(__file__).resolve().parents[1]
(OUT/'blender').mkdir(exist_ok=True)
(OUT/'blender/sequence').mkdir(exist_ok=True)
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
M={}
def mat(n,c,rough=1,metal=0):
 m=bpy.data.materials.new(n);m.diffuse_color=(*c,1);m.use_nodes=True
 bs=m.node_tree.nodes.get('Principled BSDF');bs.inputs['Base Color'].default_value=(*c,1);bs.inputs['Roughness'].default_value=rough;bs.inputs['Metallic'].default_value=metal;M[n]=m;return m
for n,c in {'blue':(.025,.24,.52),'navy':(.02,.07,.12),'glass':(.12,.25,.29),'tyre':(.025,.029,.028),'silver':(.5,.53,.51),'maroon':(.29,.025,.055),'skin':(.57,.32,.14),'skin2':(.69,.44,.25),'hair':(.022,.019,.016),'white':(.83,.81,.71),'gold':(.81,.55,.13),'road':(.25,.27,.25),'concrete':(.54,.51,.42),'cream':(.74,.69,.51),'green':(.15,.24,.08),'leaf':(.27,.35,.1),'trunk':(.23,.16,.08),'teal':(.06,.24,.21),'yellow':(.93,.62,.035),'orange':(.58,.24,.055),'black':(.025,.027,.025),'red':(.47,.08,.055),'grey':(.28,.30,.29)}.items():mat(n,c)
def finish(o,n,m,parent=None):
 o.name=n;o.data.materials.append(M[m]);o.parent=parent;return o
def cube(n,p,s,m,parent=None,bevel=0):
 bpy.ops.mesh.primitive_cube_add(size=1,location=p);o=finish(bpy.context.object,n,m,parent);o.scale=s
 if bevel:
  bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);mod=o.modifiers.new('small bevel','BEVEL');mod.width=bevel;mod.segments=1
 return o
def ico(n,p,s,m,parent=None,sub=1):
 bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=sub,radius=1,location=p);o=finish(bpy.context.object,n,m,parent);o.scale=s;return o
def uv(n,p,s,m,parent=None):
 bpy.ops.mesh.primitive_uv_sphere_add(segments=12,ring_count=8,radius=1,location=p);o=finish(bpy.context.object,n,m,parent);o.scale=s;return o
def empty(n,p=(0,0,0),parent=None):
 o=bpy.data.objects.new(n,None);bpy.context.collection.objects.link(o);o.location=p;o.parent=parent;return o
def segment(n,a,b,r1,r2,m,parent=None,vertices=8):
 a,b=Vector(a),Vector(b);bpy.ops.mesh.primitive_cone_add(vertices=vertices,radius1=r1,radius2=r2,depth=1)
 o=finish(bpy.context.object,n,m,parent);o.location=(a+b)/2;o.rotation_mode='QUATERNION';o.rotation_quaternion=(b-a).to_track_quat('Z','Y');o.scale.z=(b-a).length;return o
def move_segment(o,a,b,f):
 a,b=Vector(a),Vector(b);o.location=(a+b)/2;o.rotation_quaternion=(b-a).to_track_quat('Z','Y');o.scale.z=(b-a).length
 for prop in ['location','rotation_quaternion','scale']:o.keyframe_insert(prop,frame=f)
def text(n,body,p,size,m,rot=(math.pi/2,0,0)):
 bpy.ops.object.text_add(location=p,rotation=rot);o=finish(bpy.context.object,n,m);o.data.body=body;o.data.size=size;o.data.align_x='CENTER';o.data.extrude=.001;return o
def torso(n,parent,m):
 rings=[(.82,.19,.13),(1.02,.17,.115),(1.20,.22,.14),(1.37,.25,.13),(1.43,.13,.105)];verts=[]
 for z,rx,ry in rings:
  for i in range(8):a=2*math.pi*i/8;verts.append((rx*math.cos(a),ry*math.sin(a),z))
 faces=[]
 for j in range(4):
  for i in range(8):faces.append((j*8+i,j*8+(i+1)%8,(j+1)*8+(i+1)%8,(j+1)*8+i))
 faces += [tuple(range(7,-1,-1)),tuple(range(32,40))]
 mesh=bpy.data.meshes.new(n);mesh.from_pydata(verts,[],faces);mesh.update();o=bpy.data.objects.new(n,mesh);bpy.context.collection.objects.link(o);finish(o,n,m,parent);return o
class Person:
 def __init__(self,n,outfit='maroon',skin='skin',hair='pony'):
  self.root=empty(n);self.n=n;self.parts={};torso(n+' torso',self.root,outfit)
  segment(n+' neck',(0,0,1.37),(0,0,1.51),.075,.065,skin,self.root)
  uv(n+' face',(0,.015,1.64),(.125,.115,.165),skin,self.root)
  uv(n+' hair cap',(0,-.025,1.71),(.137,.111,.12),'hair',self.root)
  if hair=='pony':
   segment(n+' ponytail',(0,-.12,1.72),(.04,-.19,1.35),.08,.04,'hair',self.root)
  elif hair=='bob':
   for x in [-.11,.11]:uv(n+' bob',(x,-.035,1.60),(.055,.09,.145),'hair',self.root)
  for x in [-.045,.045]:
   cube(n+' eye',(x,.116,1.67),(.042,.009,.018),'white',self.root)
   cube(n+' pupil',(x,.123,1.67),(.015,.006,.017),'black',self.root)
   cube(n+' brow',(x,.118,1.696),(.048,.01,.009),'hair',self.root)
  ico(n+' nose',(0,.13,1.625),(.028,.035,.035),skin,self.root)
  cube(n+' mouth',(0,.12,1.578),(.045,.008,.008),'maroon',self.root)
  for side in [-1,1]:
   for part,a,b,r1,r2,ma in [('thigh',(side*.115,0,.87),(side*.13,0,.48),.105,.075,outfit),('calf',(side*.13,0,.48),(side*.13,0,.10),.075,.045,outfit),('upperarm',(side*.235,0,1.35),(side*.29,0,1.08),.065,.05,skin),('forearm',(side*.29,0,1.08),(side*.29,.04,.84),.05,.035,skin)]:
    self.parts[(side,part)]=segment(n+part+str(side),a,b,r1,r2,ma,self.root)
   self.parts[(side,'hand')]=uv(n+' hand',(side*.29,.04,.81),(.045,.035,.075),skin,self.root)
   self.parts[(side,'shoe')]=cube(n+' shoe',(side*.13,.07,.065),(.115,.27,.11),'white',self.root,bevel=.025)
  self.bag=None
  if hair=='pony':
   self.bag=empty(n+' handbag',parent=self.root);cube(n+' bag body',(0,0,-.22),(.26,.12,.23),'black',self.bag,bevel=.012)
   cube(n+' gold clasp',(0,.065,-.18),(.045,.008,.025),'gold',self.bag)
   for x in [-.075,.075]:segment(n+' bag handle',(x,0,-.11),(x,0,-.015),.012,.012,'black',self.bag)
   segment(n+' bag top',(-.075,0,-.015),(.075,0,-.015),.012,.012,'black',self.bag)
 def pose(self,f,pos,angle=0,walk=0,seated=0,reach=None):
  self.root.location=pos;self.root.rotation_euler.z=angle
  self.root.keyframe_insert('location',frame=f);self.root.keyframe_insert('rotation_euler',frame=f)
  for side in [-1,1]:
   phase=walk+(0 if side==1 else math.pi);swing=math.sin(phase)*(.22 if walk else 0)
   hip=(side*.115,0,.88);knee=(side*.13,swing+.30*seated,.48+.27*seated);ankle=(side*.13,-swing+.48*seated,.1+.25*seated)
   move_segment(self.parts[(side,'thigh')],hip,knee,f);move_segment(self.parts[(side,'calf')],knee,ankle,f)
   shoe=self.parts[(side,'shoe')];shoe.location=(ankle[0],ankle[1]+.07,ankle[2]-.035);shoe.keyframe_insert('location',frame=f)
   shoulder=(side*.235,0,1.35);elbow=(side*.285,-swing*.5+.15*seated,1.08);wrist=(side*.30,-swing*.9+.35*seated,.86+.18*seated)
   if reach is not None and side==1:
    wrist=reach;elbow=((shoulder[0]+wrist[0])*.5,(shoulder[1]+wrist[1])*.5-.09,1.17)
   move_segment(self.parts[(side,'upperarm')],shoulder,elbow,f);move_segment(self.parts[(side,'forearm')],elbow,wrist,f)
   hand=self.parts[(side,'hand')];hand.location=(wrist[0],wrist[1],wrist[2]-.035);hand.keyframe_insert('location',frame=f)
   if side==-1 and self.bag:
    self.bag.location=wrist;self.bag.keyframe_insert('location',frame=f)
# +Y is vehicle forward; +X is driver's right; local Z is up.
bus=empty('BUS-SOS-01 chassis transform')
bus['forward_axis']='+Y';bus['driver_side']='+X';bus['passenger_side']='-X'
bus['door_interval_y']=[3.80,5.30];bus['front_axle_y']=3.15
# Open shell, never a solid cube around the actor.
cube('floor',(0,0,.48),(2.50,12,.18),'navy',bus)
cube('roof',(0,0,3.05),(2.54,12,.20),'red',bus)
cube('driver right side',(1.25,0,1.55),(.10,12,2.0),'white',bus)
cube('right purple skirt',(1.31,0,.83),(.035,12,.55),'maroon',bus)
# Entire passenger-side wall stops at the actual FRONT passenger entrance.
for name,lo,hi in [('aft wall',-6,3.80),('front corner',5.30,6)]:
 cube('left '+name,(-1.25,(lo+hi)/2,1.55),(.10,hi-lo,2.0),'white',bus)
 cube('left skirt '+name,(-1.31,(lo+hi)/2,.83),(.035,hi-lo,.55),'maroon',bus)
cube('front passenger door header',(-1.25,4.55,2.84),(.12,1.5,.32),'white',bus)
cube('front passenger door sill',(-1.25,4.55,.56),(.12,1.5,.13),'yellow',bus)
for yy in [3.80,5.30]:cube('door jamb',(-1.26,yy,1.70),(.14,.10,2.25),'yellow',bus)
for y in [-5.2,-3.8,-2.4,-1,.4,1.8,3.0]:
 for x in [-1.31,1.31]:cube('side window',(x,y,2.20),(.025,1.15,.98),'glass',bus)
# Explicit front windscreen and rear engine, distinguishable after rollover.
cube('front lower nose',(0,6,1.0),(2.50,.12,.9),'white',bus)
cube('front windshield',(0,6.01,2.20),(2.34,.08,1.28),'glass',bus)
cube('rear bulkhead',(0,-6,1.65),(2.5,.12,2.6),'white',bus)
cube('rear glass',(0,-6.08,2.4),(2.15,.025,.80),'glass',bus)
for z in [.8,.95,1.1,1.25,1.4]:cube('rear engine louvre',(0,-6.085,z),(1.6,.03,.055),'black',bus)
for x in [-.85,.85]:
 cube('headlight',(x,6.08,.96),(.42,.035,.2),'white',bus)
 cube('red rear lamp',(x,-6.09,.9),(.24,.04,.42),'red',bus)
 for y in [-3.65,3.15]:
  segment('wheel',(x/abs(x)*1.14,y,.51),(x/abs(x)*1.43,y,.51),.5,.5,'tyre',bus,vertices=16)
# Open door leaves folded INSIDE the front jamb, not removed/teleported.
for yy in [5.37,5.49]:
 cube('folded front door glass',(-.92,yy,1.7),(.55,.045,2.1),'glass',bus)
 for zz in [.66,2.74]:cube('folded door frame',(-.92,yy,zz),(.60,.07,.055),'yellow',bus)
# Cabin and reader are all children of chassis, with local transforms fixed.
cube('right driver seat',(.64,4.30,.92),(.6,.7,.55),'navy',bus)
cube('driver seat back',(.64,3.96,1.47),(.6,.15,.8),'navy',bus)
cube('front dash',(0,5.5,1.42),(2.15,.45,.35),'navy',bus)
for y in [-4.8,-3,-1.2,.6,2.3]:
 for x in [-.65,.65]:cube('passenger seat',(x,y,.92),(.65,.6,.45),'navy',bus)
reader_pole=segment('front entrance reader pole',(-1.08,3.95,.58),(-1.08,3.95,2.74),.035,.035,'yellow',bus)
reader=cube('READER-01 at front door aft jamb',(-1.08,3.95,1.60),(.27,.16,.35),'black',bus,bevel=.025)
reader['parent_rule']='Fixed to front passenger doorway; rotates with chassis'
screen=cube('reader green display',(-1.08,4.036,1.60),(.22,.016,.27),'green',bus)
contact=empty('CARD CONTACT surface',(-1.08,4.062,1.60),bus)
# All fictional wordmarks use SOS. No SBS letter meshes or textures.
for name,p,rot,size in [('left',(-1.32,-1,1.42),(math.pi/2,0,-math.pi/2),.32),('rear',(0,-6.10,1.8),(math.pi/2,0,0),.3),('front',(0,6.10,1.35),(math.pi/2,0,math.pi),.29)]:
 o=text('SOS Transit '+name,'SOS Transit',p,size,'maroon',rot);o.parent=bus
# Roll the whole assembled rigid asset onto its RIGHT side.
bus.rotation_euler.y=math.pi/2;bus.location.z=1.45
bpy.context.view_layer.update()
# Location staging is intentionally neutral: facade likeness is in look frames.
cube('road',(1,0,-.10),(24,28,.20),'road')
cube('footpath',(-2,0,.06),(3,28,.20),'concrete')
for y in range(-12,14,2):cube('yellow curb line',(-.42,y,.012),(.08,1.8,.012),'yellow')
# Empty damaged shelter behind, not an alternate bus doorway.
cube('shelter roof',(-2,-4,2.4),(3,4,.12),'concrete').rotation_euler.y=.2
for y in [-5.5,-2.5]:segment('bent shelter post',(-2,y,.2),(-1.6,y,2.4),.06,.06,'silver')
# Proxy cast has constant limb lengths, solved two-bone chains.
girl=Person('GG01 blocking proxy')
card=cube('EZLink card in right hand',(0,0,0),(.085,.006,.055),'teal')
card.rotation_euler=(0,0,0)

def ik(a,b,l1,l2,hint):
 a,b,hint=Vector(a),Vector(b),Vector(hint);v=b-a;d=v.length
 assert d<l1+l2+.008,('unreachable limb',globals().get('f'),globals().get('side'),d,l1+l2)
 d=max(.01,min(d,l1+l2-.0001));u=v.normalized();mid=(l1*l1-l2*l2+d*d)/(2*d)
 bend=hint-a;perp=bend-u*bend.dot(u)
 if perp.length<.001:perp=Vector((1,0,0))
 return a+u*mid+perp.normalized()*math.sqrt(max(0,l1*l1-mid*mid))

# World-space pose marks; timestamps are planned blockout seconds.
# Root argument is pelvis. Feet are ankle centres, palms have explicit contacts.
poses=[
 (0.0,(2.0,4.50,1.82),(2.14,4.52,.98),(1.86,4.52,.98),(2.78,4.42,2.55),(1.68,4.12,2.24)),
 (1.0,(2.0,4.50,1.82),(2.14,4.52,.98),(1.86,4.52,.98),(2.78,4.42,2.55),(1.68,4.12,2.24)),
 (2.0,(2.0,4.45,2.12),(2.14,4.52,1.28),(1.86,4.52,1.28),(2.78,4.42,2.55),(1.65,4.22,2.48)),
 (2.8,(2.0,4.45,2.12),(2.14,4.52,1.28),(1.86,4.52,1.28),(2.78,4.42,2.55),(1.60,4.074,2.38)),
 (3.3,(2.0,4.45,2.12),(2.14,4.52,1.28),(1.86,4.52,1.28),(2.78,4.42,2.55),(1.60,4.074,2.38)),
 (4.0,(2.0,4.30,2.58),(2.14,4.55,1.80),(1.86,3.58,2.66),(2.60,4.12,2.55),(1.68,3.80,2.60)),
 (4.8,(2.0,4.10,2.96),(2.14,4.42,2.28),(1.86,3.58,2.66),(2.43,3.95,2.96),(1.65,3.86,2.95)),
 (5.5,(2.0,3.56,3.30),(2.14,3.28,2.65),(1.86,3.58,2.66),(2.30,3.48,3.30),(1.70,3.48,3.30)),
 (6.0,(2.0,3.38,3.45),(2.14,3.24,2.66),(1.86,3.55,2.66),(2.30,3.38,3.42),(1.70,3.38,3.42)),
]
scene=bpy.context.scene;scene.frame_start=1;scene.frame_end=73;scene.render.fps=12
pose_checks=[]
for f in range(1,74):
 t=(f-1)/12
 for j in range(len(poses)-1):
  if poses[j][0]<=t<=poses[j+1][0]:break
 a,b=poses[j],poses[j+1];u=(t-a[0])/(b[0]-a[0]);u=u*u*(3-2*u)
 hip,lf,rf,lh,rh=[Vector(a[k]).lerp(Vector(b[k]),u)+Vector((0,0,.15)) for k in range(1,6)]
 girl.root.location=(hip.x,hip.y,hip.z-.88);girl.root.rotation_euler.z=math.pi
 for attr in ['location','rotation_euler']:girl.root.keyframe_insert(attr,frame=f)
 def local(p):return Vector((hip.x-p.x,hip.y-p.y,p.z-(hip.z-.88)))
 for side,foot,hand in [(-1,lf,lh),(1,rf,rh)]:
  # Facing -Y: anatomical left is world +X.
  h=hip+Vector((-side*.13,0,0));ankle=foot
  knee=ik(h,ankle,.46,.46,hip+Vector((-side*.5,-.5,.4)))
  move_segment(girl.parts[(side,'thigh')],local(h),local(knee),f)
  move_segment(girl.parts[(side,'calf')],local(knee),local(ankle),f)
  shoe=girl.parts[(side,'shoe')];shoe.location=local(ankle)+Vector((0,.07,-.05));shoe.keyframe_insert('location',frame=f)
  sh=hip+Vector((-side*.235,0,.47));elbow=ik(sh,hand,.34,.34,hip+Vector((-side*.65,-.1,.33)))
  move_segment(girl.parts[(side,'upperarm')],local(sh),local(elbow),f)
  move_segment(girl.parts[(side,'forearm')],local(elbow),local(hand),f)
  palm=girl.parts[(side,'hand')];palm.location=local(hand);palm.keyframe_insert('location',frame=f)
  if side==-1:
   girl.bag.location=local(hand)+Vector((0,-.04,.04));girl.bag.keyframe_insert('location',frame=f)
 card.location=rh+Vector((0,-.01,0));card.keyframe_insert('location',frame=f)
 screen.data.materials.clear();screen.data.materials.append(M['green'])
 pose_checks.append({'frame':f,'t':t,'pelvis':list(hip),'left_ankle':list(lf),'right_ankle':list(rf),'left_hand':list(lh),'card_center':list(card.location)})
# Camera behind the player facing -Y, slightly elevated for obstruction clearance.
bpy.ops.object.camera_add(location=(-1.2,7.8,5.1));cam=bpy.context.object;cam.name='PLAYER recovery front-left follow'
target=empty('PLAYER camera target',(1.9,4.0,2.45));cam.rotation_euler=(target.location-cam.location).to_track_quat('-Z','Y').to_euler()
cam.data.sensor_fit='HORIZONTAL';cam.data.sensor_width=36;cam.data.lens=36/(2*math.tan(math.radians(52)/2));scene.camera=cam
scene.render.engine='CYCLES';scene.cycles.samples=4;scene.cycles.use_denoising=True
scene.render.resolution_x=432;scene.render.resolution_y=768;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG';scene.world.use_nodes=True
bg=scene.world.node_tree.nodes.get('Background');bg.inputs['Color'].default_value=(.68,.78,.82,1);bg.inputs['Strength'].default_value=.7
bpy.ops.object.light_add(type='SUN',location=(4,4,12));bpy.context.object.rotation_euler=(.3,-.3,-.6);bpy.context.object.data.energy=2
scene.view_settings.view_transform='Standard';scene.view_settings.look='None';scene.view_settings.exposure=-.4
# Linear sampling prevents bezier overshoot between explicitly solved poses.
for o in bpy.data.objects:
 if o.animation_data and o.animation_data.action:
  for layer in o.animation_data.action.layers:
   for strip in layer.strips:
    for slot in o.animation_data.action.slots:
     try: curves=strip.channelbag(slot).fcurves
     except: continue
     for fc in curves:
      for kp in fc.keyframe_points:kp.interpolation='LINEAR'
scene.frame_set(35);bpy.context.view_layer.update()
assert reader.parent==bus and reader_pole.parent==bus
assert abs(contact.matrix_world.translation.z-2.53)<.001
assert contact.matrix_world.translation.y>bus['front_axle_y']
assert min((o.matrix_world @ Vector(v)).z for o in bpy.data.objects if o.name.startswith('wheel') for v in o.bound_box)>-.005
assert all('SBS' not in o.name for o in bpy.data.objects)
record={'role':'motion blockout, not final cast/look','blender_version':bpy.app.version_string,'units':'metres','forward':'+Y','driver_right':'+X','roll_axis':'+Y','roll_degrees':90,'bus_root_world':list(bus.location),'door':{'side':'left','y_bounds':[3.80,5.30],'local_z_bounds':[.625,2.68],'world_opening_plane_z':2.70,'front_axle_y':3.15},'reader':{'local':list(reader.location),'world':list(reader.matrix_world.translation),'contact_world':list(contact.matrix_world.translation),'face_normal_world':[0,1,0]},'camera':{'position':list(cam.location),'rotation_euler':list(cam.rotation_euler),'lens_mm':cam.data.lens,'sensor_fit':cam.data.sensor_fit,'sensor_width_mm':36,'horizontal_fov_degrees':52,'shift':[cam.data.shift_x,cam.data.shift_y],'size':[432,768]},'timeline':{'fps':12,'frames':[1,73],'duration_seconds':73/12,'index_mapping':'video index 0 = Blender frame 1','action_seconds':6},'events':{'pause':[0,1],'rise':[1,2],'tap':[2.8,3.3],'climb_clear':[3.3,6]},'review':{'normal_speed_reviewed':False,'cast':'unreviewed procedural proxy','facades':'neutral background; photo-derived facades supplied in separate look frames','physics':'keyed poses, not simulated fall'},'pose_samples':pose_checks}
(OUT/'blender/scene-record.json').write_text(json.dumps(record,indent=2))
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'blender/bus-exit.blend'))
frames=[1,25,35,49,59,73] if '--preview' in sys.argv else range(1,74)
for f in frames:
 scene.frame_set(f);scene.render.filepath=str(OUT/'blender/sequence'/f'{f:04d}.png');bpy.ops.render.render(write_still=True)
# Inspection angle shows full bus, front windshield, doorway and rear engine.
if '--preview' in sys.argv:
 scene.frame_set(35);cam.location=(10,14,9);cam.rotation_euler=(Vector((1.4,0,1.5))-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.lens=38
 scene.render.resolution_x=960;scene.render.resolution_y=640
 scene.render.filepath=str(OUT/'blender/geometry-overview.png');bpy.ops.render.render(write_still=True)
