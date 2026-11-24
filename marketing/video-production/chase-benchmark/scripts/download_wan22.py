"""Stage pinned public Wan control weights, leaving at least 12 GiB free."""
import hashlib
import json
import shutil
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = Path('/Users/tidepool/Models/goji-chase-wan22-vace')
COMFY = Path('/Users/tidepool/Projects/goji-comfy-control/models')
DEST.mkdir(exist_ok=True)
manifest = json.loads((ROOT / 'wan22-weights.json').read_text())


def digest(path):
    with path.open('rb') as file:
        return hashlib.file_digest(file, 'sha256').hexdigest()


missing = [f for f in manifest['files'] if not (DEST / f['local_name']).exists()]
required = sum(f['size'] for f in missing) + 12 * 1024**3
if shutil.disk_usage(DEST).free < required:
    raise RuntimeError(f'Need {required / 1024**3:.1f} GiB free before staging Wan')
for item in manifest['files']:
    target = DEST / item['local_name']
    if not target.exists():
        partial = target.with_suffix(target.suffix + '.partial')
        url = f"https://huggingface.co/{item['repo']}/resolve/main/{item['path']}"
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
