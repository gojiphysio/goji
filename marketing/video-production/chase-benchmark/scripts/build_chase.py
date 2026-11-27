"""Frozen five-second chase layout. Run with Blender --background --python.

Original illustrative geometry, not imported GTA assets or approved character meshes.
--preview renders six anchors; --all renders all 121 frames. CPU Cycles avoids
contending with model inference. Source frame 1 = video index 0 = t=0.
"""
import bpy
import json
import math
import random
import sys
from pathlib import Path
from mathutils import Vector

OUT = Path(__file__).resolve().parents[1] / 'staging'
OUT.mkdir(parents=True, exist_ok=True)
(OUT / 'frames').mkdir(exist_ok=True)
random.seed(1017)
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
M = {}

def material(name, color, noise=False):
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*color, 1)
    m.use_nodes = True
    bs = m.node_tree.nodes.get('Principled BSDF')
    bs.inputs['Base Color'].default_value = (*color, 1)
    bs.inputs['Roughness'].default_value = .88
    if noise:
        tex = m.node_tree.nodes.new('ShaderNodeTexNoise')
        tex.inputs['Scale'].default_value = 25
        tex.inputs['Detail'].default_value = 1
        ramp = m.node_tree.nodes.new('ShaderNodeValToRGB')
        ramp.color_ramp.elements[0].color = tuple(c*.72 for c in color)+(1,)
        ramp.color_ramp.elements[1].color = tuple(min(1,c*1.15) for c in color)+(1,)
        m.node_tree.links.new(tex.outputs['Fac'], ramp.inputs[0])
        m.node_tree.links.new(ramp.outputs[0], bs.inputs['Base Color'])
    M[name] = m

for n,c in {'blue':(.018,.19,.45),'silver':(.45,.47,.45),'white':(.71,.72,.66),
    'glass':(.07,.14,.14),'black':(.022,.025,.023),'road':(.27,.28,.25),
    'concrete':(.44,.45,.39),'hdb':(.48,.5,.46),'window':(.11,.18,.18),
    'leaves':(.15,.26,.07),'leaves2':(.22,.32,.09),'bark':(.18,.13,.08),
    'skin':(.53,.30,.15),'maroon':(.27,.024,.048),'red':(.6,.045,.018),
    'amber':(.92,.32,.025),'plate':(.85,.57,.045)}.items():
    material(n,c,n in ['road','concrete','hdb','leaves','leaves2','bark'])

def link(o, name, mat, parent=None):
    o.name = name
    o.data.materials.append(M[mat])
    o.parent = parent
    return o

def box(name, loc, scale, mat, parent=None, bevel=0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o = link(bpy.context.object,name,mat,parent)
    o.scale = scale
    if bevel:
        bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
        mod=o.modifiers.new('one-segment corners','BEVEL'); mod.width=bevel; mod.segments=1
    return o

def mesh(name, verts, faces, mat, parent=None):
    m=bpy.data.meshes.new(name); m.from_pydata(verts,[],faces); m.update()
    o=bpy.data.objects.new(name,m); bpy.context.collection.objects.link(o)
    return link(o,name,mat,parent)

def empty(name):
    o=bpy.data.objects.new(name,None); bpy.context.collection.objects.link(o); return o

def rod(name, a, b, radius, mat, parent=None, vertices=8):
    a,b=Vector(a),Vector(b)
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices,radius=radius,depth=(b-a).length,location=(a+b)/2)
    o=link(bpy.context.object,name,mat,parent)
    o.rotation_euler=(b-a).to_track_quat('Z','Y').to_euler(); return o

def sphere(name, loc, scale, mat, parent=None):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=10,ring_count=6,radius=1,location=loc)
    o=link(bpy.context.object,name,mat,parent);o.scale=scale;return o

def label(name, text, loc, size, mat, parent, rot=(math.pi/2,0,0)):
    bpy.ops.object.text_add(location=loc,rotation=rot)
    o=link(bpy.context.object,name,mat,parent);o.data.body=text;o.data.size=size
    o.data.align_x='CENTER';return o

