"""Geometry checks on original choreography; not a claim of measured GTA physics."""
import json,math,hashlib
from pathlib import Path
from stunt_motion import chase_pose,crash_pose
R=Path(__file__).resolve().parents[1]
def hull(points):
 p=sorted(set(points))
 def cross(o,a,b):return (a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0])
 lo=[];hi=[]
 for a in p:
  while len(lo)>1 and cross(lo[-2],lo[-1],a)<=0:lo.pop()
  lo.append(a)
 for a in p[::-1]:
  while len(hi)>1 and cross(hi[-2],hi[-1],a)<=0:hi.pop()
  hi.append(a)
 return lo[:-1]+hi[:-1]
def distance(p,poly):
 ds=[]
 for a,b in zip(poly,poly[1:]+poly[:1]):
  dx=b[0]-a[0];dy=b[1]-a[1];u=max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/(dx*dx+dy*dy)))
  ds.append(math.hypot(p[0]-a[0]-u*dx,p[1]-a[1]-u*dy))
 return min(ds)
clearance=100;wall_x=100;peak=0;last=None
for i in range(601):
 t=i/120;xy,yaw,roll,phase=crash_pose(t)
 if last:peak=max(peak,math.dist(xy,last)*120)
 last=xy;pts=[]
 for x in [-1.45,1.45]:
  for y in [-6.1,6.1]:
   for z in [0,4.65]:
    xx=x*math.cos(roll)+z*math.sin(roll)
    pts.append((xy[0]+xx*math.cos(yaw)-y*math.sin(yaw),xy[1]+xx*math.sin(yaw)+y*math.cos(yaw)))
 poly=hull(pts)
 for npc in [(-8.6,8),(-8.7,12),(-8.8,28.4),(-6,30.5)]:clearance=min(clearance,distance(npc,poly)-.35)
 for x,y in pts:
  if -21<y<41:wall_x=min(wall_x,x)
assert clearance>.5,clearance
assert wall_x> -9.7,wall_x
exit_audit=json.loads((R/'guides/08-contact-audit.json').read_text());assert not exit_audit['violations']
checks={'basis':'Original proposed kinematic staging; no extracted game data or validated real-vehicle simulation','chase_forward_travel_metres':chase_pose(5)[0][1]-chase_pose(0)[0][1],'chase_duration_seconds':5,'chase_forward_speed_mps':22,'chase_forward_speed_kph':79.2,'crash_peak_speed_mps':peak,'wall_minimum_x':wall_x,'wall_limit_x':-9.7,'minimum_projected_bus_to_npc_body_clearance_m':clearance,'exit_limb_reach_violations':len(exit_audit['violations']),'scene08_end_root':[-7.35,4.4,.13],'scene09_start_root':[-7.35,4.4,.13],'limitations':['Projected conservative bus body bounds, fixed NPC marks; generated motion must be reviewed separately.','Reach audit checks limb lengths; it does not prove skin-level collision or model output contacts.','Canopy supports intentionally break; this is exaggerated game choreography.']}
(R/'guides/motion-audit.json').write_text(json.dumps(checks,indent=2)+'\n');print(json.dumps(checks,indent=2))
