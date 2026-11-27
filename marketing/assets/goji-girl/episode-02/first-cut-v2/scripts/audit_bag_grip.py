"""Check the saved running guides; generated footage needs separate review."""
import bpy
import json
import math
from pathlib import Path
from mathutils import Matrix, Vector

R = Path(__file__).resolve().parents[1]
records = []
for shot in ['03', '04', '10']:
    source = R / 'guides' / f'{shot}-grip-motion-v2-motion.blend'
    bpy.ops.wm.open_mainfile(filepath=str(source))
    root = bpy.data.objects[f'CUT{shot} GG01']
    bag = bpy.data.objects[f'CUT{shot} GG01 handbag']
    hands = [o for o in root.children if o.type == 'MESH' and o.name.startswith(f'CUT{shot} GG01 hand')]
    hand = min(hands, key=lambda o: o.location.x)
    expected = Matrix.Rotation(math.pi / 2, 3, 'Z').to_quaternion()
    angles, distances, outward = [], [], []
    for frame in range(bpy.context.scene.frame_start, bpy.context.scene.frame_end + 1):
        bpy.context.scene.frame_set(frame)
        relative = hand.matrix_world.inverted() @ bag.matrix_world
        angles.append(relative.to_quaternion().rotation_difference(expected).angle)
        distances.append((bag.matrix_world.translation - hand.matrix_world.translation).length)
        normal = (bag.matrix_world.to_3x3() @ Vector((0, 1, 0))).normalized()
        left = (root.matrix_world.to_3x3() @ Vector((-1, 0, 0))).normalized()
        outward.append(normal.dot(left))
        assert max(abs(v - 1) for v in bag.scale) < 1e-6, 'Bag scale changed'
    assert max(angles) < 0.002, 'Bag orientation detached from the hand grip'
    assert max(abs(d - .035) for d in distances) < 0.0001, 'Bag detached from the grip position'
    assert min(outward) > .999, 'Broad face no longer points outward beside her body'
    records.append({'shot': shot, 'frames_checked': len(angles), 'max_grip_rotation_error_radians': max(angles), 'grip_offset_metres': [min(distances), max(distances)], 'minimum_outward_face_dot': min(outward), 'scale_constant': True})

(R / 'guides/bag-grip-audit.json').write_text(json.dumps({'scope': 'Saved Blender running guides only; not a generated-footage pass', 'checks': records}, indent=2) + '\n')
print(json.dumps(records))