def car(name, paint, taxi=False, van=False):
    root=empty(name)
    box(name+' lower body',(0,0,.66),(1.85,4.5,.62),paint,root,.14)
    box(name+' bonnet',(0,1.55,1),(1.78,1.34,.15),paint,root,.07)
    box(name+' boot',(0,-1.69,1.01),(1.79,.94,.2),paint,root,.05)
    if van:
        box('van cargo body',(0,-.5,1.5),(1.89,3,1.8),paint,root,.1)
        box('van rear seam',(0,-2.01,1.6),(.02,.02,1.5),'black',root)
        for x in [-.48,.48]:box('van rear window',(x,-2.025,1.95),(.7,.02,.47),'glass',root)
    else:
        # Sloped glazed cabin, separate rails and real seats. Rear glass is open in
        # the layout so the seated driver remains an observable motion-guide object.
        for x in [-1,1]:
            rod('rear pillar',(x*.85,-1.3,1.04),(x*.71,-.65,1.68),.047,paint,root)
            rod('front pillar',(x*.85,.94,1.04),(x*.71,.55,1.68),.047,paint,root)
            rod('B pillar',(x*.87,-.1,1.04),(x*.73,-.1,1.68),.032,'black',root)
            box('window sill',(x*.88,-.13,1.03),(.045,2.25,.055),'black',root)
            for y in [-.67,.43]:
                box('door handle',(x*.935,y-.25,.97),(.025,.18,.04),'silver',root)
                box('door seam',(x*.934,y+.49,.77),(.01,.012,.43),'black',root)
        box('roof',(0,-.05,1.7),(1.49,1.44,.10),paint,root,.06)
        mesh('windscreen',[(-.82,.97,1.08),(.82,.97,1.08),(.70,.57,1.65),(-.70,.57,1.65)],[(0,1,2,3)],'glass',root)
        box('rear parcel shelf',(0,-1.05,1.07),(1.56,.35,.07),'black',root)
        for x in [-.44,.44]:
            box('front seat back',(x,.01,1.10),(.5,.15,.62),'black',root,.035)
            box('headrest',(x,.01,1.19),(.29,.12,.18),'black',root,.03)
        if taxi:
            # Sitting right-hand driver; only rear head/shoulders are in this shot.
            box('GG01 maroon shoulders',(.44,.23,1.27),(.45,.22,.32),'maroon',root,.055)
            sphere('GG01 head',(.44,.23,1.52),(.115,.10,.15),'skin',root)
            sphere('GG01 hair cap',(.44,.19,1.58),(.12,.10,.12),'black',root)
            rod('GG01 ponytail',(.44,.08,1.59),(.47,.04,1.25),.055,'black',root)
            for x in [.24,.64]:rod('GG01 driving arm',(x,.25,1.35),(x,.66,1.18),.045,'skin',root)
    wheels=[]
    for x in [-.91,.91]:
        for y in [-1.43,1.43]:
            wheel=empty('wheel pivot');wheel.parent=root;wheel.location=(x,y,.34)
            rod('tire',(-.12,0,0),(.12,0,0),.34,'black',wheel,12)
            rod('hub',(-.125,0,0),(.125,0,0),.20,'silver',wheel,10)
            for a in range(5):
                aa=a*math.tau/5
                rod('hub spoke',(x/abs(x)*.13,0,0),(x/abs(x)*.13,math.sin(aa)*.18,math.cos(aa)*.18),.018,'black',wheel,4)
            wheels.append(wheel)
        box('mirror',(x*1.1,.66,1.1),(.23,.22,.13),paint,root,.03)
    for y in [-2.26,2.26]:box('bumper',(0,y,.54),(1.75,.09,.14),'black',root,.03)
    for x in [-.66,.66]:
        box('tail light',(x,-2.263,.91),(.43,.025,.17),'red',root)
        box('indicator',(x*.8,-2.281,.91),(.10,.025,.17),'amber',root)
        box('headlamp',(x,2.263,.91),(.43,.025,.17),'white',root)
    box('yellow rear plate',(0,-2.315,.74),(.47,.012,.13),'plate',root)
    label('number plate','SH 2004',(0,-2.325,.71),.082,'black',root)
    if taxi:
        box('white TAXI roof sign',(0,-.02,1.85),(.51,.30,.21),'white',root,.02)
        label('taxi lettering','TAXI',(0,-.176,1.80),.11,'black',root)
        label('comfort rear lettering','COMFORT',(0,-2.286,1.02),.12,'white',root)
    return root,wheels

# Straight Singapore road; dramatic lane changes supply the camera movement.
box('road',(0,80,-.10),(11.4,230,.18),'road')
for x in [-6.8,6.8]:box('raised footpath',(x,80,.01),(2.1,230,.24),'concrete')
for x in [-5.6,5.6]:
    box('kerb',(x,80,.10),(.18,230,.28),'white')
    box('yellow edge',(x*.96,80,.002),(.08,230,.014),'plate')
for x in [-1.75,1.75]:
    for y in range(-30,201,7):box('lane dash',(x,y,.002),(.1,3,.015),'white')
for y in range(-15,201,14):
    for side in [-1,1]:
        x=side*8.3
        rod('tree trunk',(x,y,.1),(x+.15,y,5.1),.21,'bark')
        for j in range(7):
            a=j*math.tau/7
            bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2,radius=1,location=(x+math.cos(a)*1.55,y+math.sin(a)*1.35,5.2+random.random()))
            o=link(bpy.context.object,'leafy tropical canopy','leaves' if j%2 else 'leaves2');o.scale=(2.3,2.1,1.5)
    rod('streetlamp',(-5.9,y,0),(-5.9,y,6),.055,'silver')
    rod('streetlamp arm',(-5.9,y,6),(-4.8,y,6.1),.04,'silver')
    box('lamp head',(-4.7,y,6.08),(.6,.22,.10),'white')
