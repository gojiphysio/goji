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
for n,c in {'blue':(.025,.24,.52),'navy':(.02,.07,.12),'glass':(.065,.075,.075),'purple':(.26,.08,.36),'tyre':(.025,.029,.028),'silver':(.5,.53,.51),'maroon':(.29,.025,.055),'skin':(.57,.32,.14),'skin2':(.69,.44,.25),'hair':(.022,.019,.016),'white':(.83,.81,.71),'gold':(.81,.55,.13),'road':(.25,.27,.25),'concrete':(.54,.51,.42),'cream':(.74,.69,.51),'green':(.15,.24,.08),'leaf':(.27,.35,.1),'trunk':(.23,.16,.08),'teal':(.06,.24,.21),'yellow':(.93,.62,.035),'orange':(.58,.24,.055),'black':(.025,.027,.025),'red':(.47,.08,.055),'grey':(.28,.30,.29)}.items():mat(n,c)
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
    wrist=reach;elbow=((shoulder[0]+wrist[0])*.5,(shoulder[1]+wrist[1])*.5-.09,(shoulder[2]+wrist[2])*.5)
   move_segment(self.parts[(side,'upperarm')],shoulder,elbow,f);move_segment(self.parts[(side,'forearm')],elbow,wrist,f)
   hand=self.parts[(side,'hand')];hand.location=(wrist[0],wrist[1],wrist[2]-.035);hand.keyframe_insert('location',frame=f)
   if side==-1 and self.bag:
    self.bag.location=wrist;self.bag.keyframe_insert('location',frame=f)
# +Y is vehicle forward; +X is driver's right; local Z is up.
bus=empty('BUS-SOS-01 chassis transform')
bus['forward_axis']='+Y';bus['driver_side']='+X';bus['passenger_side']='-X'
bus['door_interval_y']=[3.80,5.30];bus['front_axle_y']=3.15
# Open shell, never a solid cube around the actor.
cube('floor',(0,0,.48),(2.50,12,.18),'black',bus)
cube('roof',(0,0,3.05),(2.54,12,.20),'red',bus)
cube('driver right lower side',(1.25,0,1.10),(.10,12,1.10),'white',bus)
cube('driver side header',(1.25,0,2.80),(.10,12,.30),'red',bus)
cube('right purple skirt',(1.31,0,.83),(.035,12,.55),'purple',bus)
# Entire passenger-side wall stops at the actual FRONT passenger entrance.
for name,lo,hi in [('aft wall',-6,3.80),('front corner',5.30,6)]:
 cube('left '+name,(-1.25,(lo+hi)/2,1.55),(.10,hi-lo,2.0),'white',bus)
 cube('left skirt '+name,(-1.31,(lo+hi)/2,.83),(.035,hi-lo,.55),'purple',bus)
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
cube('right driver seat',(.64,5.15,.92),(.6,.7,.55),'navy',bus)
cube('driver seat back',(.64,4.81,1.47),(.6,.15,.8),'navy',bus)
cube('front dash',(0,5.80,1.42),(2.15,.30,.35),'navy',bus)
for y in [-4.8,-3,-1.2,.6,2.3]:
 for x in [-.65,.65]:cube('passenger seat',(x,y,.92),(.65,.6,.45),'navy',bus)
reader_pole=segment('front entrance reader pole',(-1.08,3.95,.58),(-1.08,3.95,2.74),.035,.035,'yellow',bus)
reader=cube('READER-01 at front door aft jamb',(-1.08,3.95,1.60),(.27,.16,.35),'black',bus,bevel=.025)
reader['parent_rule']='Fixed to front passenger doorway; rotates with chassis'
screen=cube('reader green display',(-1.08,4.036,1.60),(.22,.016,.27),'green',bus)
contact=empty('CARD CONTACT surface',(-1.08,4.062,1.60),bus)

# Shared staged set and shot cameras follow.
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

mat('reader lit green',(.10,.65,.035))
screen.data.materials.clear();screen.data.materials.append(M['reader lit green'])
# One bus asset for every panel. All body materials and text stay in local space.
# Underbody is charcoal; the purple skirt is bodywork, never a blue floor plate.
for x in [-.85,.85]:
 cube('front purple bumper',(x,6.08,.60),(.80,.08,.28),'purple',bus)
 cube('rear purple bumper',(x,-6.10,.60),(.80,.08,.28),'purple',bus)
