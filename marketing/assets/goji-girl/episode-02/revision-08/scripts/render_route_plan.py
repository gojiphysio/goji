import bpy,math,json
from pathlib import Path
from mathutils import Vector
R=Path(__file__).resolve().parents[1];E=R.parent
bpy.ops.wm.open_mainfile(filepath=str(R/'blender/route-09-10.blend'))
s=bpy.context.scene
source=(E/'revision-07/scripts/build_continuity.py').read_text()
exec(source[source.index('M={}'):source.index('# +Y is vehicle forward')])
# Native top-down route diagram with the same fixed geometry and marks.
for ob in bpy.data.objects:
 if ob.name.startswith(('ROUTE','balcony','tower window','tree crown')):ob.hide_render=True
route=[(-6.3,5.4,.30),(-6.35,10,.30),(-6.6,16,.30),(-7.15,22.1,.30),(-9.58,25.3,.30)]
for a,b in zip(route,route[1:]):segment('review route',a,b,.06,.06,'yellow')
for label,p in [('09',route[0]),('10',route[-2]),('GOJI',route[-1])]:text('plan '+label,label,(p[0]-1.1,p[1],38),.45,'white',(0,0,0))
text('plan wreck','WRECK',(-3.0,-2,38),.55,'white',(0,0,0))
for ob in bpy.data.objects:
 if 'roof' in ob.name and ('canopy' in ob.name or 'shelter' in ob.name):ob.hide_render=True
bpy.ops.object.camera_add(location=(-4.7,12.0,45));cam=bpy.context.object;cam.rotation_euler=(0,0,0);cam.data.type='ORTHO';cam.data.ortho_scale=39;s.camera=cam
s.render.resolution_x=900;s.render.resolution_y=1200;s.render.filepath=str(R/'frames/route-plan.png');bpy.ops.render.render(write_still=True)
