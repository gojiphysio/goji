"""Run Episode 2 H3 test takes serially through ComfyUI (port 8195).

Usage: python3 run_ep02.py TAKE_ID [TAKE_ID ...]
TAKE_ID = <scene>-<variant>-s<seed>, e.g. t02-B-s1017, t03-CONT-s1017.

Variants (one change per step):
  A  prose prompt with exclusion list, Blender <Video 1>, Ref2V Turbo 4-step v0.1, 576x1024
  B  A with the six-section Ref2VA prompt
  C  B at 768x1344 with Ref2V Turbo 8-step v1.1 768p, 8 steps (shift 12/3, inferred; see weights record)
  D  B with the Blender depth pass through Fun ControlNet Union instead of <Video 1> (strength 1.0)
  D2 D at ControlNet strength 2.0 (after D at 1.0 ignored the depth layout)
  CONT  continuation of the selected native T03 take (anchors its last 22 frames at frame_idx 0)
  P  smoke: 2 steps, 124 frames, 288x512, B graph (validates loading only; never scored)

Generated H3 footage is written OUTSIDE the repository (territorial licence):
~/Projects/goji-ep02-runtime/takes/<take>/. Only the take record JSON is copied
into the repository's takes/ directory.
"""
import hashlib, json, os, shutil, subprocess, sys, time, urllib.request, urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMFY = Path('/Users/tidepool/Projects/goji-comfy-control')
PRIVATE = Path('/Users/tidepool/Projects/goji-ep02-runtime/takes')
URL = 'http://127.0.0.1:8195'
REFS = ROOT.parents[0] / 'skills/goji-gta-video/assets'
REF_IMAGES = ['ep01-reception.png', 'ep01-therapist-back.png', 'ep01-street.png']
FRAMES = {'t01': 192, 't02': 192, 't02v2': 192, 't03': 362, 'CONT': 192}
PROMPTS = json.loads((ROOT / 'prompts/ep02-prompts.json').read_text())
GUIDES = json.loads((ROOT / 'guides.json').read_text())
CONT_SOURCE = ROOT / 'takes' / 'cont-source.json'  # {"take": "t03-B-s1017"} chosen after review


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def node(t, **i):
    return {'class_type': t, 'inputs': i}


def stage_input(path, name):
    path = Path(path).resolve()
    target = COMFY / 'input' / name
    if target.exists() and sha(target) != sha(path):
        raise RuntimeError(f'{name} already holds different pixels')
    if not target.exists():
        shutil.copy2(path, target)
    return name


