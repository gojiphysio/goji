"""Refine the shared bus mesh before any image appearance pass.
Executed within build_continuity.py after both decks exist. Anchors stay fixed.
"""
def remove_prefix(*prefixes):
 for ob in list(bus.children_recursive):
  if any(ob.name==p or ob.name.startswith(p+'.') for p in prefixes):bpy.data.objects.remove(ob,do_unlink=True)
def bevel_mesh(ob,width=.035,segments=2):
 bpy.ops.object.select_all(action='DESELECT');ob.select_set(True);bpy.context.view_layer.objects.active=ob
 bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
 mod=ob.modifiers.new('authored rounded body edge','BEVEL');mod.width=width;mod.segments=segments
 mod.affect='EDGES'
 norm=ob.modifiers.new('weighted broad shading','WEIGHTED_NORMAL');norm.keep_sharp=True
 return ob
# Replace roof slab with a softly rolled roof cap; no change to top height.
roof=bpy.data.objects['roof'];roof.scale=(2.50,12,.44);roof.location.z=4.43;bevel_mesh(roof,.20,4)
remove_prefix('upper orange cantrail','upper front roof brow','front purple bumper','rear purple bumper','headlight')
# Bus faces have formed corners, not protruding box panels.
for ob in list(bus.children_recursive):
 if ob.type=='MESH' and any(ob.name.startswith(p) for p in ['front lower nose','rear bulkhead','upper front white fascia','upper front pillar','front driver corner pillar']):bevel_mesh(ob,.075,3)
# Thin fitted window gaskets surround slightly recessed glazing.
for ob in list(bus.children_recursive):
 if ob.type!='MESH' or not any(ob.name.startswith(p) for p in ['side window','upper continuous glazing','front windshield','upper front windshield','upper rear windshield']):continue
 if ob.name.startswith('upper continuous glazing'):
  ob.scale.y=11.72;ob.scale.z=1.13;ob.location.x=math.copysign(1.275,ob.location.x)
 gasket=ob.copy();gasket.data=ob.data.copy();bpy.context.collection.objects.link(gasket);gasket.name='fitted black window gasket';gasket.data.materials.clear();gasket.data.materials.append(M['black'])
 thin=min(range(3),key=lambda i:ob.scale[i]);gasket.scale=[s+(.012 if i==thin else .065) for i,s in enumerate(ob.scale)]
 # Keep glazing in front of the gasket, along the outward surface normal.
 if thin==0:gasket.location.x-=math.copysign(.022,ob.location.x)
 else:gasket.location.y-=math.copysign(.022,ob.location.y)
 bevel_mesh(gasket,.028,3);bevel_mesh(ob,.018,3)
# Cut actual wheel arches through all lower side body and livery surfaces.
body=[ob for ob in list(bus.children_recursive) if ob.type=='MESH' and (ob.name.startswith(('driver right lower side','left aft wall','left skirt','right purple skirt','purple diagonal body livery')))]
for ob in body:
 bpy.ops.object.select_all(action='DESELECT');ob.select_set(True);bpy.context.view_layer.objects.active=ob
 bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
 if 'diagonal' in ob.name:
  mod=ob.modifiers.new('paint panel thickness','SOLIDIFY');mod.thickness=.012;bpy.ops.object.modifier_apply(modifier=mod.name)
for yy in [-4.2,-2.8,3.15]:
 bpy.ops.mesh.primitive_cylinder_add(vertices=24,radius=.585,depth=3.5,location=(0,yy,.51),rotation=(0,math.pi/2,0));cutter=bpy.context.object
 for ob in body:
  bpy.context.view_layer.objects.active=ob;mod=ob.modifiers.new('cut wheel arch','BOOLEAN');mod.operation='DIFFERENCE';mod.solver='EXACT';mod.object=cutter;bpy.ops.object.modifier_apply(modifier=mod.name)
 bpy.data.objects.remove(cutter,do_unlink=True)
 # Slim shaped arch rim; wheels retain axle centres and external bounds.
 for side in [-1,1]:
  verts=[]
  for radius in [.59,.63]:
   for i in range(17):
    a=math.pi*i/16;verts.append((side*1.352,yy+radius*math.cos(a),.51+radius*math.sin(a)))
  faces=[(i,i+1,i+18,i+17) for i in range(16)]
  mesh=bpy.data.meshes.new('arch lip');mesh.from_pydata(verts,[],faces);mesh.update();ob=bpy.data.objects.new('formed wheel arch lip',mesh);bpy.context.collection.objects.link(ob);finish(ob,ob.name,'transit white' if yy>0 else 'transit deep purple',bus)
