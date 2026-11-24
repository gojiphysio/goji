"""Stage pinned public Wan control weights, leaving at least 12 GiB free."""
import argparse
import hashlib
import json
import shutil
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser()
p.add_argument('--manifest', type=Path, default=ROOT/'wan22-weights.json')
p.add_argument('--destination', type=Path, default=Path('/Users/tidepool/Models/goji-chase-wan22-vace'))
a = p.parse_args()
DEST = a.destination
COMFY = Path('/Users/tidepool/Projects/goji-comfy-control/models')
DEST.mkdir(exist_ok=True)
manifest = json.loads(a.manifest.read_text())


def digest(path):
    with path.open('rb') as file:
        return hashlib.file_digest(file, 'sha256').hexdigest()


missing = [f for f in manifest['files'] if not (DEST / f['local_name']).exists()]
required = sum(f['size'] for f in missing) + 12 * 1024**3
if shutil.disk_usage(DEST).free < required:
    raise RuntimeError(f'Need {required / 1024**3:.1f} GiB free before staging Wan')
for item in manifest['files']:
    target = DEST / item['local_name']
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        partial = target.with_suffix(target.suffix + '.partial')
        url = f"https://huggingface.co/{item['repo']}/resolve/{item.get('revision', 'main')}/{item['path']}"
        print('Downloading', item['local_name'], flush=True)
        with urllib.request.urlopen(url, timeout=120) as response, partial.open('wb') as file:
            shutil.copyfileobj(response, file, 8 * 1024**2)
        if partial.stat().st_size != item['size'] or digest(partial) != item['sha256']:
            raise RuntimeError(f'Download verification failed: {partial.name}')
        partial.rename(target)
    elif target.stat().st_size != item['size'] or digest(target) != item['sha256']:
        raise RuntimeError(f'Existing weight differs: {target.name}')
    link = COMFY / item['comfy_kind'] / target.name
    if link.is_symlink():
        assert link.resolve() == target
    elif link.exists():
        raise FileExistsError(link)
    else:
        link.symlink_to(target)
    print('Verified', target.name, flush=True)
(DEST / 'download.json').write_text(json.dumps(manifest, indent=2))
