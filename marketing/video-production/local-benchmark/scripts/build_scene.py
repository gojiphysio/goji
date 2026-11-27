"""Original procedural low-poly taxi continuity stage; Blender 5.x, no external assets."""
import bpy, math, random, json, sys
from pathlib import Path
from mathutils import Vector
random.seed(21)
OUT=Path(__file__).resolve().parents[1]/'staging'
OUT.mkdir(parents=True,exist_ok=True)
PREVIEW='--preview' in sys.argv
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
def smooth(a,b,t):
 t=max(0,min(1,t));return a+(b-a)*t*t*(3-2*t)
# Singapore-like set, original illustrative geography.
cube('road',(0,4,-.16),(18,40,.25),'road')
cube('raised footpath',(4.6,5,-.025),(5,40,.30),'concrete')
for y in range(-15,25,2):
 cube('kerb',(2.12,y,.1),(.2,1.96,.24),'cream')
 cube('yellow road edge',(1.85,y,-.025),(.06,1.1,.008),'yellow')
for y in range(-15,28,4):cube('lane dash',(-2.5,y,-.025),(.10,2,.01),'cream')
for x in [-12,-8]:
 for y in [0,9,18]:
  cube('HDB block',(x,y,5.5),(3,7,11),'cream')
  for z in range(1,11,2):
   for yy in [-2,0,2]:cube('window',(x+1.51,y+yy,z),(.015,.9,.9),'teal')
for y in [9,17]:
 segment('tree trunk',(5,y,.1),(5,y,4.8),.24,.13,'trunk',vertices=7)
 for i in range(6):
  a=i*math.pi/3;ico('tropical crown',(5+math.cos(a)*1.4,y+math.sin(a)*1.4,5+random.random()),(1.65,1.7,1),'green' if i%2 else 'leaf',sub=1)
cube('mall timber wall',(6.8,7,2),(1.3,10,4),'cream')
cube('GOJI doorway',(6.12,6.4,1.5),(.06,1.9,2.8),'teal')
# Sign on a face towards camera (+x).
sign=text('Goji sign','GOJI',(6.05,6.4,3.2),.5,'maroon',(math.pi/2,0,-math.pi/2))
for y in [2.4,10.4]:cube('shelter post',(3.3,y,2),(.12,.12,4),'teal')
cube('shelter canopy',(4.6,6.4,4.05),(3.8,10,.15),'concrete')
# Yellow entry beacon is geometry, no invented UI.
bpy.ops.mesh.primitive_cone_add(vertices=12,radius1=.5,radius2=.08,depth=1.8,location=(5.4,6.4,1.0));finish(bpy.context.object,'yellow mission beacon','yellow')
segment('lamp post',(1.5,5,.1),(1.5,5,5.5),.07,.06,'silver')
segment('lamp arm',(1.5,5,5.5),(.2,5,5.5),.055,.055,'silver');cube('lamp',(.1,5,5.48),(.5,.25,.12),'cream')
# Four-door right-hand-drive taxi with genuine articulated front-right door.
car=empty('blue four-door taxi')
cube('chassis',(0,0,.48),(1.85,4.45,.43),'blue',car,bevel=.13)
cube('hood',(0,1.5,.82),(1.8,1.25,.26),'blue',car,bevel=.08)
cube('trunk',(0,-1.7,.82),(1.8,.92,.24),'blue',car,bevel=.06)
cube('roof',(0,-.13,1.59),(1.51,1.94,.12),'blue',car,bevel=.06)
for x in [-.91,.91]:
 for y in [-1.45,1.45]:
  o=segment('tyre',(x-.12,y,.36),(x+.12,y,.36),.34,.34,'tyre',car,vertices=12)
  segment('hubcap',(x-.13,y,.36),(x+.13,y,.36),.18,.18,'silver',car,vertices=10)
 for y in [-1.12,-.13,.92]:segment('pillar',(x*.86,y,.9),(x*.78,y*.90,1.55),.043,.04,'blue',car)
# Front and rear windshield planes keep the cabin a closed four-door shell.
for name,verts in [('windshield',[(-.85,1.12,.99),(.85,1.12,.99),(.72,.84,1.54),(-.72,.84,1.54)]),('rear glass',[(-.85,-1.45,.99),(.85,-1.45,.99),(.72,-1.10,1.54),(-.72,-1.10,1.54)])]:
 mesh=bpy.data.meshes.new(name);mesh.from_pydata(verts,[],[(0,1,2,3)]);o=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(o);finish(o,name,'glass',car)
# Floor and visible seats, no enclosing solid cabin cube.
cube('cabin floor',(0,-.05,.48),(1.65,2.3,.1),'navy',car)
for x in [-.42,.42]:
 for y in [-.72,.36]:
  cube('seat cushion',(x,y,.68),(.53,.47,.15),'navy',car,bevel=.05)
  cube('seat back',(x,y-.21,.99),(.53,.13,.63),'navy',car,bevel=.07)
cube('dashboard',(0,.84,1.04),(1.55,.28,.2),'navy',car)
bpy.ops.mesh.primitive_torus_add(major_radius=.17,minor_radius=.025,major_segments=12,minor_segments=6,location=(.43,.70,1.17),rotation=(math.radians(65),0,0));finish(bpy.context.object,'right-side steering wheel','black',car)
for x in [-.92,.92]:
 cube('rear door',(x,-.70,.87),(.065,.99,.50),'blue',car)
 cube('rear window',(x*.93,-.69,1.30),(.026,.85,.31),'glass',car)
 cube('rear handle',(x*1.04,-1.01,1.02),(.025,.15,.035),'silver',car)
 if x<0:
  cube('far front door',(x,.4,.87),(.065,1.1,.5),'blue',car)
  cube('far front window',(x*.93,.39,1.3),(.025,.91,.31),'glass',car)
