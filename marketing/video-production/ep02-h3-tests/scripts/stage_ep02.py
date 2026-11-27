"""Episode 2 hard-scene motion guides (T01 walk/occlusion, T02 bag + therapist, T03 squats).

Run: blender -b --python stage_ep02.py -- SCENE [--render none|preview|all] [--depth]

Original low-poly PROXY figures and sets. They establish blocking, contacts,
timing and camera only; they are not reviewed cast assets and carry no approved
appearance. Units are metres, Z up. Characters are built facing local +Y.
Video index 0 = Blender frame 0 = t 0 s, 24 fps. Frame counts sit on H3's
17k+5 grid (192 = 8.0 s, 362 = 15.08 s). T03 runs to 532 frames so frames
340-531 can guide the continuation take.
"""
import bpy, json, math, sys
from pathlib import Path
from mathutils import Vector, Matrix, Euler

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else ['t02']
SCENE = argv[0]
RENDER = argv[argv.index('--render') + 1] if '--render' in argv else 'none'
DEPTH = '--depth' in argv
FPS = 24
OUT = Path(__file__).resolve().parents[1] / 'staging' / SCENE
OUT.mkdir(parents=True, exist_ok=True)

for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
M = {}


def material(name, color, checker=None, noise=False):
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*color, 1)
    m.use_nodes = True
    nt = m.node_tree
    bs = nt.nodes.get('Principled BSDF')
    bs.inputs['Base Color'].default_value = (*color, 1)
    bs.inputs['Roughness'].default_value = .85
    if checker:
        tc = nt.nodes.new('ShaderNodeTexCoord')
        ck = nt.nodes.new('ShaderNodeTexChecker')
        ck.inputs['Scale'].default_value = checker[2]
        ck.inputs['Color1'].default_value = (*checker[0], 1)
        ck.inputs['Color2'].default_value = (*checker[1], 1)
        nt.links.new(tc.outputs['Object'], ck.inputs['Vector'])
        nt.links.new(ck.outputs['Color'], bs.inputs['Base Color'])
    elif noise:
        tex = nt.nodes.new('ShaderNodeTexNoise')
        tex.inputs['Scale'].default_value = 18
        ramp = nt.nodes.new('ShaderNodeValToRGB')
        ramp.color_ramp.elements[0].color = tuple(c * .8 for c in color) + (1,)
        ramp.color_ramp.elements[1].color = tuple(min(1, c * 1.12) for c in color) + (1,)
        nt.links.new(tex.outputs['Fac'], ramp.inputs[0])
        nt.links.new(ramp.outputs[0], bs.inputs['Base Color'])
    M[name] = m
    return m


PALETTE = {
    'skin': (.50, .27, .13), 'skin2': (.42, .22, .11), 'skin3': (.58, .36, .2),
    'maroon': (.25, .02, .035), 'black': (.018, .018, .02), 'hair': (.012, .01, .01),
    'white': (.8, .8, .78), 'gold': (.7, .45, .05), 'goji': (.75, .08, .06),
    'shirtblue': (.25, .42, .62), 'khaki': (.42, .35, .2), 'brown': (.12, .07, .04),
    'yellowtop': (.75, .55, .06), 'grey': (.25, .25, .26), 'eye': (.02, .015, .01),
    'tabletop': (.28, .025, .02), 'wood': (.55, .28, .08), 'wall': (.62, .36, .12),
    'cream': (.75, .68, .52), 'shelf': (.5, .26, .07), 'vase': (.78, .76, .7),
    'leaf': (.08, .25, .05), 'flower': (.7, .03, .04), 'paper': (.85, .85, .82),
    'pave': (.42, .38, .32), 'road': (.22, .22, .21), 'kerb': (.55, .55, .5),
    'lane': (.8, .78, .7), 'yline': (.75, .55, .03), 'roof': (.5, .5, .48),
    'pillar': (.42, .42, .4), 'hdb': (.7, .66, .58), 'hdbred': (.55, .2, .2),
    'trunk': (.2, .14, .08), 'canopy': (.12, .28, .06), 'grass': (.15, .3, .07),
    'marker': (.95, .7, .02), 'rail': (.05, .3, .15), 'floorwood': (.55, .38, .2),
    'mat': (.8, .55, .05), 'plinth': (.15, .15, .17), 'wallcream': (.78, .72, .6),
    'glass': (.15, .22, .24),
}
for n, c in PALETTE.items():
    material(n, c, noise=n in ['pave', 'road', 'hdb', 'canopy', 'grass', 'wall', 'floorwood'])
material('checker', (.5, .1, .1), checker=((.42, .05, .05), (.8, .7, .55), 14))


