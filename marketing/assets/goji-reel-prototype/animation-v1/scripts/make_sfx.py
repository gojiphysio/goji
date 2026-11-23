"""Original, dry PS2-era game-style effects; no music or sampled game assets."""
from pathlib import Path
import json, wave
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'audio'
OUT.mkdir(exist_ok=True)
SR = 48000
rng = np.random.default_rng(20261122)
stems = {k: np.zeros((SR*20,2),np.float32) for k in ['footsteps','vehicles','impact','interior','ui']}
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
    n=min(len(x),SR*20-int(at*SR));i=int(at*SR)
    stereo=np.stack([x[:n]*np.sqrt((1-pan)/2),x[:n]*np.sqrt((1+pan)/2)],axis=1)
    stems[stem][i:i+n]+=gain*stereo
    if label:cues.append(dict(time=at,stem=stem,label=label))
def foot():return env(.65*tone(.16,95)+.18*noise(.16,5),decay=28)
def clack():return env(.25*noise(.2,2)+.45*tone(.2,420)+.2*tone(.2,1130),decay=35)
def chime():
    t=np.arange(int(.28*SR))/SR
    # A single brief UI notification, not a melody or music bed.
    return .7*np.sin(2*np.pi*1100*t)*np.exp(-18*t)+.15*np.sin(2*np.pi*2200*t)*np.exp(-26*t)
for n,at in enumerate([.12,.52,.94,1.36]):add('footsteps',at,foot(),.24,(-1)**n*.12,'swagger footstep')
add('vehicles',0,env(noise(1.1,8),.01,3),.07,-.3,'bus air-brake hiss')
add('vehicles',1.83,clack(),.38,.15,'door latch and swing')
add('vehicles',2.15,env(noise(.28,50),.02,10),.09,.15,'door creak')
add('footsteps',2.5,env(noise(.3,12),.01,9),.1,.2,'clothing scuffle')
add('impact',3.04,env(.7*tone(.25,70)+.2*noise(.25,7),decay=17),.25,.25,'harmless shoulder-roll thud')
add('vehicles',3.5,clack(),.35,.05,'taxi door closes')
d=2.85;t=np.arange(int(d*SR))/SR;f=48+48*(t/d)**.8
phase=2*np.pi*np.cumsum(f)/SR
motor=sum(np.sin(phase*k)*(.7/k) for k in range(1,8))
motor=(motor+.06*noise(d,12))*(.75+.25*np.sin(2*np.pi*11*t))
motor*=np.minimum(t/.1,1)*np.minimum((d-t)/.08,1)
add('vehicles',3.6,motor,.22,0,'engine accelerates')
d=.56;t=np.arange(int(d*SR))/SR
skid=(np.sin(2*np.pi*(850*t+130*t*t)+.6*np.sin(2*np.pi*37*t))+.25*noise(d,2))*np.sin(np.pi*t/d)**.8
add('vehicles',5.72,skid,.1,-.1,'short tyre squeal')
crash=env(noise(.65,4),.001,9)*.75+env(tone(.65,54),.001,11)*.9
add('impact',6.22,crash,.58,0,'compact metal crash')
clang=sum(tone(.6,f,8+f/600) for f in [510,817,1331,2103])/4
add('impact',6.24,clang,.18,-.15,'lamp-post clang')
for n in range(17):
    add('impact',6.42+n*.012,env(tone(.17,float(rng.uniform(2300,8500)))+.15*noise(.17),decay=50),.035,float(rng.uniform(-.3,.3)), 'glass fragments' if n==0 else '')
add('impact',6.5,env(noise(.55,14),.1,5),.1,.2,'ejection whoosh')
add('impact',7.28,env(.7*tone(.2,85)+.2*noise(.2,6),decay=22),.2,.15,'soft landing')
for n,at in enumerate([7.48,7.73,7.98,8.23,8.48,8.73,8.98,9.23]):add('footsteps',at,foot(),.22,(-1)**n*.1,'run footstep')
add('ui',9.28,chime(),.11,0,'entry trigger')
# Cut exterior effects cleanly at loading transition, leaving room silence.
for key in ['footsteps','vehicles','impact','ui']:
    stems[key][int(9.4*SR):]=0
add('interior',9.87,clack(),.07,.1,'quiet reception door')
for at in [10.15,10.75,11.25]:add('interior',at,foot(),.07,.05,'calm indoor step')
for at in [12.0,13.6]:
    add('interior',at,env(noise(.85,70),.12,3),.018,-.1,'soft reformer carriage')
for at in [15.2,17.5]:add('interior',at,env(noise(.8,100),.2,3),.012,0,'quiet clothing movement')
add('ui',18.3,chime(),.15,-.1,'strength notification')
add('ui',19.1,chime(),.15,-.1,'mobility notification')
mix=sum(stems.values());peak=float(np.abs(mix).max());gain=min(1,.75/peak)
def write(path,data):
    with wave.open(str(path),'wb') as f:
        f.setnchannels(2);f.setsampwidth(2);f.setframerate(SR)
        f.writeframes((np.clip(data,-1,1)*32767).astype('<i2').tobytes())
for name,data in stems.items():write(OUT/(name+'.wav'),data*gain)
write(OUT/'goji-sfx-only.wav',mix*gain)
(OUT/'cue-sheet.json').write_text(json.dumps(cues,indent=2))
print('Created original sound-effects mix and five stems, exactly 20s; peak',round(20*np.log10(peak*gain),1),'dBFS. No music.')