for y in [-3.65,3.15]:
 segment('steel axle',(-1.35,y,.51),(1.35,y,.51),.09,.09,'black',bus)
for x in [-.72,.72]:cube('chassis rail',(x,0,.32),(.14,10.5,.20),'black',bus)
for name,p,rot,size in [('left',(-1.33,-.8,1.42),(math.pi/2,0,-math.pi/2),.38),('right',(1.33,-.8,1.42),(math.pi/2,0,math.pi/2),.38),('rear',(0,-6.11,1.80),(math.pi/2,0,0),.32),('front',(0,6.11,1.35),(math.pi/2,0,math.pi),.30)]:
 logo=empty('LOGO '+name,p,bus);logo.rotation_euler=rot
 for word,dx,color in [('SOS',-.72,'red'),('Transit',.13,'purple')]:
  o=text(name+' '+word,word,(0,0,0),size,color,(0,0,0));o.parent=logo;o.location=(dx,0,0);o.rotation_euler=(0,0,0);o.data.align_x='LEFT';o.data.shear=.15
# Compact driver's opening directly beside the windscreen. All dimensions local.
DRIVER_WINDOW={'centre_y':5.15,'width_y':1.10,'height_z':.82,'bottom_z':1.78,'front_gap_to_nose':.30}
driver_pane=cube('intact driver side glass',(1.31,5.15,2.19),(.04,1.10,.82),'glass',bus)
for y in [4.60,5.70]:cube('driver window jamb',(1.3,y,2.19),(.1,.075,.94),'black',bus)
for z in [1.74,2.64]:cube('driver window horizontal frame',(1.30,5.15,z),(.12,1.18,.08),'black',bus)
cube('cab panel behind driver window',(1.25,4.09,2.15),(.10,.94,1.0),'white',bus)
cube('front driver corner pillar',(1.25,5.88,2.15),(.10,.24,1.0),'white',bus)
cube('driver sill infill',(1.25,5.15,1.695),(.10,1.18,.09),'white',bus)

# User-provided double-decker photo: palette/livery reference on the approved single-decker.
# These are local materials and paint polygons, not mirrored screen-space edits.
mat('transit orange red',(.72,.045,.018))
mat('transit deep purple',(.22,.025,.13))
mat('transit white',(.82,.83,.78))
mat('transit dark glazing',(.025,.038,.035))
mat('logo burgundy',(.35,.015,.025))
mat('logo purple',(.17,.025,.13))
paint={'red':'transit orange red','purple':'transit deep purple','white':'transit white','glass':'transit dark glazing'}
for o in bus.children_recursive:
 if o.type not in ['MESH','FONT']:continue
 for slot in o.material_slots:
  if slot.material and slot.material.name in paint:slot.material=M[paint[slot.material.name]]
# Remove the uniform purple side skirt: white forward with a diagonal purple aft section.
for o in list(bus.children_recursive):
 if 'skirt' in o.name or o.name=='front purple bumper' or o.name.startswith('front purple bumper.'):
  o.data.materials.clear();o.data.materials.append(M['transit white'])
def paint_face(name,x,yz,material):
 verts=[(x,y,z) for y,z in yz];mesh=bpy.data.meshes.new(name);mesh.from_pydata(verts,[],[tuple(range(len(verts)))]);mesh.update()
 o=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(o);finish(o,name,material,bus);return o
for x in [-1.345,1.345]:
 paint_face('purple diagonal body livery',x,[(-6,.56),(3.40,.56),(1.0,1.65),(-6,1.65)],'transit deep purple')
 cube('orange red upper cantrail',(x,0,2.84),(.025,12,.30),'transit orange red',bus)
# The rear is orange-red above purple; white italic lettering sits on the purple field.
bpy.data.objects['rear bulkhead'].data.materials.clear();bpy.data.objects['rear bulkhead'].data.materials.append(M['transit orange red'])
cube('purple rear body panel',(0,-6.076,1.15),(2.50,.015,1.70),'transit deep purple',bus)
for side,y in [('left',2.65),('right',2.30)]:bpy.data.objects['LOGO '+side].location.y=y
for o in bus.children_recursive:
 if o.type=='FONT':
  o.data.materials.clear()
  o.data.materials.append(M['transit white'] if o.name.startswith('rear ') else M['logo burgundy' if o.name.endswith('SOS') else 'logo purple'])
