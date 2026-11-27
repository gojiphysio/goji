"""Assemble the private review repository (H3 footage never enters the public goji repo).

python3 make_review.py OUT_DIR
Copies, per take: the MP4, its 12-frame contact sheet, the guide/take pair strip and any
contact crops (bag.jpg, occl.jpg, onset.jpg, scene.jpg, pre.jpg), then writes README.md from
evaluations.json, the take records and review-notes.md (hand-written summary, placed first).
"""
import json, shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIV = Path('/Users/tidepool/Projects/goji-ep02-runtime/takes')
out = Path(sys.argv[1])
(out / 'takes').mkdir(parents=True, exist_ok=True)
(out / 'guides').mkdir(exist_ok=True)
evals = json.loads((ROOT / 'evaluations.json').read_text())
CATS = ['all_human_ps2_style', 'spatial_structure', 'motion_contacts', 'camera', 'temporal_continuity']
NAMES = {'all_human_ps2_style': 'Style', 'spatial_structure': 'Structure', 'motion_contacts': 'Contacts',
         'camera': 'Camera', 'temporal_continuity': 'Time'}
CROPS = {'bag.jpg': 'Bag/hand region', 'occl.jpg': 'Occlusion frames', 'pre.jpg': 'Ghost onset (foreground)',
         'onset.jpg': 'Ghost onset', 'scene.jpg': 'Scene change', 'seam.jpg': 'Seam', 'every15.jpg': 'Every 15th frame'}

for sheet in (ROOT / 'staging').glob('*/sheet-*.jpg'):
    shutil.copy2(sheet, out / 'guides' / f'{sheet.parent.name}-{sheet.name}')

sections = []
for take, ev in evals.items():
    rec = json.loads((ROOT / 'takes' / f'{take}.json').read_text())
    src = PRIV / take
    dst = out / 'takes' / take
    dst.mkdir(exist_ok=True)
    shutil.copy2(src / f'{take}.mp4', dst / f'{take}.mp4')
    shutil.copy2(src / 'contact.jpg', dst / 'contact.jpg')
    review = sorted(src.glob('review-*.jpg'))
    if review:
        shutil.copy2(review[0], dst / 'pairs.jpg')
    st = rec['settings']
    sc = ev['scores']
    lines = [f'### {take}', '',
             f"{ev.get('label', '')} {st['width']}x{st['height']}, {st['frames']} frames, {st['steps']} steps, "
             f"`{st['lora']}`, prompt `{st['prompt_key']}` ({st['prompt_format']}), seed {st['seed']}. "
             f"Wall time **{rec['wall_seconds'] / 60:.1f} min**. Usable **{ev['usable_seconds']} s**.", '',
             '| Cast | ' + ' | '.join(NAMES[c] for c in CATS) + ' |', '|' + ' --- |' * (len(CATS) + 1),
             '| not assessed | ' + ' | '.join(str(sc[c]) for c in CATS) + ' |', '',
             f"**Verdict:** {ev['usable_note']}", '']
    if ev['failure_timecodes']:
        lines += ['**Failures**', ''] + [f'- {f}' for f in ev['failure_timecodes']] + ['']
    lines += ['**Holds**', ''] + [f'- {f}' for f in ev['passes']] + ['', f"*Look:* {ev['style_note']}", '']
    lines += [f'[Play MP4](takes/{take}/{take}.mp4)', '', f'![{take} contact sheet](takes/{take}/contact.jpg)', '']
    if review:
        lines += ['Guide | take pairs (guide left of each pair):', '', f'![{take} guide and take](takes/{take}/pairs.jpg)', '']
    for crop, label in CROPS.items():
        if (src / crop).exists():
            shutil.copy2(src / crop, dst / crop)
            lines += [f'{label}:', '', f'![{take} {label}](takes/{take}/{crop})', '']
    sections.append('\n'.join(lines))

notes = (ROOT / 'review-notes.md').read_text() if (ROOT / 'review-notes.md').exists() else ''
guides = '\n'.join(f'![{p.stem}](guides/{p.name})\n' for p in sorted((out / 'guides').glob('*.jpg')))
(out / 'README.md').write_text(notes + '\n\n## Every take\n\n' + '\n\n'.join(sections) +
                               '\n\n## Blender guides (proxies, not cast)\n\n' + guides)
print(out / 'README.md')
