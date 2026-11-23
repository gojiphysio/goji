from huggingface_hub import snapshot_download,HfApi
from pathlib import Path
import json,time
out=Path('/Users/tidepool/Models/ltx-2.5-mlx-q8')
repos=[('notapalindrome/ltx25-mlx',['transformer*','*lora*','vae_diffusion_decoder*','temporal_upscaler*']),('notapalindrome/ltx25-mlx-ditq8',None)]
manifest=[]
for repo,exclude in repos:
 info=HfApi().model_info(repo,files_metadata=True)
 manifest.append({'repo':repo,'revision':info.sha,'ignored':exclude})
 print('Downloading',repo,info.sha,flush=True)
 snapshot_download(repo_id=repo,revision=info.sha,local_dir=out,ignore_patterns=exclude,max_workers=4)
 print('Completed',repo,flush=True)
(out/'download-manifest.json').write_text(json.dumps(manifest,indent=2))
print('ALL MODEL COMPONENTS READY',flush=True)