bus['livery_reference']='User-supplied double-decker photograph; colour and diagonal paint adapted to single-decker; SOS branding retained.'

# Fixed world: northbound +Y uses WEST/left lane x<0. No camera-based geometry.
CURB=-5.2;PARK=(-3.65,-28,0);WRECK=(-5.1,0,1.45)
cube('two-way asphalt',(0,10,-.12),(10.4,100,.24),'road')
cube('west sidewalk',(-7.6,10,.01),(4.8,100,.22),'concrete')
cube('east sidewalk',(7.1,10,.01),(3.8,100,.22),'concrete')
for y in range(-40,50,3):
 cube('centre line',(0,y,.014),(.10,1.5,.02),'white')
 for x in [-5.04,-4.88,4.88,5.04]:cube('yellow curb line',(x,y,.016),(.055,2.95,.02),'yellow')
for x in [-5.3,5.3]:
 for y in range(-40,50):cube('kerb block',(x,y,.10),(.18,.96,.22),'concrete')
def arrow(x,y,forward):
 root=empty('lane direction arrow',(x,y,.025));root.rotation_euler.z=0 if forward else math.pi
 cube('arrow shaft',(0,-.5,0),(.12,1.4,.012),'white',root)
 for sign in [-1,1]:
  o=cube('arrow head',(sign*.20,.12,0),(.12,.7,.012),'white',root);o.rotation_euler.z=sign*.65
for y in [-21,-11,15,28]:arrow(-2.6,y,True);arrow(2.6,y,False)

# Photo-derived architectural cues; street arrangement is fictional, fixed across views.
cube('Lentor dark cladding',(-10.2,10,4.0),(.7,62,7.8),'grey')
for y in range(-20,41):cube('vertical cladding rib',(-9.82,y,5.1),(.035,.045,3.8),'black')
for y in range(-19,40,2):
 cube('shop glazing',(-9.79,y,1.7),(.05,1.88,2.9),'glass')
 cube('shop mullion',(-9.70,y+1,1.7),(.10,.07,3.1),'black')
for y in [-9,7,24]:
 cube('balcony tower',(-13,y,19),(7,11,27),'grey')
 for z in range(8,32,2):
  cube('balcony slab',(-9.25,y,z),(.75,11.3,.16),'concrete')
  for yy in range(y-5,y+6,2):cube('tower window',(-9.45,yy,z+.8),(.05,1.5,1.35),'glass')
text('LENTOR MODERN fixed sign','LENTOR MODERN',(-9.72,1.5,5.1),.65,'white',(math.pi/2,0,math.pi/2))
cube('silver canopy roof',(-7.75,4.6,3.65),(4.9,17,.14),'silver')
for y in [-3,0,3,9,12]:
 cube('canopy post',(-5.62,y,1.87),(.14,.14,3.54),'silver')
 cube('canopy beam',(-7.75,y,3.51),(4.9,.12,.22),'silver')
bent=[]
for a,b in [((-5.62,6.2,.12),(-5.62,6.2,1.05)),((-5.62,6.2,1.05),(-4.72,6.08,3.54))]:
 bent.append(segment('damaged canopy post',a,b,.09,.09,'silver',vertices=4))
for y in [-1.5,1.5,4.5,7.5,10.5]:
 cube('bollard',(-6.1,y,.65),(.16,.16,1.1),'silver')
 cube('chevron yellow face',(-5.99,y,.99),(.025,.20,.32),'yellow')
 o=cube('chevron black stroke',(-5.97,y,1.0),(.02,.055,.22),'black');o.rotation_euler.x=.6