def build(take):
    scene, variant, seed = take.split('-')
    seed = int(seed[1:])
    smoke = variant == 'P'
    cont = variant == 'CONT'
    w, h = (768, 1344) if variant == 'C' else (288, 512) if smoke else (576, 1024)
    n = 124 if smoke else FRAMES['CONT' if cont else scene]
    pkey = f'{scene[:3]}/{"B" if smoke else "D" if variant == "D2" else variant}'  # t02v2 reuses the T02 prompts; only the guide changes
    prompt = PROMPTS[pkey]
    lora, steps = ('minimax_h3_ref2v_turbo_8step_v1.1_768p_comfyui_bf16.safetensors', 8) if variant == 'C' else \
                  ('minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors', 2 if smoke else 4)
    g = {
        '1': node('UnetLoaderGGUF', unet_name='minimax_h3_ref2va_pruned-Q4_K_M.gguf'),
        '2': node('CLIPLoaderGGUF', clip_name='qwen3vl_32b_minimax_h3-Q4_K_M.gguf', type='minimax'),
        '3': node('VAELoader', vae_name='minimax_h3_video_vae_fp16.safetensors'),
        '4': node('LoraLoaderModelOnly', model=['1', 0], lora_name=lora, strength_model=1.0),
        '5': node('MiniMaxH3SigmaShift', model=['4', 0], shift_video=12.0, shift_audio=3.0),
        '6': node('MiniMaxH3ReferenceToVideo', clip=['2', 0], vae=['3', 0], prompt=prompt, width=w, height=h, length=n,
                  ref_image_size='match'),
        '7': node('BasicGuider', model=['5', 0], conditioning=['6', 0]),
        '8': node('RandomNoise', noise_seed=seed),
        '9': node('KSamplerSelect', sampler_name='euler'),
        '10': node('BasicScheduler', model=['5', 0], scheduler='simple', steps=steps, denoise=1.0),
        '11': node('SamplerCustomAdvanced', noise=['8', 0], guider=['7', 0], sampler=['9', 0], sigmas=['10', 0], latent_image=['6', 1]),
        '12': node('VAEDecodeTiled', samples=['11', 0], vae=['3', 0], tile_size=256, overlap=64, temporal_size=64, temporal_overlap=8),
        '13': node('CreateVideo', images=['12', 0], fps=24.0),
        '14': node('SaveVideo', video=['13', 0], filename_prefix=f'goji-ep02/{take}', format='mp4', **{'format.codec': 'h264'}),
    }
    inputs = []
    for i, f in enumerate(REF_IMAGES):
        name = stage_input(REFS / f, f'ep02-{f}')
        g[str(20 + i)] = node('LoadImage', image=name)
        g['6']['inputs'][f'ref_images.ref_image_{i}'] = [str(20 + i), 0]
        inputs.append({'role': f'<Picture {i + 1}>', 'path': str((REFS / f).relative_to(ROOT.parents[2])), 'sha256': sha(REFS / f),
                       'note': 'Episode 1 recovered reference; cast turnarounds not reviewed'})

    def video_input(key, label, slot_node, comp_node):
        gd = GUIDES[key]
        p = ROOT / gd['path']
        assert sha(p) == gd['sha256'], key
        name = stage_input(p, f'ep02-{Path(gd["path"]).name}')
        g[slot_node] = node('LoadVideo', file=name)
        g[comp_node] = node('GetVideoComponents', video=[slot_node, 0])
        inputs.append({'role': label, 'path': gd['path'], 'sha256': gd['sha256'], 'source_frames': gd['source_frames']})
        return [comp_node, 0]

    if variant in ('A', 'B', 'C', 'P'):
        g['6']['inputs']['ref_videos.ref_video_0'] = video_input(f'{scene}/layout', '<Video 1> Blender layout', '30', '31')
    if variant in ('D', 'D2'):
        ctrl = video_input(f'{scene}/depth', 'Fun ControlNet depth control_video', '30', '31')
        g['40'] = node('ModelPatchLoader', name='minimax_h3_fun_controlnet_union_pruned_bf16.safetensors')
        g['41'] = node('MiniMaxH3FunControlNetApply', model=['5', 0], model_patch=['40', 0], vae=['3', 0], strength=2.0 if variant == 'D2' else 1.0,
                       start_percent=0.0, end_percent=1.0, control_video=ctrl)
        g['7']['inputs']['model'] = ['41', 0]
        g['10']['inputs']['model'] = ['41', 0]
    if cont:
        src = json.loads(CONT_SOURCE.read_text())['take']
        src_mp4 = PRIVATE / src / f'{src}.mp4'
        tail = PRIVATE / take / 'source-tail-56.mp4'
        tail.parent.mkdir(parents=True, exist_ok=True)
        # Last 56 frames (306-361) as <Video 1>; last 22 (340-361) anchored at frame_idx 0.
        subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-i', str(src_mp4), '-vf', 'select=gte(n\\,306)', '-fps_mode', 'passthrough',
                        '-frames:v', '56', '-c:v', 'libx264', '-crf', '10', '-pix_fmt', 'yuv420p', '-r', '24', str(tail)], check=True)
        tail22 = PRIVATE / take / 'source-tail-22.mp4'
        subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-i', str(src_mp4), '-vf', 'select=gte(n\\,340)', '-fps_mode', 'passthrough',
                        '-frames:v', '22', '-c:v', 'libx264', '-crf', '10', '-pix_fmt', 'yuv420p', '-r', '24', str(tail22)], check=True)
        for p, k, label in [(tail, '32', '<Video 1> source take frames 306-361'), (tail22, '34', 'AddGuide clip: source frames 340-361 at frame_idx 0')]:
            name = stage_input(p, f'ep02-{take}-{p.name}')
            g[k] = node('LoadVideo', file=name)
            g[str(int(k) + 1)] = node('GetVideoComponents', video=[k, 0])
            inputs.append({'role': label, 'path': str(p), 'sha256': sha(p), 'parent_take': src})
        g['6']['inputs']['ref_videos.ref_video_0'] = ['33', 0]
        g['6']['inputs']['ref_videos.ref_video_1'] = video_input('t03/layout-cont', '<Video 2> Blender layout 340-531', '30', '31')
        g['42'] = node('MiniMaxH3AddGuide', positive=['6', 0], vae=['3', 0], latent=['6', 1], image=['35', 0], frame_idx=0)
        g['7']['inputs']['conditioning'] = ['42', 0]
    return g, dict(scene=scene, variant=variant, seed=seed, width=w, height=h, frames=n, steps=steps, lora=lora,
                   shifts_video_audio=[12.0, 3.0], ref_image_size='match', sampler='euler/simple', cfg=1.0,
                   prompt_key=pkey, prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
                   prompt_format='prose-with-exclusions' if variant == 'A' else 'ref2va-six-section'), inputs


