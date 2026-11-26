import bpy,math,json
from pathlib import Path
R=Path(__file__).resolve().parents[1];E=R.parent
bpy.ops.wm.open_mainfile(filepath=str(E/'revision-07/blender/double-decker-master.blend'))
s=bpy.context.scene;s.timeline_markers.clear();s.frame_set(35)
bus=bpy.data.objects['BUS-SOS-01 chassis transform'];bus.animation_data_clear();bus.location=(-5.1,0,1.45);bus.rotation_euler=(0,math.pi/2,0)
# Preserve validated articulated exit keys; remove staged-panel visibility keys only.
for ob in bpy.data.objects:
 if ob.animation_data and ob.animation_data.action:
  for layer in ob.animation_data.action.layers:
   for strip in layer.strips:
    for slot in ob.animation_data.action.slots:
     try:bag=strip.channelbag(slot)
     except:continue
     for fc in list(bag.fcurves):
      if fc.data_path=='hide_render':bag.fcurves.remove(fc)
 if ob.name.startswith(('GG04','GG05','GG09','DRIVER','offscreen')):ob.hide_render=True
 if ob.name.startswith(('GG01','EZLink','EXIT')):ob.hide_render=False
s.camera=bpy.data.objects['SHOT 08 locked camera'];s.render.resolution_x=288;s.render.resolution_y=512;s.cycles.samples=8;s.render.fps=12
s.frame_start=1;s.frame_end=73;s.render.image_settings.file_format='PNG'
out=R/'guides/08-frames';out.mkdir(exist_ok=True)
s.render.filepath=str(out/'frame-');bpy.ops.wm.save_as_mainfile(filepath=str(R/'guides/08-exit.blend'))
for f in range(1,74):
 s.frame_set(f);s.render.filepath=str(out/f'{f:04}.png');bpy.ops.render.render(write_still=True)
print('08 exit guide done')
