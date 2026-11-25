"""Ground shots09–10 in one frozen street. Wreck stays behind the player."""
import bpy,math,json
from pathlib import Path
from mathutils import Vector
R=Path(__file__).resolve().parents[1];E=R.parent
bpy.ops.wm.open_mainfile(filepath=str(E/'revision-07/blender/double-decker-master.blend'))
s=bpy.context.scene;s.timeline_markers.clear();s.frame_set(80)
# Reuse the existing primitive/actor functions, without rebuilding or clearing set.
source=(E/'revision-07/scripts/build_continuity.py').read_text()
exec(source[source.index('M={}'):source.index('# +Y is vehicle forward')])
bus=bpy.data.objects['BUS-SOS-01 chassis transform'];bus.animation_data_clear();bus.location=(-5.1,0,1.45);bus.rotation_euler=(0,math.pi/2,0)
# Hide every old actor and old camera-only light; geometry is kept in the same place.
for ob in bpy.data.objects:
 if ob.name.startswith(('GG','DRIVER','EXIT','EZLink','offscreen')):
  ob.animation_data_clear();ob.hide_render=True
# Fix a clinic bay farther along the SAME west sidewalk, ahead in +Y.
for ob in list(bpy.data.objects):
 if ob.name.startswith(('shop glazing','shop mullion')) and 22<=ob.location.y<=29:ob.hide_render=True
for yy in [22,23.4,27.2,28.6]:
 cube('Goji fixed facade glass',(-9.66,yy,1.65),(.04,1.32,2.9),'glass')
 cube('Goji fixed facade mullion',(-9.60,yy+.68,1.65),(.08,.055,3.0),'black')
# Door bay opening around y25.3, with a small recessed reception.
cube('Goji door top rail',(-9.58,25.3,3.10),(.10,2.5,.10),'black')
for yy in [24.08,26.52]:cube('Goji door jamb',(-9.58,yy,1.65),(.10,.09,3.0),'black')
cube('Goji entry threshold',(-9.9,25.3,.15),(.75,2.45,.06),'cream')
cube('Goji recessed interior',(-10.5,25.3,1.6),(.08,2.5,2.9),'cream')
text('Goji facade wordmark','GOJI',(-9.54,23.2,2.20),.42,'white',(math.pi/2,0,math.pi/2))
text('Goji facade descriptor','Physiotherapy',(-9.53,23.2,1.91),.12,'white',(math.pi/2,0,math.pi/2))
# Red round projecting sign at the approach edge, faces arriving player.
segment('Goji red round projecting sign',(-8.85,22.8,2.85),(-8.85,22.86,2.85),.38,.38,'maroon',vertices=32)
text('Goji round sign wordmark','GOJI',(-8.85,22.77,2.79),.20,'white',(math.pi/2,0,0))
# Same girl at two successive route positions; exactly two pursuing cops in10.
g9=Person('ROUTE09 Goji girl');g9.pose(1,(-6.3,5.4,.13),0,walk=.3)
g10=Person('ROUTE10 Goji girl');g10.pose(1,(-7.15,22.1,.13),.35,walk=1.2)
cops=[]
for name,pos,phase in [('left',(-7.95,19.2,.13),1.0),('right',(-5.9,19.6,.13),2.0)]:
 p=Person('ROUTE10 officer '+name,outfit='navy',hair='short');p.pose(1,pos,.20,walk=phase);cops.append(p)
 cube('ROUTE10 police cap', (0,0,1.81),(.28,.25,.07),'navy',p.root)
def set_actor(p,shown):
 for ob in [p.root]+list(p.root.children_recursive):ob.animation_data_clear();ob.hide_render=not shown
# Clear stage keys on newly posed actors after evaluating frame1.
s.frame_set(1)
for p in [g9,g10]+cops:
 for ob in [p.root]+list(p.root.children_recursive):ob.animation_data_clear()
# Hide old actors again after inherited frame evaluation.
for ob in bpy.data.objects:
 if ob.name.startswith(('GG','DRIVER','EXIT','EZLink','offscreen')):ob.hide_render=True
