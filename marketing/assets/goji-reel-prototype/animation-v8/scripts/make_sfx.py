"""Conform the approved original SFX to the exact v6 12.5-to-16-second picture cut."""
from pathlib import Path
import json,wave
import numpy as np
R=Path(__file__).resolve().parents[1]
SOURCE=R.parent/'goji-reel-animation-v6'/'audio'
for p in SOURCE.glob('*.wav'):
 with wave.open(str(p),'rb') as f:
  params=f.getparams();sr=f.getframerate();channels=f.getnchannels()
  samples=np.frombuffer(f.readframes(f.getnframes()),dtype='<i2').reshape(-1,channels)
 output=np.concatenate([samples[:int(12.5*sr)],samples[16*sr:]])
 with wave.open(str(R/'audio'/p.name),'wb') as f:
  f.setparams(params);f.writeframes(output.tobytes())
cues=json.loads((SOURCE/'cue-sheet.json').read_text());kept=[]
for cue in cues:
 if 12.5<=cue['time']<16:continue
 if cue['time']>=16:cue['time']=round(cue['time']-3.5,5)
 if cue['label']=='Mobility upgraded notification':cue['label']='Mobility — cops arrest joke notification'
 kept.append(cue)
(R/'audio/cue-sheet.json').write_text(json.dumps(kept,indent=2))
print('Conformed original SFX: remove exactly [12.5,16) seconds; no music.')