cube('fixed green bin',(-5.95,0,.65),(.54,.54,1.1),'teal')
for i in range(10):
 cube('fixed crash debris',(-5.1+(i%3)*.21,6.3+(i//3)*.19,.14),(.12,.18,.045),'glass').rotation_euler.z=i*.7
for y in [-16,18,35]:
 segment('tree trunk',(-7.7,y,.12),(-7.7,y,5.8),.22,.14,'trunk')
 for dx,dy,dz in [(0,0,6),(-.8,0,5.8),(.8,.5,6.3)]:ico('tree crown',(-7.7+dx,y+dy,dz),(2.0,2.2,1.8),'leaf',sub=2)

# Separate original neighbourhood bus stop, fixed at y=-28 for04/05.
cube('neighbourhood shelter roof',(-7.4,-27,3.25),(4.0,13,.16),'silver')
for y in [-33,-29,-25,-21]:cube('neighbourhood shelter post',(-6.0,y,1.68),(.13,.13,3.2),'silver')
cube('neighbourhood green bin',(-6.4,-23,.65),(.54,.54,1.1),'teal')
cube('neighbourhood HDB',(-13,-28,10),(5,16,20),'cream')
for y in range(-35,-20,2):
 for z in range(2,20,3):cube('HDB window',(-10.45,y,z),(.06,1.4,1.6),'glass')

# Reuse the validated exit pose in the new world by ONE translation.
exit_root=empty('EXIT world offset',(WRECK[0],0,0));girl.root.parent=exit_root;card.parent=exit_root
approach=Person('GG04 approach proxy');approach.pose(1,(-5.85,-22.6,.13),-math.pi/2,walk=.5)
takeover=Person('GG05 takeover proxy');takeover.pose(1,(-2.02,-22.85,0),math.pi/2,reach=(.1,.35,1.77))
driver=Person('DRIVER purple proxy',outfit='purple',hair='short');driver.pose(1,(-2.72,-22.85,.63),-math.pi/2,seated=1)
depart=Person('GG09 departure proxy');depart.pose(1,(-6.3,5.4,.13),0,walk=.3)
def descendants(root):return [root]+list(root.children_recursive)
groups={'04':descendants(approach.root),'05':descendants(takeover.root)+descendants(driver.root),'08':descendants(girl.root)+[card],'09':descendants(depart.root)}
scene.frame_start=1;scene.frame_end=90
scene.render.engine='CYCLES';scene.cycles.samples=16;scene.cycles.use_denoising=True
scene.render.resolution_x=540;scene.render.resolution_y=960;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG';scene.world.use_nodes=True
scene.world.node_tree.nodes.get('Background').inputs['Color'].default_value=(.59,.73,.79,1)
scene.world.node_tree.nodes.get('Background').inputs['Strength'].default_value=1.0
bpy.ops.object.light_add(type='SUN',location=(5,0,12));sun=bpy.context.object;sun.rotation_euler=(.3,-.3,-.6);sun.data.energy=1.6;sun.data.angle=.15
scene.view_settings.view_transform='Standard';scene.view_settings.look='None';scene.view_settings.exposure=0
police=[]
for name,p,c,e in [('offscreen blue pursuer',(-6,-26,1.6),(.07,.16,1),6000),('offscreen red pursuer',(1,-29,1.6),(1,.025,.01),3500)]:
 bpy.ops.object.light_add(type='POINT',location=p);o=bpy.context.object;o.name=name;o.data.color=c;o.data.energy=e;o.data.shadow_soft_size=3;police.append(o)
shots=[
 ('04',1,PARK,0,(-8.2,-18.5,2.7),(-4.3,-24.8,1.4),52),
 ('05',10,PARK,0,(1.0,-20,2.8),(-2.85,-22.85,1.4),49),
 ('06',20,(-3.65,-12,0),0,(-3.65,-24,4.5),(-3.65,-10,1.8),52),
 ('07',30,WRECK,90,(-1.7,-13,6.0),(-3.5,0,1.45),52),
 ('08',35,WRECK,90,(-5.05,9.0,5.6),(-3.2,4.0,2.45),52),
 ('09',80,WRECK,90,(-6.7,1.3,2.0),(-6.1,5.4,1.25),52),
]
record={'role':'direct Blender continuity proof; proxy cast, not final appearance','world':{'forward':'+Y','road_bounds_x':[-5.2,5.2],'centreline_x':0,'northbound_lane':'x<0','mall_and_passenger_curb':'west, x< -5.2','bus_driver_side':'+X','bus_passenger_side':'-X'},'bus_materials':{'roof':'orange-red','body':'white forward with purple diagonal aft panels','skirt':'deep purple aft / white forward','rear':'orange-red upper / deep-purple lower / white SOS Transit text','floor_and_chassis':'charcoal black','windows':'dark neutral glazing'},'driver_window':DRIVER_WINDOW,'shots':[]}
for sid,f,pos,roll,cp,target,hfov in shots:
 scene.frame_set(f);bus.location=pos;bus.rotation_euler=(0,math.radians(roll),0)
 for prop in ['location','rotation_euler']:bus.keyframe_insert(prop,frame=f)
 for group,objects in groups.items():
  for o in objects:o.hide_render=group!=sid;o.keyframe_insert('hide_render',frame=f)
 driver_pane.hide_render=sid!='04';driver_pane.keyframe_insert('hide_render',frame=f)
 for o in police:o.hide_render=sid!='06';o.keyframe_insert('hide_render',frame=f)
 bpy.ops.object.camera_add(location=cp);cam=bpy.context.object;cam.name='SHOT '+sid+' locked camera'
 aim=empty('SHOT '+sid+' target',target);cam.rotation_euler=(aim.location-cam.location).to_track_quat('-Z','Y').to_euler()
 cam.data.sensor_fit='HORIZONTAL';cam.data.sensor_width=36;cam.data.lens=36/(2*math.tan(math.radians(hfov)/2));scene.camera=cam
 marker=scene.timeline_markers.new('SHOT '+sid,frame=f);marker.camera=cam
 bpy.context.view_layer.update()
 matrix=[[round(v,6) for v in row] for row in bus.matrix_world]
 points=[o.matrix_world @ Vector(v) for o in bus.children_recursive if o.type=='MESH' for v in o.bound_box]
 bounds={'min':[min(p[i] for p in points) for i in range(3)],'max':[max(p[i] for p in points) for i in range(3)]}
 assert bounds['max'][0]<0,('wrong lane',sid,bounds)
 assert bounds['min'][0]>=CURB-.02,('curb intrusion',sid,bounds)
 record['shots'].append({'id':sid,'frame':f,'bus_matrix_world':matrix,'matrix_determinant':round(bus.matrix_world.determinant(),6),'forward_world':list(bus.matrix_world.to_3x3()@Vector((0,1,0))),'bus_bounds':bounds,'front_world':list(bus.matrix_world@Vector((0,6.1,1))),'rear_world':list(bus.matrix_world@Vector((0,-6.1,1))),'camera':{'position':list(cam.location),'rotation':list(cam.rotation_euler),'horizontal_fov_degrees':hfov,'lens_mm':cam.data.lens,'sensor_fit':cam.data.sensor_fit,'size':[540,960]},'reader_world':list(reader.matrix_world.translation)})
 scene.render.filepath=str(OUT/'frames'/f'{sid}-direct.png');bpy.ops.render.render(write_still=True)
# Snapshot transitions are CONSTANT; this is a staged board, not a crash animation.
for o in [bus,driver_pane]+police+[o for a in groups.values() for o in a]:
 if o.animation_data and o.animation_data.action:
  for layer in o.animation_data.action.layers:
   for strip in layer.strips:
    for slot in o.animation_data.action.slots:
     try:curves=strip.channelbag(slot).fcurves
     except:continue
     for fc in curves:
      if fc.data_path in ['hide_render','location','rotation_euler'] and (o==bus or fc.data_path=='hide_render'):
       for kp in fc.keyframe_points:kp.interpolation='CONSTANT'
assert record['shots'][0]['bus_matrix_world']==record['shots'][1]['bus_matrix_world']
assert record['shots'][3]['bus_matrix_world']==record['shots'][4]['bus_matrix_world']==record['shots'][5]['bus_matrix_world']
assert reader.parent==bus and reader_pole.parent==bus
record['checks']={'04_05_same_bus_transform':True,'07_08_09_same_bus_transform':True,'all_bus_bounds_in_left_lane':True,'reader_chassis_parent':True,'one_shared_livery_mesh':True,'positive_determinant_no_mirroring':all(s['matrix_determinant']>0 for s in record['shots']),'new_motion_animation':False}
(OUT/'blender/continuity-record.json').write_text(json.dumps(record,indent=2))
scene.frame_set(35);scene.camera=bpy.data.objects['SHOT 08 locked camera']
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'blender/continuity-master.blend'))
# Plan view is a separate review aid, never an outdoor story camera.
scene.timeline_markers.clear()
for sid,f in [('parked',1),('wreck',30)]:
 scene.frame_set(f);bpy.ops.object.camera_add(location=(-2,-28 if sid=='parked' else 1,35));cam=bpy.context.object;cam.rotation_euler=(0,0,0);cam.data.type='ORTHO';cam.data.ortho_scale=23;scene.camera=cam
 scene.render.resolution_x=900;scene.render.resolution_y=900;scene.render.filepath=str(OUT/'frames'/f'plan-{sid}.png');bpy.ops.render.render(write_still=True)