# Hinge at A-pillar; door local -Y extends behind hinge.
door=empty('front right hinge',(.94,.95,.9),car)
cube('front driver door',(0,-.55,-.03),(.07,1.1,.48),'blue',door)
cube('driver window',(0,-.54,.37),(.026,.94,.30),'glass',door)
for yy in [-1.07,-.03]:segment('door window frame',(0,yy,.2),(0,yy,.56),.022,.022,'blue',door)
segment('door upper frame',(0,-1.07,.56),(0,-.03,.56),.023,.023,'blue',door)
cube('driver handle',(.05,-.92,.10),(.04,.16,.035),'silver',door)
cube('single door mirror',(.18,-.06,.27),(.25,.16,.12),'blue',door,bevel=.03)
for x in [-.57,.57]:
 cube('headlight',(x,2.235,.78),(.40,.02,.16),'white',car)
 cube('tail light',(x,-2.23,.76),(.37,.02,.17),'red',car)
cube('taxi roof sign',(0,-.10,1.78),(.48,.25,.19),'white',car,bevel=.025)
# all characters share same original mesh/detail language.
girl=Person('GG01',hair='pony');driver=Person('DRIVER01','grey','skin2','short');therapist=Person('GP01','black','skin2','bob');npc=Person('NPC01','orange','skin2','short')
# 8 seconds, with first 5 seconds available as native-window comparison.
scene=bpy.context.scene;scene.frame_start=1;scene.frame_end=193;scene.render.fps=24
for f in range(1,194):
 t=(f-1)/24
 # Door handover: girl opens door, driver exits, both remain separate.
 op=smooth(0,1,(t-.3)/1.0)
 door.rotation_euler.z=math.radians(72)*op;door.keyframe_insert('rotation_euler',frame=f)
 x=1.55+.85*op; y=-.4
 angle=math.pi/2
 theta=door.rotation_euler.z
 hx=.94+.05*math.cos(theta)+.92*math.sin(theta)
 hy=.95+.05*math.sin(theta)-.92*math.cos(theta)
 gz=.12*op
 reach=(hy-y,-(hx-x),1.0-gz) if t<3.6 else None
 girl.pose(f,(x,y,gz),angle=angle,reach=reach)
 exit=smooth(0,1,(t-1.3)/1.8)
 dx=smooth(.43,1.65,exit);dy=smooth(.35,.15,exit);dz=smooth(-.10,0,exit)
 walk=0
 if t>3.1:
  dy=.15+(t-3.1)*.36;dx=1.65+(t-3.1)*.06;walk=(t-3.1)*6.5
 driver.pose(f,(dx,dy,dz),angle=0,walk=walk,seated=1-exit)
 therapist.pose(f,(5.25,5.3,.12),angle=math.pi*.80,reach=(.37,.20,1.34) if t>5.5 else None)
 npc.pose(f,(3.5,8.0-t*.45,.12),angle=math.pi,walk=t*6)
# Calibrated static elevated rear-right view; camera never moves.
bpy.ops.object.camera_add(location=(7,-10,5));cam=bpy.context.object;cam.name='locked rear-right camera'
cam.rotation_euler=(Vector((1.55,2.0,1.1))-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.type='PERSP';cam.data.lens=30;scene.camera=cam
scene.render.engine='CYCLES';scene.cycles.samples=12;scene.cycles.use_denoising=True
# CPU render avoids concurrent model GPU contention; use modest draft canvas.
scene.render.resolution_x=576;scene.render.resolution_y=1024;scene.render.resolution_percentage=100
scene.world.color=(.38,.42,.38)
scene.world.use_nodes=True;bg=scene.world.node_tree.nodes.get('Background');bg.inputs['Color'].default_value=(.68,.78,.82,1);bg.inputs['Strength'].default_value=.55
bpy.ops.object.light_add(type='SUN',location=(3,-4,12));sun=bpy.context.object;sun.rotation_euler=(.45,-.4,-.55);sun.data.energy=2.2;sun.data.angle=.08
scene.view_settings.view_transform='Standard';scene.view_settings.look='Medium High Contrast' if 'Medium High Contrast' in [] else 'None';scene.view_settings.exposure=-.4
scene.render.image_settings.file_format='PNG';scene.render.film_transparent=False
scene.frame_set(1);bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'taxi-stage.blend'))
frames=[1,25,49,73,97,121,169,193] if PREVIEW else range(1,194)
for f in frames:
 scene.frame_set(f);scene.render.filepath=str(OUT/f'frame-{f:04d}.png');bpy.ops.render.render(write_still=True)
(OUT/'stage.json').write_text(json.dumps({'fps':24,'frames':193,'size':[576,1024],'seed':21,'camera':{'position':list(cam.location),'target':[1.55,2.0,1.1],'lens_mm':cam.data.lens,'sensor_width_mm':cam.data.sensor_width,'sensor_height_mm':cam.data.sensor_height,'sensor_fit':cam.data.sensor_fit,'projection':cam.data.type,'rotation_euler':list(cam.rotation_euler),'shift':[cam.data.shift_x,cam.data.shift_y],'pixel_aspect':[scene.render.pixel_aspect_x,scene.render.pixel_aspect_y]},'events':{'door_open':[.3,1.3],'driver_exit':[1.3,3.1],'driver_walk':[3.1,8],'girl_release':[3.6,3.6]},'note':'Original procedural blockout, illustrative Singapore geography; likeness approximations, not approved character replacements'},indent=2))
