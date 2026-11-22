from pathlib import Path
import argparse, datetime, json, os, subprocess, sys, time

ROOT = Path(__file__).resolve().parents[1]
PYTHON = '/Users/tidepool/Projects/goji-video-engine/.venv/bin/python'
MODEL = Path('/Users/tidepool/Models/ltx-2.5-mlx-q8')
p = argparse.ArgumentParser()
p.add_argument('--only')
p.add_argument('--wait-for-model', action='store_true')
a = p.parse_args()
if a.wait_for_model:
    while not (MODEL/'download-manifest.json').exists():
        time.sleep(15)
jobs = json.loads((ROOT/'jobs.json').read_text())
if a.only:
    jobs = [j for j in jobs if j['name'] in a.only.split(',')]
for j in jobs:
    out = ROOT/'clips'/(j['name']+'.mp4')
    if out.exists() and out.stat().st_size > 10000:
        print('Already rendered:', j['name'], flush=True)
        continue
    if j.get('pipeline') == 'video_tail_extension':
        subprocess.run([PYTHON, str(ROOT/'scripts/extend_bailout.py')], check=True)
        continue
    if j.get('pipeline') == 'selected_prior_clip':
        raise RuntimeError('Restore the selected prior clip from the editing pack: '+j['name'])
    cmd = [PYTHON, str(ROOT/'scripts/ltx25_community_adapter.py'), 'generate',
           '--model', str(MODEL), '--distilled', '--prompt', j['prompt'],
           '--width', str(j['width']), '--height', str(j['height']),
           '--frames', str(j['frames']), '--frame-rate', str(j['fps']),
           '--seed', str(j['seed']), '--no-audio', '--output', str(out)]
    for im in j['images']:
        cmd += ['--image', str(ROOT / im['path']), str(im['frame']), str(im['strength'])]
    env = dict(os.environ, PYTHONUNBUFFERED='1', LTX2_COMPUTE_DTYPE='float16')
    began = time.time()
    status = dict(shot=j['name'],state='rendering',started=datetime.datetime.now().isoformat(),command=cmd)
    (ROOT/'status.json').write_text(json.dumps(status,indent=2))
    print('Rendering',j['name'],flush=True)
    with (ROOT/'logs'/(j['name']+'.log')).open('w') as log:
        result = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, env=env)
    status.update(state='complete' if result.returncode == 0 else 'failed',seconds=round(time.time()-began,1),returncode=result.returncode)
    (ROOT/'status.json').write_text(json.dumps(status,indent=2))
    with (ROOT/'render-history.jsonl').open('a') as log:
        log.write(json.dumps(status)+'\n')
    print(status['state'],j['name'],status['seconds'],'seconds',flush=True)
    if result.returncode:
        sys.exit(result.returncode)