def box(name, loc, size, mat, parent=None, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    o = bpy.context.object
    o.name = name
    o.scale = size
    o.data.materials.append(M[mat])
    if parent:
        o.parent = parent
    return o


def cyl(name, loc, r, depth, mat, verts=8, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=depth, location=loc, rotation=rot)
    o = bpy.context.object
    o.name = name
    o.data.materials.append(M[mat])
    return o


def empty(name, loc=(0, 0, 0)):
    o = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(o)
    o.location = loc
    return o


# ---------------------------------------------------------------- characters
H0 = 1.65
JOINTS = {  # name: (head, tail, parent) in metres for a 1.65 m figure facing +Y
    'pelvis': ((0, 0, .95), (0, 0, 1.05), None),
    'spine': ((0, 0, 1.05), (0, 0, 1.38), 'pelvis'),
    'head': ((0, 0, 1.40), (0, 0, 1.65), 'spine'),
}
for s, k in [(1, 'R'), (-1, 'L')]:
    JOINTS.update({
        f'shoulder.{k}': ((0, 0, 1.36), (s * .19, 0, 1.36), 'spine'),
        f'upperarm.{k}': ((s * .19, 0, 1.36), (s * .21, -.04, 1.08), f'shoulder.{k}'),
        f'forearm.{k}': ((s * .21, -.04, 1.08), (s * .22, 0, .83), f'upperarm.{k}'),
        f'hand.{k}': ((s * .22, 0, .83), (s * .22, .01, .74), f'forearm.{k}'),
        f'thigh.{k}': ((s * .1, 0, .93), (s * .1, .04, .51), 'pelvis'),
        f'shin.{k}': ((s * .1, .04, .51), (s * .1, 0, .09), f'thigh.{k}'),
        f'foot.{k}': ((s * .1, 0, .09), (s * .1, .16, .03), f'shin.{k}'),
    })


class Figure:
    """Armature proxy with IK hands and feet. Targets are world-space empties."""

    def __init__(self, name, height, outfit):
        self.name, self.h = name, height
        self.scale = height / H0
        data = bpy.data.armatures.new(name + ' rig')
        self.arm = bpy.data.objects.new(name, data)
        bpy.context.collection.objects.link(self.arm)
        bpy.context.view_layer.objects.active = self.arm
        bpy.ops.object.mode_set(mode='EDIT')
        for b, (hd, tl, par) in JOINTS.items():
            eb = data.edit_bones.new(b)
            eb.head, eb.tail = hd, tl
            if par:
                eb.parent = data.edit_bones[par]
                eb.use_connect = b.startswith(('upperarm', 'forearm', 'hand', 'shin'))
        bpy.ops.object.mode_set(mode='OBJECT')
        self.arm.scale = (self.scale,) * 3
        self.targets = {}
        for k in 'LR':
            for part, chain in [('hand', 'forearm'), ('ankle', 'shin')]:
                t = empty(f'{name} {part}.{k} target')
                self.targets[f'{part}.{k}'] = t
                c = self.arm.pose.bones[f'{chain}.{k}'].constraints.new('IK')
                c.target, c.chain_count = t, 2
            cr = self.arm.pose.bones[f'foot.{k}'].constraints.new('COPY_ROTATION')
            cr.target = self.arm
        self.build_mesh(outfit)

    def part(self, bone, size, mat, offset=(0, 0, 0), frac=.5):
        hd, tl, _ = JOINTS[bone]
        hd, tl = Vector(hd), Vector(tl)
        loc = hd.lerp(tl, frac) + Vector(offset)
        d = tl - hd
        q = d.to_track_quat('Z', 'Y') if bone.startswith(('upperarm', 'forearm', 'hand', 'thigh', 'shin')) else None
        o = box(f'{self.name} {bone} {mat}', (0, 0, 0), size, mat)
        world = Matrix.Translation(loc) @ (q.to_matrix().to_4x4() if q else Matrix())
        o.parent = self.arm
        o.parent_type = 'BONE'
        o.parent_bone = bone
        bpy.context.view_layer.update()
        o.matrix_world = self.arm.matrix_world @ world @ Matrix.Diagonal((*size, 1))
        o.scale = size
        return o

    def build_mesh(self, f):
        p = self.part
        p('pelvis', (.33, .2, .2), f['legs'], (0, 0, -.04))
        p('spine', (.34, .2, .2), f['top'], (0, 0, -.06), .35)
        p('spine', (.38, .22, .16), f['top'], (0, 0, .07), .6)
        if f.get('mark'):
            p('spine', (.05, .01, .04), 'goji', (-.09, .115, .1), .6)
        p('head', (.05, .06, .08), f['skin'], (0, 0, -.11), .2)  # neck
        p('head', (.17, .19, .22), f['skin'], (0, .01, .02), .55)
        p('head', (.025, .01, .02), 'eye', (-.045, .105, .05), .55)
        p('head', (.025, .01, .02), 'eye', (.045, .105, .05), .55)
        hair = f['hair']
        p('head', (.185, .2, .07), 'hair', (0, -.01, .12), .55)
        if hair == 'ponytail':
            p('head', (.18, .07, .2), 'hair', (0, -.09, .04), .55)
            p('head', (.08, .07, .3), 'hair', (0, -.15, -.15), .55)
        elif hair == 'bob':
            p('head', (.2, .19, .16), 'hair', (0, -.03, -.03), .55)
        elif hair == 'cap':
            p('head', (.2, .24, .06), f['top'], (0, .03, .14), .55)
        for k in 'LR':
            sl = f.get('sleeve')
            p(f'upperarm.{k}', (.085, .085, .29), sl if sl else f['skin'])
            p(f'forearm.{k}', (.075, .075, .26), f['skin'])
            p(f'hand.{k}', (.06, .085, .11), f['skin'])
            p(f'thigh.{k}', (.14, .14, .43), f['legs'])
            p(f'shin.{k}', (.11, .11, .43), f['legs'])
            p(f'foot.{k}', (.1, .25, .08), f['shoes'], (0, .03, -.02))

    def bone_world(self, bone, end='tail'):
        pb = self.arm.pose.bones[bone]
        return self.arm.matrix_world @ getattr(pb, end)


def heading_mat(theta):
    return Matrix.Rotation(theta, 4, 'Z')


def smooth(x):
    x = min(1, max(0, x))
    return x * x * (3 - 2 * x)


def interp(keys, t):
    """keys: [(t, value)], smoothstep between keys; value may be tuple/float."""
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t <= t1:
            u = smooth((t - t0) / (t1 - t0)) if t1 > t0 else 1
            if isinstance(v0, (int, float)):
                return v0 + (v1 - v0) * u
            return tuple(a + (b - a) * u for a, b in zip(v0, v1))
    return keys[-1][1]


def linear(keys, t):
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t <= t1:
            u = (t - t0) / (t1 - t0) if t1 > t0 else 1
            if isinstance(v0, (int, float)):
                return v0 + (v1 - v0) * u
            return tuple(a + (b - a) * u for a, b in zip(v0, v1))
    return keys[-1][1]


class Motion:
    """Per-character timeline. root(t)->(x,y), heading(t)->radians, plus
    stepping plan, hand overrides and posture curves, evaluated per frame."""

    def __init__(self, fig, root, heading, steps, lateral=.1):
        self.fig, self.root, self.heading, self.steps, self.lat = fig, root, heading, steps, lateral
        self.hand = {}      # 'L'/'R' -> function(t) -> world Vector or None
        self.lean = lambda t: 0.0
        self.drop = lambda t: 0.0      # pelvis drop (squat)
        self.hipback = lambda t: 0.0
        self.head_turn = lambda t: 0.0
        self.nod = lambda t: 0.0
        self.swing = lambda t: 1.0     # arm swing amount 0..1
        # steps: list of (land_time, side) in order; plant = root(land+0.25)
        self.plants = {'L': [], 'R': []}
        for land, side in steps:
            self.plants[side].append(land)

    def world(self, local, t):
        x, y = self.root(t)
        return Vector((x, y, 0)) + heading_mat(self.heading(t)).to_3x3() @ Vector(local)

    def plant_pos(self, side, land):
        tm = land + .25
        s = 1 if side == 'R' else -1
        x, y = self.root(tm)
        return Vector((x, y, 0)) + heading_mat(self.heading(tm)).to_3x3() @ Vector((s * self.lat * self.fig.scale, 0, 0))

    def ankle(self, side, t):
        lands = self.plants[side]
        z0 = .09 * self.fig.scale
        swing_t = .38
        prev = [l for l in lands if l <= t]
        nxt = [l for l in lands if l > t]
        if not prev:
            p = self.plant_pos(side, lands[0] - 1) if lands else None
            if nxt and t > nxt[0] - swing_t:
                a = self.plant_pos(side, -10)
                b = self.plant_pos(side, nxt[0])
                u = (t - (nxt[0] - swing_t)) / swing_t
                v = a.lerp(b, smooth(u))
                v.z = z0 + .09 * math.sin(math.pi * u)
                return v
            v = self.plant_pos(side, -10)
            v.z = z0
            return v
        cur = self.plant_pos(side, prev[-1])
        if nxt and t > nxt[0] - swing_t:
            b = self.plant_pos(side, nxt[0])
            u = (t - (nxt[0] - swing_t)) / swing_t
            v = cur.lerp(b, smooth(u))
            v.z = z0 + .09 * math.sin(math.pi * u)
            return v
        cur.z = z0
        return cur

    def moving(self, t):
        a, b = Vector(self.root(t - .05)), Vector(self.root(t + .05))
        return min(1, (a - b).length / .1 / .8)


def apply_motion(mo, frame, t):
    f = mo.fig
    x, y = mo.root(t)
    th = mo.heading(t)
    sp = mo.moving(t)
    bob = .018 * sp * math.cos(4 * math.pi * t)
    back = heading_mat(th).to_3x3() @ Vector((0, -mo.hipback(t), 0))
    f.arm.location = (x + back.x, y + back.y, -mo.drop(t) + bob - .015)
    f.arm.rotation_euler = (0, 0, th)
    f.arm.keyframe_insert('location', frame=frame)
    f.arm.keyframe_insert('rotation_euler', frame=frame)
    sb = f.arm.pose.bones['spine']
    sb.rotation_mode = 'XYZ'
    sb.rotation_euler = (mo.lean(t), 0, 0)
    sb.keyframe_insert('rotation_euler', frame=frame)
    hb = f.arm.pose.bones['head']
    hb.rotation_mode = 'XYZ'
    hb.rotation_euler = (mo.nod(t), mo.head_turn(t), 0)
    hb.keyframe_insert('rotation_euler', frame=frame)
    for k in 'LR':
        a = f.targets[f'ankle.{k}']
        a.location = mo.ankle(k, t)
        a.keyframe_insert('location', frame=frame)
        s = 1 if k == 'R' else -1
        override = mo.hand.get(k)
        pos = override(t) if override else None
        if pos is None:
            # Relaxed arm, swinging opposite to the same-side leg.
            phase = math.sin(2 * math.pi * t) * (1 if k == 'L' else -1)
            amt = mo.swing(t) * sp
            local = Vector((s * .25, .16 * amt * phase + .02, .80 - mo.drop(t) / f.scale * .9)) * f.scale
            pos = mo.world(local, t)
        h = f.targets[f'hand.{k}']
        h.location = pos
        h.keyframe_insert('location', frame=frame)


# ---------------------------------------------------------------- outfits
GIRL = dict(top='maroon', legs='maroon', skin='skin', hair='ponytail', shoes='white')
THERAPIST = dict(top='black', legs='black', skin='skin3', hair='bob', shoes='white', sleeve='black', mark=True)
NPC1 = dict(top='shirtblue', legs='khaki', skin='skin2', hair='short', shoes='brown', sleeve='shirtblue')
NPC2 = dict(top='yellowtop', legs='grey', skin='skin', hair='cap', shoes='black', sleeve='yellowtop')


def handbag(name='GG01 black handbag'):
    root = empty(name)
    box(name + ' body', (0, 0, .085), (.26, .12, .17), 'black', root)
    box(name + ' flap', (0, .062, .12), (.24, .01, .08), 'black', root)
    box(name + ' gold clasp', (0, .068, .11), (.035, .01, .025), 'gold', root)
    for x in (-.07, .07):
        box(name + ' handle post', (x, 0, .2), (.015, .015, .07), 'black', root)
    box(name + ' handle top', (0, 0, .235), (.155, .015, .015), 'black', root)
    return root


def camera(loc, look, hfov=42, w=576, h=1024):
    cam = bpy.data.cameras.new('cam')
    cam.sensor_fit = 'HORIZONTAL'
    cam.sensor_width = 36
    cam.lens = 36 / (2 * math.tan(math.radians(hfov) / 2))
    o = bpy.data.objects.new('camera', cam)
    bpy.context.collection.objects.link(o)
    bpy.context.scene.camera = o
    set_cam(o, loc, look)
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = w, h
    return o


def set_cam(o, loc, look, frame=None):
    o.location = loc
    o.rotation_euler = (Vector(look) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    if frame is not None:
        o.keyframe_insert('location', frame=frame)
        o.keyframe_insert('rotation_euler', frame=frame)


def light(sun_rot=(math.radians(50), math.radians(10), math.radians(30)), strength=3.5, world=(.55, .6, .65)):
    s = bpy.data.lights.new('sun', 'SUN')
    s.energy = strength
    s.angle = math.radians(3)
    o = bpy.data.objects.new('sun', s)
    bpy.context.collection.objects.link(o)
    o.rotation_euler = sun_rot
    w = bpy.data.worlds.new('world')
    w.use_nodes = True
    w.node_tree.nodes['Background'].inputs['Color'].default_value = (*world, 1)
    w.node_tree.nodes['Background'].inputs['Strength'].default_value = .9
    bpy.context.scene.world = w


def walk_steps(t0, t1, first='R', period=.5):
    out, t, side = [], t0, first
    while t <= t1 + 1e-6:
        out.append((round(t, 4), side))
        side = 'L' if side == 'R' else 'R'
        t += period
    return out


# ---------------------------------------------------------------- scenes
def scene_t02(v2=False):
    """Interior reception. GG-01 walks toward camera, places bag on the table,
    GP-01 turns from the shelf and gestures. 192 frames, fixed camera."""
    n = 192
    box('floor', (0, 2.5, -.01), (6, 7, .02), 'checker')
    box('back wall', (0, 5.0, 1.6), (6, .1, 3.2), 'wall')
    box('left wall', (-2.2, 2.5, 1.6), (.1, 7, 3.2), 'wallcream')
    box('right wall', (2.4, 2.5, 1.6), (.1, 7, 3.2), 'wallcream')
    for i, z in enumerate((.9, 1.35, 1.8)):
        box(f'shelf board {i}', (2.2, 3.0, z), (.35, 1.0, .04), 'shelf')
    for i, (y, z, m) in enumerate([(2.7, .97, 'paper'), (3.2, .97, 'goji'), (2.9, 1.42, 'vase'), (3.3, 1.42, 'paper'), (3.0, 1.87, 'goji')]):
        box(f'shelf product {i}', (2.2, y, z + .04), (.12, .12, .14), m)
    box('back shelf', (-1.0, 4.85, 1.3), (1.0, .3, .04), 'shelf')
    box('back shelf jar', (-1.2, 4.85, 1.45), (.18, .18, .26), 'goji')
    box('logo panel', (.6, 4.93, 1.9), (1.2, .04, .4), 'cream')
    box('ceiling', (0, 2.5, 3.2), (6, 7, .1), 'cream')
    # Reception table: fixed surface, top at z = .76, spans x -.8..1.0, y 1.65..2.35
    box('table top', (.1, 2.0, .74), (1.8, .7, .05), 'tabletop')
    box('table pedestal L', (-.5, 2.0, .36), (.25, .25, .72), 'tabletop')
    box('table pedestal R', (.7, 2.0, .36), (.25, .25, .72), 'tabletop')
    cyl('vase', (.75, 2.1, .88), .07, .24, 'vase', 8)
    for i, dx in enumerate((-.05, .04, 0)):
        box(f'ginger flower {i}', (.75 + dx, 2.1, 1.1 + i * .05), (.04, .04, .12), 'flower')
    box('brochure stand', (.45, 1.85, .82), (.12, .04, .12), 'paper')

    girl = Figure('GG01 proxy', 1.65, GIRL)
    ther = Figure('GP01 proxy', 1.58, THERAPIST)
    bag = handbag()

    # GG-01: walk toward camera (heading pi), stop behind table at y 2.75.
    groot = lambda t: (-.35, linear([(0, 4.45), (.25, 4.45), (2.25, 2.5)], t))
    gm = Motion(girl, groot, lambda t: math.pi, walk_steps(.25, 2.25, 'R') + [(2.6, 'L')], lateral=.1)
    gm.lean = lambda t: interp([(0, 0), (2.3, 0), (3.0, .5), (3.9, .5), (4.6, 0)], t)
    gm.head_turn = lambda t: interp([(0, 0), (4.6, 0), (5.4, .55), (8, .55)], t)
    bag_rest = Vector((-.14, 2.2, .76))   # bag base on tabletop
    hand_over = bag_rest + Vector((0, 0, .225))   # hand reaches forward, so tail and wrist share height
    swing_off = lambda t: None

    def g_left(t):
        if v2:
            # v2: lift the bag to chest height while still walking, so it stays above
            # the table edge in camera, then reach forward and lower it onto the top.
            if t < 1.4:
                return None
            carry = gm.world(Vector((-.25, .02, .80)) * girl.scale, 1.4)
            chest = lambda tt: gm.world(Vector((-.14, .32, 1.2)) * girl.scale, tt)
            if t < 2.4:
                u = smooth((t - 1.4) / .6)
                c0 = gm.world(Vector((-.25, .02, .80)) * girl.scale, t)
                return c0.lerp(chest(t), u)
            keys = [(2.4, tuple(chest(2.4))), (3.0, tuple(hand_over + Vector((0, 0, .15)))),
                    (3.5, tuple(hand_over)), (3.9, tuple(hand_over)),
                    (4.6, tuple(gm.world(Vector((-.25, .02, .80)) * girl.scale, 4.6)))]
            if t >= 4.6:
                return None
            return Vector(interp(keys, t))
        if t < 2.3:
            return None
        carry = gm.world(Vector((-.25, .02, .80)) * girl.scale, t)
        keys = [(2.3, tuple(carry)), (3.1, tuple(hand_over + Vector((0, 0, .12)))),
                (3.6, tuple(hand_over)), (3.9, tuple(hand_over)),
                (4.6, tuple(gm.world(Vector((-.25, .02, .80)) * girl.scale, 4.6)))]
        if t >= 4.6:
            return None
        return Vector(interp(keys, t))
    gm.hand['L'] = g_left
    gm.swing = lambda t: 1.0 if t < 2.3 else 0.0
    # GP-01: at shelf facing +x, turns via facing camera to face GG-01 / camera diagonal.
    th0, th1 = -math.pi / 2, -math.pi
    troot = lambda t: (1.12, 2.85)
    tm = Motion(ther, troot, lambda t: interp([(0, th0), (4.0, th0), (5.1, th1)], t),
                [(4.3, 'R'), (4.8, 'L')], lateral=.1)
    tm.swing = lambda t: 0

    def t_right(t):  # open-palm gesture toward GG-01 (her right, screen left)
        if t < 5.2:
            return None
        rest = tm.world(Vector((.25, .02, .80)) * ther.scale, 5.2)
        out = tm.world(Vector((.46, .34, 1.1)) * ther.scale, 6.0)
        keys = [(5.2, tuple(rest)), (6.0, tuple(out)), (7.0, tuple(out + Vector((0, 0, .03)))), (7.99, tuple(out))]
        return Vector(interp(keys, t))
    tm.hand['R'] = t_right
    tm.head_turn = lambda t: interp([(0, 0), (3.6, 0), (4.0, -.5), (5.1, -.35), (8, -.35)], t)
    tm.nod = lambda t: interp([(0, 0), (6.2, 0), (6.5, .18), (6.8, 0)], t)
    cam = camera((.4, -.15, 1.62), (.4, 2.6, .95), hfov=48) if v2 else camera((.4, -.15, 1.38), (.4, 2.6, 1.0), hfov=48)
    light((math.radians(55), 0, math.radians(-35)), 1.8, (.55, .47, .36))
    pt = bpy.data.lights.new('ceiling', 'AREA')
    pt.energy, pt.size = 150, 3
    po = bpy.data.objects.new('ceiling', pt)
    bpy.context.collection.objects.link(po)
    po.location = (0, 2.4, 3.1)
    events = {'bag_contact_frame': None, 'release_frame': round(3.9 * FPS)}
    return n, [gm, tm], dict(bag=bag, girl=girl, bag_rest=bag_rest, grip=(round(2.3 * FPS), round(3.6 * FPS)), release=round(3.9 * FPS)), cam


def tree(name, x, y, h=6):
    cyl(name + ' trunk', (x, y, h / 2 - .5), .18, h - 1, 'trunk', 6)
    box(name + ' canopy', (x, y, h), (3.2, 3.2, 1.6), 'canopy', rot=(0, 0, .4))
    box(name + ' canopy top', (x + .3, y - .2, h + 1), (2.2, 2.2, 1.0), 'canopy', rot=(0, 0, 1.1))


def hdb(name, x, y, w=10, d=10, h=24):
    box(name, (x, y, h / 2), (w, d, h), 'hdb')
    for z in range(3, int(h) - 1, 3):
        box(name + f' band {z}', (x, y, z), (w + .05, d + .05, .35), 'hdbred')


def scene_t01():
    """Exterior walkway. Rear-follow walk past NPC-01 (oncoming) and NPC-02
    (crosses the foreground, occluding GG-01 ~4.3-4.8 s); GG-01 stops on the
    yellow marker. 192 frames."""
    n = 192
    box('pavement', (.3, 30, -.05), (4.6, 80, .1), 'pave')
    box('kerb', (2.65, 30, .0), (.15, 80, .2), 'kerb')
    box('road', (6, 30, -.1), (6.6, 80, .1), 'road')
    for i in range(0, 80, 6):
        box(f'lane dash {i}', (6.0, i, -.04), (.12, 2.5, .01), 'lane')
    box('yellow line a', (2.95, 30, -.04), (.08, 80, .01), 'yline')
    box('yellow line b', (3.1, 30, -.04), (.08, 80, .01), 'yline')
    box('grass verge', (-4.5, 30, -.02), (4, 80, .1), 'grass')
    box('walkway roof', (-2.3, 6, 3.0), (1.6, 14, .15), 'roof')
    for y in range(0, 14, 4):
        box(f'roof pillar {y}', (-1.65, y, 1.5), (.18, .18, 3.0), 'pillar')
    box('railing', (-3.2, 18, .5), (.06, 30, 1.0), 'rail')
    for i, y in enumerate((14, 24, 34, 44)):
        tree(f'rain tree {i}', 2.25 if i % 2 else -3.5, y)
    tree('rain tree near', 4.0, 9, 7)
    hdb('HDB block A', -14, 26, 12, 12, 30)
    hdb('HDB block B', 16, 40, 12, 10, 27)
    hdb('HDB block end', 0, 70, 30, 8, 33)
    cyl('yellow marker', (.2, 7.75, .005), .45, .02, 'marker', 16)
    box('entrance frame', (-1.6, 9.6, 1.3), (.2, .2, 2.6), 'pillar')
    box('bin', (-1.3, 3.0, .45), (.4, .4, .9), 'rail')

    girl = Figure('GG01 proxy', 1.65, GIRL)
    n1 = Figure('NPC01 proxy commuter', 1.72, NPC1)
    n2 = Figure('NPC02 proxy passer-by', 1.68, NPC2)
    bag = handbag()
    gy = lambda t: linear([(0, 0), (.2, 0), (6.6, 7.36), (7.0, 7.75)], t)
    gm = Motion(girl, lambda t: (.2, gy(t)), lambda t: 0.0, walk_steps(.2, 6.7, 'R') + [(7.1, 'R')], lateral=.1)
    gm.head_turn = lambda t: 0
    m1 = Motion(n1, lambda t: (1.35, linear([(0, 6.4), (8, 6.4 - 1.3 * 8)], t)), lambda t: math.pi,
                walk_steps(-.25, 8.2, 'L'), lateral=.11)
    cross_y = 3.6
    n2x = lambda t: linear([(0, -2.8), (2.4, -2.8), (5.9, 1.95), (8, 1.95)], t)
    m2 = Motion(n2, lambda t: (n2x(t), cross_y), lambda t: interp([(0, -math.pi / 2), (5.6, -math.pi / 2), (6.1, -math.pi)], t),
                walk_steps(2.4, 5.9, 'L', .52), lateral=.1)
    cam = camera((.45, -3.3, 1.75), (.2, 2, 1.1), hfov=46)
    for fr in range(n):
        t = fr / FPS
        y = gy(t)
        set_cam(cam, (.45, y - 3.3, 1.75), (.2, y + 2.2, 1.05), fr)
    light((math.radians(48), math.radians(8), math.radians(140)), 2.6, (.5, .62, .72))
    return n, [gm, m1, m2], dict(bag=bag, girl=girl, carry=True), cam


def scene_t03():
    """Treatment room. GG-01 does slow bodyweight squats facing the camera;
    GP-01 watches, nods, claps twice, gives a thumbs-up gesture. Camera arcs
    slowly throughout so the 15 s tail is moving. 532 frames (native 0-361,
    continuation guide 340-531)."""
    n = 532
    box('floor', (0, 3, -.01), (7, 8, .02), 'floorwood')
    box('back wall', (0, 5.6, 1.6), (7, .1, 3.2), 'wallcream')
    box('left wall', (-3.0, 3, 1.6), (.1, 8, 3.2), 'wall')
    box('exercise mat', (0, 3.0, .005), (1.1, 1.9, .01), 'mat')
    box('plinth top', (-1.6, 4.8, .65), (1.9, .7, .12), 'plinth')
    for x in (-2.4, -.8):
        box('plinth leg', (x, 4.8, .3), (.1, .5, .6), 'plinth')
    box('wall bars', (1.6, 5.5, 1.2), (1.2, .06, 2.4), 'wood')
    for z in range(1, 9):
        box(f'wall bar {z}', (1.6, 5.45, z * .27), (1.2, .05, .04), 'shelf')
    box('ball', (2.3, 4.9, .3), (.6, .6, .6), 'goji', rot=(0, 0, .3))
    box('logo panel', (-1.4, 5.53, 2.1), (1.2, .04, .4), 'cream')

    girl = Figure('GG01 proxy', 1.65, GIRL)
    ther = Figure('GP01 proxy', 1.58, THERAPIST)
    girl_h = math.pi
    gm = Motion(girl, lambda t: (0, 3.0), lambda t: girl_h, [], lateral=.17)
    gm.lat = .17
    period, start = 2.6, 1.0

    def sq(t):
        if t < start:
            return 0.0
        u = ((t - start) % period) / period
        return .5 - .5 * math.cos(2 * math.pi * u)
    gm.drop = lambda t: .36 * sq(t)
    gm.hipback = lambda t: .2 * sq(t)
    gm.lean = lambda t: .45 * sq(t)
    for k, s in (('L', -1), ('R', 1)):
        def hand(t, s=s):
            u = sq(t)
            local = Vector((s * .2, .05 + .5 * u, .80 + .55 * u)) * girl.scale
            return gm.world(local, t) + Vector((0, 0, -.36 * u)) + heading_mat(girl_h).to_3x3() @ Vector((0, -.2 * u, 0))
        gm.hand[k] = hand
    tdir = 1.95  # faces (-0.93,-0.37): toward GG-01 and camera
    tm = Motion(ther, lambda t: (1.35, 3.35), lambda t: tdir, [], lateral=.12)
    tm.nod = lambda t: interp([(0, 0), (5.5, 0), (5.8, .2), (6.1, 0), (6.4, .2), (6.7, 0)], t)

    def clap(t, side):
        s = 1 if side == 'R' else -1
        rest = Vector((s * .25, .02, .80))
        c = Vector((s * .03, .32, 1.15))
        o = Vector((s * .17, .30, 1.17))
        keys = [(0, rest), (9.0, rest), (9.5, o), (9.75, c), (10.0, o), (10.25, c), (10.6, o), (11.2, rest),
                (16.0, rest), (16.6, Vector((s * .2, .3, 1.05)) if s < 0 else rest),
                (17.0, Vector((s * .22, .34, 1.3)) if s < 0 else rest),
                (19.0, Vector((s * .22, .34, 1.3)) if s < 0 else rest), (19.8, rest)]
        v = interp([(k, tuple(x)) for k, x in keys], t)
        return tm.world(Vector(v) * ther.scale, t)
    tm.hand['L'] = lambda t: clap(t, 'L')
    tm.hand['R'] = lambda t: clap(t, 'R')
    tm.head_turn = lambda t: 0
    cam = camera((-1.2, -1.2, 1.5), (.4, 3.1, .95), hfov=44)
    for fr in range(n):
        t = fr / FPS
        a = math.radians(-18 + 30 * t / (n / FPS))
        c = Vector((.45, 3.1, 0))
        pos = c + Vector((3.3 * math.sin(a), -3.3 * math.cos(a), 1.35))
        set_cam(cam, tuple(pos), (.45, 3.1, .88), fr)
    light((math.radians(55), 0, math.radians(-25)), 1.6, (.55, .52, .46))
    pt = bpy.data.lights.new('ceiling', 'AREA')
    pt.energy, pt.size = 140, 3
    po = bpy.data.objects.new('ceiling', pt)
    bpy.context.collection.objects.link(po)
    po.location = (0, 3, 3.1)
    return n, [gm, tm], dict(girl=girl), cam


n, motions, extra, cam = {'t01': scene_t01, 't02': scene_t02, 't02v2': lambda: scene_t02(True), 't03': scene_t03}[SCENE]()
sc = bpy.context.scene
sc.render.fps = FPS
sc.frame_start, sc.frame_end = 0, n - 1
for fr in range(n):
    for mo in motions:
        apply_motion(mo, fr, fr / FPS)

# Bag: held by the left-hand grip, then rigidly at rest on the table after release.
bag = extra.get('bag')
records = []
for fr in range(n):
    sc.frame_set(fr)
    t = fr / FPS
    rec = {'frame': fr, 't': round(t, 4)}
    for mo in motions:
        f = mo.fig
        rec[f.name] = {
            'root': [round(v, 4) for v in f.arm.location[:2]], 'heading': round(f.arm.rotation_euler.z, 4),
            'hand.L': [round(v, 4) for v in f.bone_world('hand.L')], 'hand.R': [round(v, 4) for v in f.bone_world('hand.R')],
            'foot.L': [round(v, 4) for v in f.bone_world('foot.L', 'head')], 'foot.R': [round(v, 4) for v in f.bone_world('foot.R', 'head')],
            'head': [round(v, 4) for v in f.bone_world('head')]}
    if bag:
        g = extra['girl']
        grip = g.bone_world('hand.L')
        loc = grip - Vector((0, 0, .235))
        if 'bag_rest' in extra and not extra.get('contact') and t > 3.0 and loc.z <= extra['bag_rest'].z + .004:
            extra['contact'] = fr
            extra['bag_rest'] = Vector((loc.x, loc.y, extra['bag_rest'].z))
        released = bool(extra.get('contact'))
        if released:
            loc = extra['bag_rest']
        bag.location = loc
        bag.rotation_euler = (0, 0, g.arm.rotation_euler.z)
        bag.keyframe_insert('location', frame=fr)
        bag.keyframe_insert('rotation_euler', frame=fr)
        rec['bag'] = {'base': [round(v, 4) for v in loc], 'held': not released,
                      'grip_gap_m': round((grip - (Vector(loc) + Vector((0, 0, .235)))).length, 4)}
    rec['camera'] = {'loc': [round(v, 4) for v in cam.matrix_world.translation]}
    records.append(rec)

cam_data = cam.data
meta = {'scene': SCENE, 'frames': n, 'fps': FPS, 'resolution': [sc.render.resolution_x, sc.render.resolution_y],
        'camera': {'lens_mm': cam_data.lens, 'sensor_width_mm': cam_data.sensor_width, 'sensor_fit': cam_data.sensor_fit},
        'blender': bpy.app.version_string, 'units': 'metres, Z up', 'frame_index': 'Blender frame f = video index f, t = f/24',
        'proxies': 'All figures are labelled proxies, not reviewed cast assets.'}
meta['bag_table_contact_frame'] = extra.get('contact')
(OUT / 'stage.json').write_text(json.dumps({'meta': meta, 'frames': records}))
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / f'{SCENE}.blend'))

