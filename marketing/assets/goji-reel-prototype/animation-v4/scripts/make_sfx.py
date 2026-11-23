"""Original, dry PS2-era game-style effects; no music or sampled game assets."""
from pathlib import Path
import json, wave
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'audio'
OUT.mkdir(exist_ok=True)
SR = 48000
edit=json.loads((ROOT/'edit-timeline.json').read_text())
D=edit['duration']
T={x['shot']:x['start'] for x in edit['shots']}
rng = np.random.default_rng(20261122)
stems = {k: np.zeros((int(SR*D),2),np.float32) for k in ['footsteps','vehicles','impact','interior','ui']}
cues=[]
def tone(d,f,decay=0):
    t=np.arange(int(d*SR))/SR
    return np.sin(2*np.pi*f*t)*np.exp(-decay*t)
def noise(d,smooth=1):
    x=rng.standard_normal(int(d*SR))
    if smooth>1:
        cs=np.cumsum(np.r_[0,x]);x=(cs[smooth:]-cs[:-smooth])/smooth
        x=np.pad(x,(0,smooth-1))
    return x
def env(x,attack=.003,decay=12):
    t=np.arange(len(x))/SR
    return x*np.minimum(t/attack,1)*np.exp(-decay*t)
def add(stem,at,x,gain=1,pan=0,label=''):
    n=min(len(x),int(SR*D)-int(at*SR));i=int(at*SR)
    stereo=np.stack([x[:n]*np.sqrt((1-pan)/2),x[:n]*np.sqrt((1+pan)/2)],axis=1)
    stems[stem][i:i+n]+=gain*stereo
    if label:cues.append(dict(time=at,stem=stem,label=label))
def foot():return env(.65*tone(.16,95)+.18*noise(.16,5),decay=28)
def clack():return env(.25*noise(.2,2)+.45*tone(.2,420)+.2*tone(.2,1130),decay=35)
def chime():
    t=np.arange(int(.28*SR))/SR
    # A single brief UI notification, not a melody or music bed.
    return .7*np.sin(2*np.pi*1100*t)*np.exp(-18*t)+.15*np.sin(2*np.pi*2200*t)*np.exp(-26*t)
def motor(d,base=50):
 t=np.arange(int(d*SR))/SR;f=base+55*(t/d)**.7;phase=2*np.pi*np.cumsum(f)/SR
 x=sum(np.sin(phase*k)*(.65/k) for k in range(1,9))+.08*noise(d,8)
 return x*np.minimum(t/.04,1)*np.minimum((d-t)/.06,1)
def skid(d=.5):
 t=np.arange(int(d*SR))/SR
 return (np.sin(2*np.pi*(950*t+180*t*t)+.8*np.sin(2*np.pi*39*t))+.4*noise(d,2))*np.sin(np.pi*t/d)**.7
def horn(d=.24):return env(tone(d,390)+.55*tone(d,510),.008,2)
for n,at in enumerate([.12,.52,.94,1.36]):add('footsteps',at,foot(),.24,(-1)**n*.12,'swagger footstep')
add('vehicles',0,env(noise(1.1,8),.01,3),.07,-.3,'bus air brake')
t=T['02-takeover'];add('vehicles',t+.03,clack(),.35,.2,'door latch')
add('footsteps',t+.5,env(noise(.7,16),.02,3),.13,.2,'driver pull scuffle')
for offset in [1.1,1.35]:add('impact',t+offset,env(.7*tone(.2,75)+.2*noise(.2,7),decay=17),.19,.3,'harmless driver roll')
add('vehicles',T['03-drive']-.08,clack(),.3,0,'door slam at edit')
t=T['03-drive']
for at,d,g in [(t,1.6,.22),(t+1.6,1.5,.25),(t+3.1,1.5,.28),(t+4.6,1.7,.32)]:add('vehicles',at,motor(d),g,0,'accelerating engine and gear change')
for n,off in enumerate([1.5,3.4,5.2]):
 pan=(-1)**n*.65
 add('vehicles',t+off,skid(.3+off*.035),.065+off*.008,pan,'swerve tyre squeal')
 add('vehicles',t+off+.08,env(noise(.45,16),.08,6),.13,pan,'close traffic pass')
 add('vehicles',t+off+.13,horn(.18+.02*n),.07, -pan,'alarmed traffic horn')
impact=T['04-crash-eject']+.95
add('vehicles',T['04-crash-eject'],skid(.65),.14,-.15,'kerb approach skid')
crash=env(noise(.65,4),.001,9)*.75+env(tone(.65,54),.001,11)*.9
add('impact',impact,crash,.58,0,'hard lamp-post contact')
add('impact',impact+.02,sum(tone(.6,f,8+f/600) for f in [510,817,1331,2103])/4,.18,-.15,'lamp post clang')
for n in range(17):add('impact',impact+.08+n*.012,env(tone(.17,float(rng.uniform(2300,8500)))+.15*noise(.17),decay=50),.035,float(rng.uniform(-.3,.3)),'glass fragments' if n==0 else '')
t=T['05-recovery']-.5;add('impact',t,env(noise(.6,14),.06,4),.14,.1,'continuous ejection whoosh')
for off,pan in [(.22,-.7),(.45,.7)]:add('impact',t+off,env(noise(.45,15),.06,5),.10,pan,'pedestrians dive clear')
add('impact',T['05-recovery']+.9,env(.7*tone(.2,85)+.2*noise(.2,6),decay=22),.18,.15,'soft pavement tumble')
if '05-recovery' in T:
 t=T['05-recovery'];add('footsteps',t+1.0,env(noise(.5,16),.05,4),.08,.1,'push up from pavement')
 for n in range(9):add('footsteps',t+2.15+n*.24,foot(),.2,(-1)**n*.1,'run toward mall')
for n in range(8):add('footsteps',T['06-marker']+.1+n*.23,foot(),.22,(-1)**n*.1,'running to entrance')
cut=T['black-transition'];add('ui',cut-.1,chime(),.11,0,'entry trigger')
for key in ['footsteps','vehicles','impact','ui']:stems[key][int(cut*SR):]=0
add('interior',T['07-entry']+.05,clack(),.06,.1,'quiet reception door')
for off in [.35,.95,1.5]:add('interior',T['07-entry']+off,foot(),.06,.05,'calm indoor step')
for off in [.6,2.8]:add('interior',T['08a-warrior']+off,env(noise(.85,70),.12,3),.018,-.1,'quiet stretch clothing')
for off in [.4,2.8,4.7]:add('interior',T['08b-mat']+off,env(noise(.8,100),.2,3),.012,0,'assisted stretching clothing')
add('ui',D-5.5,chime(),.15,-.1,'Body Muscle upgraded notification')
for off in [.8,2.8,4.8]:add('interior',T['09-squat']+off,env(noise(.7,100),.12,3),.014,0,'quiet squat clothing')
mix=sum(stems.values());peak=float(np.abs(mix).max());gain=min(1,.75/peak)
def write(path,data):
 with wave.open(str(path),'wb') as f:
  f.setnchannels(2);f.setsampwidth(2);f.setframerate(SR);f.writeframes((np.clip(data,-1,1)*32767).astype('<i2').tobytes())
for name,data in stems.items():write(OUT/(name+'.wav'),data*gain)
write(OUT/'goji-sfx-only.wav',mix*gain)
(OUT/'cue-sheet.json').write_text(json.dumps(cues,indent=2))
print('Original SFX only,',D,'seconds; peak',round(20*np.log10(peak*gain),1),'dBFS')
