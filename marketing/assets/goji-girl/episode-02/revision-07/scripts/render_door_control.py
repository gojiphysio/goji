import bpy,math
from pathlib import Path
R=Path(__file__).resolve().parents[1]
bpy.ops.wm.open_mainfile(filepath=str(R/'blender/double-decker-master.blend'))
s=bpy.context.scene;s.timeline_markers.clear();s.frame_set(35);s.camera=bpy.data.objects['SHOT 08 locked camera']
bus=bpy.data.objects['BUS-SOS-01 chassis transform']
def mat(n,c):
 m=bpy.data.materials.new(n);m.diffuse_color=(*c,1);m.use_nodes=True;m.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value=(*c,1);return m
lime=mat('CONTROL intact front corner',(.25,1,.02));pink=mat('CONTROL doorway footprint',(1,.01,.6))
for o in bus.children_recursive:
 if o.name.startswith('left front corner'):o.data.materials.clear();o.data.materials.append(lime)
# Flat marks over side plane: front corner remains intact, door footprint inset aft.
for name,yy,length,ma in [('solid front corner MUST REMAIN',5.65,.70,lime),('side doorway ONLY',4.55,1.5,pink)]:
 bpy.ops.mesh.primitive_cube_add(size=1);o=bpy.context.object;o.name=name;o.parent=bus;o.location=(-1.37,yy,1.62);o.scale=(.015,length,1.98);o.data.materials.append(ma)
s.render.filepath=str(R/'frames/08-door-control.png');bpy.ops.render.render(write_still=True)