def runtime():
    rev = lambda d: subprocess.check_output(['git', '-C', str(d), 'rev-parse', 'HEAD'], text=True).strip()
    return {'comfy_commit': rev(COMFY), 'gguf_commit': rev(COMFY / 'custom_nodes/ComfyUI-GGUF'),
            'launch': 'GOJI_TEXT_ENCODER_MPS=1 .venv/bin/python main.py --port 8195 --use-pytorch-cross-attention --fp32-vae',
            'hardware': 'Mac M5 Pro, 64 GB unified memory', 'audio': 'not decoded (no audio VAE connected)'}


def run(take):
    g, settings, inputs = build(take)
    priv = PRIVATE / take
    priv.mkdir(parents=True, exist_ok=True)
    rec = {'take': take, 'status': 'submitting', 'settings': settings, 'inputs': inputs, 'runtime': runtime(),
           'workflow': g, 'private_dir': str(priv)}
    t0 = time.time()
    if os.environ.get('COLLECT_PID'):
        pid = os.environ['COLLECT_PID']
        rec.update(status='queued', prompt_id=pid, submitted=t0, note='collected after a collector fix; generation not repeated')
        return finish(rec, pid, t0, priv, take)
    try:
        r = json.load(urllib.request.urlopen(urllib.request.Request(URL + '/prompt', data=json.dumps({'prompt': g}).encode(),
                                                                    headers={'Content-Type': 'application/json'})))
    except urllib.error.HTTPError as e:
        rec.update(status='validation_failed', error=e.read().decode())
        save(rec)
        return rec
    pid = r['prompt_id']
    rec.update(status='queued', prompt_id=pid, submitted=t0)
    save(rec)
    return finish(rec, pid, t0, priv, take)


def finish(rec, pid, t0, priv, take):
    while True:
        time.sleep(20)
        hist = json.load(urllib.request.urlopen(f'{URL}/history/{pid}'))
        if pid in hist and hist[pid].get('status', {}).get('completed') is not None:
            st = hist[pid]['status']
            if st.get('status_str') in ('success', 'error'):
                break
    msgs = st.get('messages', [])
    ts = {m[0]: m[1].get('timestamp') for m in msgs}
    wall = (ts.get('execution_success') or ts.get('execution_error') or time.time() * 1000) - ts.get('execution_start', t0 * 1000)
    rec['wall_seconds'] = round(wall / 1000, 1)
    rec['messages'] = [[m[0], {k: v for k, v in m[1].items() if k != 'traceback'} if m[0] != 'execution_error' else m[1]] for m in msgs]
    if st['status_str'] != 'success':
        rec['status'] = 'execution_error'
        save(rec)
        return rec
    o = hist[pid]['outputs']['14']
    files = [v for k in ('images', 'videos', 'gifs') for v in o.get(k, []) if v.get('type') == 'output']
    src = COMFY / 'output' / files[0].get('subfolder', '') / files[0]['filename']
    dst = priv / f'{take}.mp4'
    shutil.copy2(src, dst)
    probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-count_frames', '-select_streams', 'v:0', '-show_entries',
                                                'stream=width,height,nb_read_frames,r_frame_rate', '-of', 'json', str(dst)]))['streams'][0]
    rec.update(status='generated', output={'path': str(dst), 'sha256': sha(dst), 'probe': probe})
    # Contact sheet: 12 evenly spaced frames, 4x3, for review (private).
    nfr = int(probe['nb_read_frames'])
    idx = [round(i * (nfr - 1) / 11) for i in range(12)]
    sel = '+'.join(f'eq(n\\,{i})' for i in idx)
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-i', str(dst), '-vf', f"select='{sel}',scale=288:-2,tile=6x2",
                    '-frames:v', '1', '-fps_mode', 'passthrough', str(priv / 'contact.jpg')], check=True)
    rec['contact_frames'] = idx
    save(rec)
    return rec


def save(rec):
    out = ROOT / 'takes' / f'{rec["take"]}.json'
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(rec, indent=1))
    (PRIVATE / rec['take']).mkdir(parents=True, exist_ok=True)
    (PRIVATE / rec['take'] / 'run.json').write_text(json.dumps(rec, indent=1))


if __name__ == '__main__':
    for take in sys.argv[1:]:
        print(time.strftime('%H:%M:%S'), 'start', take, flush=True)
        r = run(take)
        print(time.strftime('%H:%M:%S'), take, r['status'], r.get('wall_seconds'), flush=True)
