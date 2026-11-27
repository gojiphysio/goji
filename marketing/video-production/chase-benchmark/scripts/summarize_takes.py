"""Publish factual status only; generated H3 media and raw logs stay private."""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
rows = []
for file in sorted((root / 'results').glob('*/run.json')):
    r = json.loads(file.read_text())
    row = {'take':file.parent.name, 'status':r.get('status'),
           'purpose':r.get('purpose',r.get('mode'))}
    for key in ['diagnostic','recipe','wall_seconds','execution_wall_seconds','failure','abort_reason','review']:
        if key in r:
            row[key] = r[key]
    rows.append(row)
(root / 'takes.json').write_text(json.dumps({'status':'See individual takes; no ranking inferred from encode success', 'takes':rows},indent=2))