s.render.resolution_x=540;s.render.resolution_y=960;s.cycles.samples=24
cameras={}
for sid,pos,target in [('09',(-6.7,1.3,2.0),(-6.1,5.4,1.25)),('10',(-6.5,17.3,2.1),(-8.25,24.6,1.4))]:
 bpy.ops.object.camera_add(location=pos);cam=bpy.context.object;cam.name='ROUTE '+sid+' player camera';cam.rotation_euler=(Vector(target)-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.sensor_fit='HORIZONTAL';cam.data.sensor_width=36;cam.data.lens=36/(2*math.tan(math.radians(52)/2));cameras[sid]=cam
 s.camera=cam;set_actor(g9,sid=='09');set_actor(g10,sid=='10')
 for p in cops:set_actor(p,sid=='10')
 s.render.filepath=str(R/'frames'/f'{sid}-route-direct.png');bpy.ops.render.render(write_still=True)
bpy.context.view_layer.update()
buspoints=[o.matrix_world@Vector(v) for o in bus.children_recursive if o.type=='MESH' for v in o.bound_box]
forward10=cameras['10'].matrix_world.to_quaternion()@Vector((0,0,-1))
depths=[(p-cameras['10'].location).dot(forward10) for p in buspoints]
assert max(depths)<0,('wreck must be behind shot10 camera',max(depths))
p9=Vector(g9.root.location);p10=Vector(g10.root.location);door=Vector((-9.58,25.3,.13))
assert p10.y>p9.y and (p10-bus.location).length>(p9-bus.location).length
assert (door-p10).length<(door-p9).length
record={'source_scene':'revision-07/blender/double-decker-master.blend','world_forward':'+Y','sidewalk':'west x<-5.2','wreck_matrix':[[round(v,6) for v in row] for row in bus.matrix_world],'girl09':list(p9),'girl10':list(p10),'clinic_door':list(door),'cameras':{sid:{'position':list(c.location),'rotation':list(c.rotation_euler),'horizontal_fov_degrees':52} for sid,c in cameras.items()},'wreck_depth_from_camera10':{'min':min(depths),'max':max(depths)},'checks':{'same_frozen_wreck':True,'girl_moves_positive_Y':True,'distance_from_wreck_increases':True,'distance_to_clinic_decreases':True,'entire_wreck_behind_camera10':True},'interpretation':'09 looks forward past wreck edge;10 continues farther along same pavement toward Goji. Wreck is behind camera and cannot appear ahead of player. Geography is fictional compressed staging.'}
(R/'blender/route-record.json').write_text(json.dumps(record,indent=2)+'\n')
s.camera=cameras['10'];bpy.ops.wm.save_as_mainfile(filepath=str(R/'blender/route-09-10.blend'))
# Native top-down route diagram with the same fixed geometry and marks.
for p in [g9,g10]+cops:set_actor(p,False)
route=[(-6.3,5.4,.30),(-6.35,10,.30),(-6.6,16,.30),(-7.15,22.1,.30),(-9.58,25.3,.30)]
for a,b in zip(route,route[1:]):segment('review route',a,b,.06,.06,'yellow')
for label,p in [('09',route[0]),('10',route[-2]),('GOJI',route[-1])]:text('plan '+label,label,(p[0]-1.1,p[1],4.3),.45,'white',(0,0,0))
text('plan wreck','WRECK',(-3.0,-2,4.3),.55,'white',(0,0,0))
for ob in bpy.data.objects:
 if 'roof' in ob.name and ('canopy' in ob.name or 'shelter' in ob.name):ob.hide_render=True
bpy.ops.object.camera_add(location=(-4.7,12.0,45));cam=bpy.context.object;cam.rotation_euler=(0,0,0);cam.data.type='ORTHO';cam.data.ortho_scale=39;s.camera=cam
s.render.resolution_x=900;s.render.resolution_y=1200;s.render.filepath=str(R/'frames/route-plan.png');bpy.ops.render.render(write_still=True)

