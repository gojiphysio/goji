"""H3 Ref2VA guide conversion, not a benchmark result or timed-frame test."""
import hashlib
import json
import subprocess
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MODELS=Path('/Users/tidepool/Models/goji-chase-h3-ref')
RUNTIME=Path('/Users/tidepool/Projects/goji-h3-sdcpp')
DEST=ROOT/'results/h3-guide-conversion-01'
DEST.mkdir(parents=True,exist_ok=False)
prompt='''Use <Video 1> as the exact motion, layout and camera reference. Use <Picture 1> as the appearance reference for the whole shot. A continuous five-second rear chase-camera gameplay shot in original 2004 GTA San Andreas PlayStation 2 graphics, set on a Singapore road. A cobalt blue Comfort taxi with a white roof sign, yellow rear plate and black bumper accelerates past a silver sedan on its right, steers left to overtake a white van, then returns to the middle lane. Follow the timing, trajectories and relative positions in <Video 1>. Only these three vehicles exist. The silver sedan and white van drive straight and fall behind. The player taxi stays rigid, its wheels remain grounded. Keep the camera behind the taxi at constant distance, with gentle heading follow and no orbit or cut. Replace the simplified mockup surfaces with the painted PS2 textures and warm daylight of <Picture 1>: leafy tropical trees, pale cyan sky, grey HDB blocks, green railings, textured warm grey asphalt. Through the taxi rear window the seated adult woman on the right wears a maroon sleeveless top and black ponytail; her angular mesh and painted skin match the PS2 style. No realistic humans, no new vehicles, no spawning, no collision, no reversal, no HUD or text overlays. Quiet engine and road ambience, no speech or music.'''
refs=[ROOT/'inputs/look-start-v1.png',*sorted((ROOT/'staging/frames').glob('*.png'))]
cmd=[str(RUNTIME/'build/bin/sd-cli'),'-M','vid_gen',
 '--diffusion-model',str(MODELS/'minimax_h3_ref2va_pruned-Q4_K_M.gguf'),
 '--llm',str(MODELS/'qwen3vl_32b_minimax_h3-Q4_K_M.gguf'),
 '--vae',str(MODELS/'vae/minimax_h3_video_vae_fp16.safetensors'),
 '--ref-image',str(refs[0]),'--ref-video',str(ROOT/'staging/frames'),
 '--prompt',prompt,'--width','576','--height','1024','--video-frames','124',
 '--steps','20','--cfg-scale','1','--sampling-method','euler','--rng','cpu',
 '--seed','1017','--backend','te=cpu','--offload-to-cpu','--mmap',
 '--max-vram','40','--diffusion-fa','--vae-tiling','--output',str(DEST/'raw.avi')]
record={'purpose':'guide conversion; not benchmark','checkpoint':'H3 Ref2VA pruned Q4_K_M',
 'runtime_commit':subprocess.check_output(['git','-C',str(RUNTIME),'rev-parse','HEAD'],text=True).strip(),
 'command':cmd,'prompt':prompt,'source_fps':24,'source_frames':121,
 'references':[{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in refs],
 'started':time.time(),'status':'running'}
(DEST/'run.json').write_text(json.dumps(record,indent=2))
with (DEST/'inference.log').open('w') as log:
 result=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT)
record.update(exit_code=result.returncode,wall_seconds=time.time()-record['started'],status='generated_unreviewed' if result.returncode==0 else 'inference_failed')
(DEST/'run.json').write_text(json.dumps(record,indent=2))
if result.returncode==0:
 subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-i',str(DEST/'raw.avi'),'-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart','-an',str(DEST/'raw.mp4')],check=True)
print(json.dumps({'status':record['status'],'wall_seconds':record['wall_seconds'],'output':str(DEST/'raw.mp4')}))
