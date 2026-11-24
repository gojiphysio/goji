"""Collect a submitted Comfy job without treating a successful encode as review."""
import argparse
import hashlib
import json
import shutil
import time
import urllib.request
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('take', type=Path)
a = p.parse_args()
record_path = a.take / 'run.json'
r = json.loads(record_path.read_text())
prompt_id = r['receipt']['prompt_id']
history = json.load(urllib.request.urlopen('http://127.0.0.1:8195/history/' + prompt_id))
if prompt_id not in history:
    print('Still queued or running:', prompt_id)
    raise SystemExit()
h = history[prompt_id]
(a.take / 'history.json').write_text(json.dumps(h, indent=2))
status = h.get('status', {})
r['status'] = 'generated_unreviewed' if status.get('completed') and status.get('status_str') == 'success' else 'execution_failed'
r['execution_events'] = status.get('messages', [])
events = [e[1]['timestamp'] for e in r['execution_events'] if 'timestamp' in e[1]]
if events:
    r['execution_wall_seconds'] = (max(events) - min(events)) / 1000
r['collected_at'] = time.time()
if r['status'] == 'generated_unreviewed':
    files = []
    for output in h.get('outputs', {}).values():
        for key, entries in output.items():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict) or 'filename' not in entry:
                    continue
                source = Path('/Users/tidepool/Projects/goji-comfy-control/output') / entry.get('subfolder', '') / entry['filename']
                dest = a.take / source.name
                if source.is_file():
                    shutil.copy2(source, dest)
                    files.append({'path': str(dest.resolve()), 'sha256': hashlib.sha256(dest.read_bytes()).hexdigest()})
    r['outputs'] = files
record_path.write_text(json.dumps(r, indent=2))
print(json.dumps({k: v for k, v in r.items() if k in ['status', 'execution_wall_seconds', 'outputs']}))
