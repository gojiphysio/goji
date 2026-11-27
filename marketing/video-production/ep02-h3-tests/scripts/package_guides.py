"""Encode Blender frames into H3 guide clips on the 17k+5 grid and hash them.

Usage: python3 package_guides.py
Writes staging/<scene>/guides/*.mp4 and guides.json (paths, frame ranges, sha256).
Layout guides are 288x512 (the chase benchmark's guide scale); depth guides are
576x1024 for Fun ControlNet. Lossless-ish H.264 (crf 10, yuv420p), 24 fps.
"""
import hashlib, json, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JOBS = {
    't01': [('layout', 0, 192), ('depth', 0, 192)],
    't02': [('layout', 0, 192), ('depth', 0, 192)],
    't02v2': [('layout', 0, 192), ('depth', 0, 192)],
    't03': [('layout', 0, 362), ('depth', 0, 362), ('layout-cont', 340, 192), ('depth-cont', 340, 192)],
}


def grid(n):
    return n % 17 == 5


manifest = {}
for scene, jobs in JOBS.items():
    st = ROOT / 'staging' / scene
    out = st / 'guides'
    out.mkdir(exist_ok=True)
    for kind, start, n in jobs:
        assert grid(n), (scene, kind, n)
        src = 'depth' if kind.startswith('depth') else 'frames'
        size = '576:1024' if src == 'depth' else '288:512'
        dst = out / f'{scene}-{kind}-{n}.mp4'
        subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-framerate', '24', '-start_number', str(start),
                        '-i', str(st / src / '%04d.png'), '-frames:v', str(n), '-vf', f'scale={size}:flags=area',
                        '-c:v', 'libx264', '-crf', '10', '-pix_fmt', 'yuv420p', '-r', '24', str(dst)], check=True)
        count = int(subprocess.check_output(['ffprobe', '-v', 'error', '-count_frames', '-select_streams', 'v:0',
                                             '-show_entries', 'stream=nb_read_frames', '-of', 'csv=p=0', str(dst)]).strip())
        assert count == n, (dst, count)
        manifest[f'{scene}/{kind}'] = {'path': str(dst.relative_to(ROOT)), 'source_frames': [start, start + n],
                                       'frames': n, 'fps': 24, 'size': size.replace(':', 'x'),
                                       'sha256': hashlib.sha256(dst.read_bytes()).hexdigest(),
                                       'stage_json_sha256': hashlib.sha256((st / 'stage.json').read_bytes()).hexdigest()}
        print(scene, kind, n, 'ok')
(ROOT / 'guides.json').write_text(json.dumps(manifest, indent=1))