for y in range(-10,190,25):
    box('HDB tower',(-17,y,16),(10,17,32),'hdb')
    for z in range(2,32,3):
        box('HDB floor ledge',(-11.94,y,z),(.14,17,.15),'concrete')
        for yy in range(-6,7,3):box('HDB windows',(-11.85,y+yy,z+1),(.03,1.6,1.5),'window')
for y in range(-10,191,3):
    rod('green fence post',(6.1,y,.2),(6.1,y,1.25),.035,'window')
for z in [.55,1.15]:rod('green fence rail',(6.1,-25,z),(6.1,200,z),.035,'window')

taxi,tw=car('player blue Comfort taxi','blue',taxi=True)
sedan,sw=car('silver NPC sedan','silver')
van,vw=car('white NPC van','white',van=True)
bpy.ops.object.camera_add();cam=bpy.context.object;cam.name='rear chase camera';bpy.context.scene.camera=cam
cam.data.type='PERSP';cam.data.sensor_fit='HORIZONTAL';cam.data.sensor_width=36
cam.data.lens=36/(2*math.tan(math.radians(48)/2))

def blend(a,b,t):
    t=max(0,min(1,t));return a+(b-a)*t*t*(3-2*t)
def lane(t):
    if t<1.0:return blend(-3.5,0,t)
    if t<1.9:return 0
    if t<2.8:return blend(0,-3.5,(t-1.9)/.9)
    if t<3.6:return -3.5
    return blend(-3.5,0,(t-3.6)/1.2)

scene=bpy.context.scene;scene.frame_start=1;scene.frame_end=121;scene.render.fps=24
trajectory=[]
for f in range(1,122):
    t=(f-1)/24;x=lane(t);y=t*24
    dx=(lane(t+.01)-lane(max(0,t-.01)))/(.01 if t==0 else .02)
    taxi.location=(x,y,0);taxi.rotation_euler=(0,-dx*.006,-math.atan2(dx,24))
    sedan.location=(-3.5,16+t*12,0);van.location=(0,36+t*13,0)
    for root,wheels,speed in [(taxi,tw,24),(sedan,sw,12),(van,vw,13)]:
        root.keyframe_insert('location',frame=f);root.keyframe_insert('rotation_euler',frame=f)
        for w in wheels:w.rotation_euler.x=-speed*t/.34;w.keyframe_insert('rotation_euler',frame=f)
    cam.location=(lane(max(0,t-.12)),y-5.4,3.0)
    target=Vector((x,y+5,1.05))
    cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler()
    cam.keyframe_insert('location',frame=f);cam.keyframe_insert('rotation_euler',frame=f)
    trajectory.append({'frame':f,'time':t,'taxi':list(taxi.location),'sedan':list(sedan.location),'van':list(van.location),'camera':list(cam.location)})

scene.render.engine='CYCLES';scene.cycles.samples=6;scene.cycles.use_denoising=True
scene.render.threads_mode='FIXED';scene.render.threads=6
scene.render.resolution_x=576;scene.render.resolution_y=1024;scene.render.resolution_percentage=100
scene.world.use_nodes=True
bg=scene.world.node_tree.nodes.get('Background');bg.inputs['Color'].default_value=(.53,.67,.66,1);bg.inputs['Strength'].default_value=.7
bpy.ops.object.light_add(type='SUN');sun=bpy.context.object;sun.rotation_euler=(.35,-.4,-.55);sun.data.energy=1.8;sun.data.angle=.07
scene.view_settings.view_transform='Standard';scene.view_settings.look='None';scene.view_settings.exposure=-.4
scene.render.image_settings.file_format='PNG'
scene.frame_set(1)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'taxi-chase-v1.blend'))
metadata={'version':'chase-v1','status':'motion-layout; not approved final look','blender':bpy.app.version_string,'size':[576,1024],'fps':24,'frames':121,'seconds':121/24,'sample_times':[0,1,2,3,4,5],'camera':{'horizontal_fov_degrees':48,'lens_mm':cam.data.lens,'sensor_width_mm':cam.data.sensor_width,'sensor_fit':cam.data.sensor_fit,'shift':[cam.data.shift_x,cam.data.shift_y]},'events':{'silver_pass_seconds':16/12,'van_pass_seconds':36/11},'trajectory':trajectory}
(OUT/'stage.json').write_text(json.dumps(metadata,indent=2))
frames=range(1,122) if '--all' in sys.argv else [1,25,49,73,97,121]
for f in frames:
    scene.frame_set(f);scene.render.filepath=str(OUT/'frames'/f'{f-1:04d}.png');bpy.ops.render.render(write_still=True)
