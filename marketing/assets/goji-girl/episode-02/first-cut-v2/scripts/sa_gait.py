"""Original rig motion informed by sampled PS2 footage, not extracted game data."""
import math
from mathutils import Vector,Matrix

def sa_run_pose(actor,frame,position,heading,time,move_segment,speed=3.75,phase_offset=0):
    period=.50
    cycle=time/period+phase_offset
    lean=math.radians(11)
    bob=.022*(1-math.cos(4*math.pi*cycle))
    root=Vector(position)+Vector((0,0,bob))
    actor.pose(frame,root,heading)
    actor.root.rotation_euler=(-lean,0,heading)
    actor.root.keyframe_insert('rotation_euler',frame=frame)
    inverse_lean=Matrix.Rotation(lean,3,'X')
    amplitude=min(.46,max(.22,speed*period*.48/2))
    def lerp(a,b,u):return a+(b-a)*u
    def ease(u):return u*u*(3-2*u)
    for side in [-1,1]:
        phase=(cycle+(0 if side==1 else .5))%1
        if phase<.48:
            fy=lerp(amplitude,-amplitude,phase/.48);fz=.08
        elif phase<.70:
            u=ease((phase-.48)/.22);fy=lerp(-amplitude,-.22,u);fz=lerp(.08,.62,u)
        elif phase<.86:
            u=ease((phase-.70)/.16);fy=lerp(-.22,amplitude*.88,u);fz=lerp(.62,.32,u)
        else:
            u=ease((phase-.86)/.14);fy=lerp(amplitude*.88,amplitude,u);fz=lerp(.32,.08,u)
        hip=Vector((side*.115,0,.88))
        ankle=inverse_lean@Vector((side*.13,fy,fz-bob))
        direction=ankle-hip;length=min(.919,max(.05,direction.length))
        midpoint=(ankle+hip)*.5
        normal=Vector((0,-direction.z,direction.y)).normalized()
        knee=midpoint+normal*math.sqrt(max(0,.46**2-(length/2)**2))
        move_segment(actor.parts[(side,'thigh')],hip,knee,frame)
        move_segment(actor.parts[(side,'calf')],knee,ankle,frame)
        shoe=actor.parts[(side,'shoe')]
        shoe.location=ankle+Vector((0,.07,-.035));shoe.rotation_euler.x=lean+.13*math.sin(2*math.pi*phase)
        shoe.keyframe_insert('location',frame=frame);shoe.keyframe_insert('rotation_euler',frame=frame)
        swing=-math.cos(2*math.pi*phase)
        shoulder=Vector((side*.235,0,1.35))
        # Both arms use the SAME full pump. Holding a rigid prop never dampens
        # the left shoulder/elbow cycle. Angles are original Goji staging.
        arm_angle=math.radians(52)*swing
        elbow=shoulder+Vector((side*.10,.28*math.sin(arm_angle),-.28*math.cos(arm_angle)))
        wrist=elbow+Vector((-side*.035,.25*math.sin(arm_angle+math.pi/2),-.25*math.cos(arm_angle+math.pi/2)))
        move_segment(actor.parts[(side,'upperarm')],shoulder,elbow,frame)
        move_segment(actor.parts[(side,'forearm')],elbow,wrist,frame)
        hand=actor.parts[(side,'hand')];hand.location=wrist+Vector((0,0,-.035));hand.keyframe_insert('location',frame=frame);hand.rotation_euler.x=arm_angle;hand.keyframe_insert('rotation_euler',frame=frame)
        if side==-1 and actor.bag:
            actor.bag.location=wrist;actor.bag.rotation_euler=(arm_angle,0,0);actor.bag.scale=(1,1,1)
            for channel in ['location','rotation_euler','scale']:actor.bag.keyframe_insert(channel,frame=frame)
