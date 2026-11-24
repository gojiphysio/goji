#!/usr/bin/env python3
"""Run one immutable local benchmark take; no downloads or network calls."""
import argparse, hashlib, json, os, platform, resource, subprocess, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOME = Path('/Users/tidepool')
ENGINE = HOME/'Projects/goji-video-engine'
RUNTIME = HOME/'Projects/goji-model-bench-runtime'
MODELS = HOME/'Models/goji-benchmark'
PROMPT = """One continuous fixed-camera shot in a low-poly 2004 PlayStation 2 game, GTA San Andreas visual style, in Singapore. Preserve the supplied scene, its angular human meshes, simple painted faces, diffuse materials and warm hazy colour. The blue four-door taxi stays parked and rigid. The adult woman beside the taxi wears a maroon tank top and leggings, white trainers, a long black ponytail, and carries one black handbag in her left hand. She opens the taxi's near-side front driver door with her right hand and takes one step back while holding the door open. A separate adult male driver with short black hair, a grey shirt and grey trousers rises from that front seat, steps out through the open doorway, and walks forward alongside the car. The woman stays outside beside the open door. In the background the bob-haired woman in black stands at the yellow clinic entrance marker, and the orange-clad pedestrian walks along the pavement. Every foreground and background person keeps the same low-poly PS2 game appearance. All four people remain distinct with unchanged clothing. The car door rotates around its front hinge and stays open after the driver exits. Static elevated rear-right camera, constant focal length, stable sunlight and buildings, no cut, no camera motion, no photorealistic humans."""
NEGATIVE = 'photorealism, realistic skin pores, modern cinematic faces, changing clothes, merged people, duplicate people, extra limbs, disappearing handbag, flexible car body, detached door, teleportation, camera movement, cuts, subtitles, text overlays'

def main():
    p=argparse.ArgumentParser()
    p.add_argument('profile',choices=['ltx-first','ltx-guided','wan14-lightning','wan5','h3-turbo'])
    p.add_argument('--take',default='01')
    a=p.parse_args()
    dest=ROOT/'results'/f'{a.profile}-{a.take}'
    dest.mkdir(parents=True,exist_ok=False)
    image=ROOT/'staging/frame-0001.png'
    output=dest/'raw.mp4'
    refs=[image]
    env=dict(os.environ,PYTHONUNBUFFERED='1')
    if a.profile.startswith('ltx'):
        env['LTX2_COMPUTE_DTYPE']='float16'
        cmd=[str(ENGINE/'.venv/bin/python'),str(HOME/'Projects/goji-reel-animation-v6/scripts/ltx25_community_adapter.py'),'generate','--model',str(HOME/'Models/ltx-2.5-mlx-q8'),'--distilled','--prompt',PROMPT,'--width','576','--height','1024','--frames','121','--frame-rate','24','--seed','1017','--no-audio','--output',str(output),'--image',str(image),'0','1']
        if a.profile=='ltx-guided':
            for f in [25,49,73,97,121]:
                ref=ROOT/f'staging/frame-{f:04d}.png';refs.append(ref)
                cmd+=['--image',str(ref),str(f-1),'0.9']
    else:
        cmd=[str(RUNTIME/'.venv/bin/mlxgen'),'generate','--prompt',PROMPT,'--seed','1017','--metadata','--low-ram','--output',str(output)]
        if a.profile=='h3-turbo':
            cmd+=['--model',str(MODELS/'minimax-h3-4bit'),'--base-model','minimax-h3-turbo-544p','--image-path',str(image),'--width','544','--height','960','--frames','124','--steps','8','--soundscape','Quiet Singapore street ambience, a car door opening and footsteps. No speech.','--music','No music.']
        else:
            cmd+=['--image',str(image),'--negative-prompt',NEGATIVE,'--width','480','--height','832','--solver','unipc']
            if a.profile=='wan5':
                cmd+=['--model',str(MODELS/'wan2.2-ti2v-5b-diffusers-8bit'),'--base-model','wan2.2-ti2v-5b','--frames','121','--fps','24','--steps','25','--guidance','5','--flow-shift','3']
            else:
                lora=MODELS/'wan-lightning/Wan2.2-I2V-A14B-4steps-lora-rank64-Seko-V1'
                cmd+=['--model',str(MODELS/'wan2.2-i2v-a14b-diffusers-8bit'),'--base-model','wan2.2-i2v-a14b','--frames','81','--fps','16','--steps','4','--guidance','1','--guidance-2','1','--flow-shift','5','--lora-paths',str(lora/'high_noise_model.safetensors'),str(lora/'low_noise_model.safetensors'),'--lora-scales','1','1','--lora-target-roles','high_noise_transformer','low_noise_transformer']
    record={'profile':a.profile,'take':a.take,'prompt':PROMPT,'command':cmd,'inputs':{str(x.relative_to(ROOT)):hashlib.sha256(x.read_bytes()).hexdigest() for x in refs},'machine':platform.platform(),'started_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'api_spend':0,'status':'running'}
    path=dest/'run.json';path.write_text(json.dumps(record,indent=2))
    start=time.monotonic()
    with (dest/'run.log').open('w') as log:
        status=subprocess.run(cmd,env=env,stdout=log,stderr=subprocess.STDOUT).returncode
    record.update(exit_code=status,wall_seconds=round(time.monotonic()-start,3),max_rss_bytes=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,status='complete' if status==0 else 'failed')
    if output.exists():
        record['output_sha256']=hashlib.sha256(output.read_bytes()).hexdigest()
        probe=subprocess.run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(output)],capture_output=True,text=True)
        (dest/'probe.json').write_text(probe.stdout)
    path.write_text(json.dumps(record,indent=2));print(json.dumps({k:record[k] for k in ['profile','status','wall_seconds','max_rss_bytes']}),flush=True)
    raise SystemExit(status)

if __name__=='__main__':main()