sc.render.engine = 'BLENDER_EEVEE'
sc.view_settings.view_transform = 'Standard'
sc.render.image_settings.file_format = 'PNG'
sc.render.film_transparent = False
CLAY = '--clay' in argv
if CLAY:
    # NPC clay: same geometry and light, no colour cues on the NPC proxies for the
    # generator to copy (tests proxy-appearance leakage on subjects with no reference image).
    cm = bpy.data.materials.new('clay')
    cm.use_nodes = True
    cm.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (.62, .62, .62, 1)
    cm.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value = .9
    # Only the NPC proxies (no reference image) become clay; leads, bag and set keep their colours.
    for o in bpy.data.objects:
        if o.type == 'MESH' and o.name.startswith('NPC0'):
            o.data.materials.clear()
            o.data.materials.append(cm)
    OUT = OUT.parent / f'{SCENE}clay'
    OUT.mkdir(exist_ok=True)
if RENDER != 'none':
    frames = range(n) if RENDER == 'all' else [int(x * (n - 1) / 7) for x in range(8)]
    (OUT / 'frames').mkdir(exist_ok=True)
    for fr in frames:
        sc.frame_set(fr)
        sc.render.filepath = str(OUT / 'frames' / f'{fr:04d}.png')
        bpy.ops.render.render(write_still=True)
    if DEPTH:
        # Fixed-range depth (near = white), identical mapping for every frame.
        near, far = {'t01': (1.0, 30.0), 't02': (1.5, 7.0), 't02v2': (1.5, 7.0), 't03': (2.0, 7.5)}[SCENE]
        dm = bpy.data.materials.new('depth override')
        dm.use_nodes = True
        nt = dm.node_tree
        nt.nodes.clear()
        cd = nt.nodes.new('ShaderNodeCameraData')
        mr = nt.nodes.new('ShaderNodeMapRange')
        mr.inputs['From Min'].default_value, mr.inputs['From Max'].default_value = near, far
        mr.inputs['To Min'].default_value, mr.inputs['To Max'].default_value = 1.0, 0.0
        em = nt.nodes.new('ShaderNodeEmission')
        out = nt.nodes.new('ShaderNodeOutputMaterial')
        nt.links.new(cd.outputs['View Z Depth'], mr.inputs['Value'])
        nt.links.new(mr.outputs['Result'], em.inputs['Color'])
        nt.links.new(em.outputs['Emission'], out.inputs['Surface'])
        sc.view_layers[0].material_override = dm
        sc.view_settings.view_transform = 'Raw'
        sc.world.node_tree.nodes['Background'].inputs['Strength'].default_value = 0
        (OUT / 'depth').mkdir(exist_ok=True)
        for fr in frames:
            sc.frame_set(fr)
            sc.render.filepath = str(OUT / 'depth' / f'{fr:04d}.png')
            bpy.ops.render.render(write_still=True)
print('STAGED', SCENE, n)
