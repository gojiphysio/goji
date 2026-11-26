"""Original GTA-like stunt choreography. Units: metres, seconds, radians.
Not a measured vehicle simulator. Travel, load, contact and impact are distinct.
"""
import math
WRECK_X=-6.5
WRECK_Y=0.0
WRECK_ROLL=math.radians(94)
IMPACT_TIME=3.15

def clamp(v,a=0.,b=1.):return max(a,min(b,v))
def smooth(u):u=clamp(u);return u*u*(3-2*u)
def ramp(t,a,b,x,y):return x+(y-x)*smooth((t-a)/(b-a))
def hermite(t,marks):
 if t<=marks[0][0]:return list(marks[0][1])
 if t>=marks[-1][0]:return list(marks[-1][1])
 for a,b in zip(marks,marks[1:]):
  if a[0]<=t<=b[0]:
   dt=b[0]-a[0];u=(t-a[0])/dt
   return [(2*u**3-3*u*u+1)*pa+(u**3-2*u*u+u)*dt*va+(-2*u**3+3*u*u)*pb+(u**3-u*u)*dt*vb for pa,pb,va,vb in zip(a[1],b[1],a[2],b[2])]

def chase_xy(t):
 t=clamp(t,0,5)
 env=smooth(t/.35)*smooth((5-t)/.35)
 return [-2.8+1.05*math.sin(2*math.pi*t/1.7)*env,-176+22*t]

def chase_pose(t):
 h=.002;a=chase_xy(max(0,t-h));p=chase_xy(t);b=chase_xy(min(5,t+h))
 dx=(b[0]-a[0])/(min(5,t+h)-max(0,t-h));yaw=math.atan2(-dx,22)
 acc=(b[0]-2*p[0]+a[0])/(h*h) if h<t<5-h else 0
 roll=max(-math.radians(11),min(math.radians(11),-acc/9.81*math.radians(7)))
 return p,yaw,roll

CRASH_PATH=[
 (0,(-2.8,-66),(0,22)),
 (1.0,(-2.8,-44),(0,22)),
 (1.45,(-3.2,-34.2),(-2.2,21)),
 (1.95,(-4.8,-23.6),(-4,20)),
 (2.4,(-6.4,-15.2),(-3,17)),
 (3.15,(-7.0,-3.1),(.5,15)),
 (3.35,(-6.7,-.2),(1,.8)),
 (3.60,(WRECK_X,WRECK_Y),(0,0)),
 (5.0,(WRECK_X,WRECK_Y),(0,0)),
]

def crash_pose(t):
 p=hermite(t,CRASH_PATH)
 if t<1.08:yaw=0
 elif t<1.38:yaw=ramp(t,1.08,1.38,0,46)
 elif t<2.1:yaw=ramp(t,1.38,2.1,46,28)
 elif t<3.15:yaw=ramp(t,2.1,3.15,28,20)
 elif t<3.35:yaw=ramp(t,3.15,3.35,20,-3)
 else:yaw=ramp(t,3.35,3.60,-3,0)
 if t<1.2:roll=ramp(t,1.08,1.2,0,4)
 elif t<1.45:roll=ramp(t,1.2,1.45,4,14)
 elif t<1.95:roll=14+82*((t-1.45)/.5)**2
 elif t<2.07:roll=ramp(t,1.95,2.07,96,91)
 elif t<2.22:roll=ramp(t,2.07,2.22,91,94)
 else:roll=94
 phase='fast approach' if t<1.08 else 'hard left steer' if t<1.45 else 'outside-wheel pivot and roll' if t<1.95 else 'ground strike and fast slide' if t<3.15 else 'mall-side impact' if t<3.6 else 'wreck settled'
 return p,math.radians(yaw),math.radians(roll),phase
