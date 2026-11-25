"""Render a reference-angle view of the current bus, without changing story cameras."""
import bpy,math
from pathlib import Path
from mathutils import Vector
R=Path(__file__).resolve().parents[1]
bpy.ops.wm.open_mainfile(filepath=str(R/'blender/double-decker-master.blend'))
s=bpy.context.scene;s.timeline_markers.clear();s.frame_set(30)
# Isolated asset review: remove set occluders, keeping the same unmodified bus.
bus=bpy.data.objects['BUS-SOS-01 chassis transform'];keep=set([bus]+list(bus.children_recursive))
for o in bpy.data.objects:
 if o.type in ['MESH','FONT'] and o not in keep and o.name!='two-way asphalt':
  o.animation_data_clear();o.hide_render=True
bpy.ops.object.camera_add(location=(-13,-15,5.2));c=bpy.context.object;c.name='Livery reference angle only'
c.rotation_euler=(Vector((-2.8,0,1.45))-c.location).to_track_quat('-Z','Y').to_euler()
c.data.sensor_fit='HORIZONTAL';c.data.sensor_width=36;c.data.lens=36/(2*math.tan(math.radians(58)/2));s.camera=c
s.render.resolution_x=960;s.render.resolution_y=640
s.render.filepath=str(R/'frames/wreck-clinic-angle.png');bpy.ops.render.render(write_still=True)
