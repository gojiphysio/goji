"""Reproduce the selected bailout from a clean video-tail input and a pose guide."""
from pathlib import Path
import json,os,subprocess
R=Path(__file__).resolve().parents[1]
PY='/Users/tidepool/Projects/goji-video-engine/.venv/bin/python'
MODEL=os.environ.get('LTX_MODEL_PATH','/Users/tidepool/Models/ltx-2.5-mlx-q8')
job=next(j for j in json.loads((R/'jobs.json').read_text()) if j['name']=='04-bailout')
(R/'drafts').mkdir(exist_ok=True)
full=R/'drafts/drive-bailout-906.mp4'
subprocess.run([PY,str(R/'scripts/ltx25_community_adapter.py'),'extend','--distilled','--model',MODEL,'--video',str(R/'controls/drive-clean-approach.mp4'),'--extend-frames','6','--seed','906','--image',str(R/'assets/04-bail-end.png'),'last','1','guide','--output',str(full),'--prompt',job['prompt']],env=dict(os.environ,LTX2_COMPUTE_DTYPE='float16'),check=True)
subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(full),'-vf','trim=start_frame=97:end_frame=138,setpts=PTS-STARTPTS','-an','-c:v','libx264','-crf','17',str(R/'clips/04-bailout.mp4')],check=True)