# Tyres with stepped sidewalls and inset metal hubs instead of solid black discs.
remove_prefix('wheel')
for yy in [-4.2,-2.8,3.15]:
 for side in [-1,1]:
  profile=[(1.12,.43),(1.16,.49),(1.35,.50),(1.41,.46),(1.42,.35)]
  verts=[(side*x,yy+r*math.cos(2*math.pi*i/24),.51+r*math.sin(2*math.pi*i/24)) for x,r in profile for i in range(24)]
  faces=[]
  for j in range(len(profile)-1):
   for i in range(24):faces.append((j*24+i,j*24+(i+1)%24,(j+1)*24+(i+1)%24,(j+1)*24+i))
  mesh=bpy.data.meshes.new('profiled tyre');mesh.from_pydata(verts,[],faces);mesh.update();ob=bpy.data.objects.new('profiled tyre',mesh);bpy.context.collection.objects.link(ob);finish(ob,ob.name,'tyre',bus)
  segment('wheel rim',(side*1.36,yy,.51),(side*1.425,yy,.51),.34,.34,'grey',bus,vertices=24)
  segment('wheel hub',(side*1.42,yy,.51),(side*1.44,yy,.51),.115,.115,'black',bus,vertices=12)
  for i in range(8):
   a=2*math.pi*i/8;y=yy+.245*math.cos(a);z=.51+.245*math.sin(a)
   segment('rim ventilation hole',(side*1.425,y,z),(side*1.432,y,z),.045,.045,'black',bus,vertices=8)
   y=yy+.15*math.cos(a);z=.51+.15*math.sin(a)
   segment('wheel bolt',(side*1.43,y,z),(side*1.442,y,z),.018,.018,'silver',bus,vertices=6)
# Fitted continuous bumpers, twin recessed headlights and separate indicators.
for yy in [-6.085,6.085]:
 ob=cube('formed full width bumper',(0,yy,.52),(2.46,.16,.25),'transit white' if yy>0 else 'transit deep purple',bus);bevel_mesh(ob,.065,3)
 cube('bumper rubber insert',(0,yy+math.copysign(.086,yy),.53),(2.14,.018,.085),'black',bus,bevel=.015)
for xx in [-.84,.84]:
 ob=cube('recessed twin headlight housing',(xx,6.075,.91),(.45,.06,.22),'grey',bus);bevel_mesh(ob,.025,2)
 for dx in [-.105,.105]:
  segment('headlamp chrome surround',(xx+dx,6.10,.91),(xx+dx,6.125,.91),.085,.085,'silver',bus,vertices=12)
  segment('headlamp glass lens',(xx+dx,6.125,.91),(xx+dx,6.132,.91),.065,.065,'white',bus,vertices=12)
 segment('front amber indicator',(xx,6.08,1.22),(xx,6.12,1.22),.065,.065,'orange',bus,vertices=12)
for xx in [-.86,0,.86]:cube('roof clearance marker',(xx,5.98,4.48),(.12,.045,.045),'orange',bus,bevel=.01)
# Fine body seams and service access panels, kept off the open passenger entrance.
for side in [-1,1]:
 for yy in [-5.2,-1.7,.5]:
  cube('service hatch seam',(side*1.356,yy,1.05),(.006,.008,.72),'grey',bus)
  cube('service hatch handle',(side*1.362,yy+.12,1.23),(.012,.12,.022),'black',bus)
 for lo,hi in [(-6,-4.84),(-2.16,2.50),(3.79,5.28),(5.32,6)]:
  if side<0 and lo==3.79:continue
  cube('lower body trim seam',(side*1.352,(lo+hi)/2,.72),(.007,hi-lo,.018),'grey',bus)
# Compact cab mirrors inside the already permitted side envelope.
for side in [-1,1]:
 segment('mirror arm',(side*1.25,5.83,2.46),(side*1.47,5.86,2.46),.018,.018,'black',bus)
 ob=cube('cab mirror housing',(side*1.48,5.86,2.28),(.08,.16,.33),'black',bus);bevel_mesh(ob,.025,3)
 cube('cab mirror glass',(side*1.48,5.77,2.28),(.055,.008,.27),'silver',bus)
# Add the retained swoosh above each italic wordmark in the logo local plane.
for name in ['left','right','front','rear']:
 root=bpy.data.objects['LOGO '+name]
 scale=.65 if name in ['front','rear'] else 1.0
 for idx,(points,ma) in enumerate([([(-.28,.45),(.04,.53),(.38,.49),(.12,.43)],'logo burgundy'), ([(.04,.43),(.34,.49),(.68,.42),(.42,.37)],'logo purple')]):
  mesh=bpy.data.meshes.new('logo swoosh');mesh.from_pydata([(x*scale,y*scale,0) for x,y in points],[],[(0,1,2,3)]);mesh.update();ob=bpy.data.objects.new('SOS logo swoosh',mesh);bpy.context.collection.objects.link(ob);finish(ob,ob.name,'transit white' if name=='rear' else ma,root)
bus['detail_revision']='7: rounded roof/body, fitted gaskets, cut arches, profiled wheels/rims, lamp housings, bumpers, panel seams, mirrors'


# Keep the complete front logo and swoosh below the lower windscreen.
front_logo=bpy.data.objects["LOGO front"];front_logo.location.z=1.20;front_logo.scale=(.85,.85,.85)
