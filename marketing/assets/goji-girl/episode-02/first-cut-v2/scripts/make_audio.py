"""Original procedural SFX; independent editable stems, no music or voice clone."""
from pathlib import Path
import numpy as np,wave,json
R=Path(__file__).resolve().parents[1];SR=48000;D=49;N=SR*D;rng=np.random.default_rng(20261126)
stems={k:np.zeros((N,2),dtype=np.float32) for k in ['foley','vehicles','ui','clinic']};events=[]
def add(stem,start,signal,gain=1,pan=0,label=''):
 i=int(start*SR);v=np.asarray(signal,dtype=np.float32)*gain;n=min(len(v),N-i)
 if n<=0:return
 env=np.ones(n);fade=min(240,n//4);env[:fade]=np.linspace(0,1,fade);env[-fade:]=np.linspace(1,0,fade);v=v[:n]*env
 stems[stem][i:i+n,0]+=v*np.sqrt((1-pan)/2);stems[stem][i:i+n,1]+=v*np.sqrt((1+pan)/2)
 events.append({'stem':stem,'start':start,'duration':n/SR,'label':label})
def tone(sec,freq):return np.sin(2*np.pi*freq*np.arange(int(sec*SR))/SR)
def hit(sec=.15,low=100):
 t=np.arange(int(sec*SR))/SR;return (.55*np.sin(2*np.pi*low*t)+.28*rng.normal(size=len(t)))*np.exp(-t*25)
def noise(sec):
 a=rng.normal(size=int(sec*SR));return np.convolve(a,np.ones(15)/15,mode='same')
for t in [.4,.85,1.2]:add('foley',t,hit(.08,450),.10,label='impatient desk tap')
add('foley',2.0,hit(.4,400),.25,label='headset clatter');add('foley',2.7,hit(.25,100),.60,label='laptop shut')
add('ui',3.2,tone(.12,880)*np.linspace(1,0,int(.12*SR)),.25,label='calendar ping');add('ui',3.34,tone(.18,1320)*np.linspace(1,0,int(.18*SR)),.17,label='calendar second tone')
add('foley',5.15,hit(.35,75),.45,label='front door bang')
for start,end,step in [(5.25,11,.25),(35.0,38.9,.25)]:
 for k,t in enumerate(np.arange(start,end,step)):add('foley',float(t),hit(.13,85+(k%2)*15),.16,(-.12 if k%2 else .12),label='player running')
for off,pan in [(.1,-.5),(.23,.5)]:
 for t in np.arange(35+off,38.85,.25):add('foley',float(t),hit(.14,65),.14,pan,label='pursuer footsteps')
t=np.arange(int(13.6*SR))/SR;engine=(np.sin(2*np.pi*(44*t+2.1*t*t))+.35*np.sin(2*np.pi*88*t)+.15*noise(13.6))*.09
add('vehicles',10,engine,label='diesel idle and acceleration')
add('vehicles',11.4,noise(.18),.10,label='bus air hiss')
add('foley',11.4,noise(.5)*np.exp(-np.arange(int(.5*SR))/SR*8)+tone(.5,3200)*np.exp(-np.arange(int(.5*SR))/SR*15),.22,label='driver window break')
for start,sec,gain in [(16,8.7,.055),(33.4,5.6,.065)]:
 t=np.arange(int(sec*SR))/SR;freq=850+380*np.sin(2*np.pi*.8*t);sig=np.sin(2*np.pi*np.cumsum(freq)/SR)+.22*np.sin(4*np.pi*np.cumsum(freq)/SR)
 add('vehicles',start,sig,gain,-.3,label='offscreen police siren')
add('vehicles',19.1,tone(.5,190)+.4*tone(.5,260),.10,label='bus horn')
t=np.arange(int(3.2*SR))/SR;add('vehicles',21.1,noise(3.2)*.5+np.sin(2*np.pi*(1300*t+80*np.sin(t*3)))*.2,.14,label='tyre squeal and scrape')
add('foley',21.95,hit(.8,40),.72,label='bus body hits road');add('foley',23.3,hit(.5,55),.32,label='wreck comes to rest');add('foley',22.05,noise(.8)*np.exp(-np.arange(int(.8*SR))/SR*5),.30,label='metal and debris rattle')
add('foley',25.6,hit(.18,750),.12,label='small shelter piece falls')
add('ui',28.0,tone(.115,1100),.28,label='isolated EZ-Link BEEP')
add('foley',31.58,hit(.22,80),.25,label='two feet land after supported descent')
for t in [33.2,33.5]:add('foley',t,noise(.14),.17,label='dust off')
for t in [34.35,34.72]:add('foley',t,hit(.13,90),.13,label='recovery steps toward Goji')
# All pursuit effects end before39.0s, an abrupt calm threshold.
add('ui',39.1,tone(.4,660)*np.exp(-np.arange(int(.4*SR))/SR*7),.055,label='soft clinic chime')
add('clinic',39,noise(10),.008,label='quiet room tone')
for t in [42,46]:add('clinic',t,noise(1.7)*np.sin(np.linspace(0,np.pi,int(1.7*SR))),.025,label='reformer carriage hush')
add('clinic',43.6,noise(2)*np.sin(np.linspace(0,np.pi,2*SR)),.020,label='soft exhale')
def save(name,a):
 a=np.clip(a,-.95,.95)
 with wave.open(str(R/'audio'/name),'wb') as f:f.setnchannels(2);f.setsampwidth(2);f.setframerate(SR);f.writeframes((a*32767).astype('<i2').tobytes())
mix=sum(stems.values());peak=float(np.max(np.abs(mix)));gain=min(1,.85/peak)
for name,a in stems.items():save(name+'.wav',a*gain)
save('sfx-mix.wav',mix*gain)
(R/'audio/cues.json').write_text(json.dumps({'duration':D,'sample_rate':SR,'channels':2,'source':'original procedural synthesis','music':False,'dialogue':False,'peak_before_normalization':peak,'gain':gain,'events':events},indent=2)+'\n')
print('49-second stereo SFX mix and four editable stems rendered')
