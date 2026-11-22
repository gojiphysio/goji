from pathlib import Path
import shutil,json,zipfile,subprocess
R=Path(__file__).resolve().parents[1]
DEST=Path('/Users/tidepool/Projects/goji-reel-github/marketing/assets/goji-reel-prototype/animation-v2')
DEST.mkdir(parents=True,exist_ok=True)
for name in ['audio','assets','scripts']:
 shutil.copytree(R/name,DEST/name,dirs_exist_ok=True)
(DEST/'clips').mkdir(exist_ok=True)
for job in json.loads((R/'jobs.json').read_text()):
 source=R/'clips'/(job['name']+'.mp4');target=DEST/'clips'/source.name
 if 'source_duration' in job:
  subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(source),'-t',str(job['source_duration']),'-an','-c:v','libx264','-preset','fast','-crf','18','-movflags','+faststart',str(target)],check=True)
 else:shutil.copy2(source,target)
for name in ['goji-v2-silent.mp4','goji-v2-sfx-no-music.mp4','preview.gif','jobs.json','setup.json','THIRD_PARTY_NOTICES.txt','edit-timeline.json','render-history.jsonl']:
 shutil.copy2(R/name,DEST/name)
with zipfile.ZipFile(DEST/'goji-v2-editing-pack.zip','w',zipfile.ZIP_DEFLATED) as z:
 for folder in ['clips','audio','scripts']:
  for f in (DEST/folder).rglob('*'):
   if f.is_file() and '__pycache__' not in str(f):z.write(f,f.relative_to(DEST))
 for name in ['jobs.json','edit-timeline.json','setup.json','THIRD_PARTY_NOTICES.txt']:z.write(R/name,name)
base='https://raw.githubusercontent.com/gojiphysio/goji/codex/goji-reel-mobile-handoff/marketing/assets/goji-reel-prototype/animation-v2/'
edit=json.loads((R/'edit-timeline.json').read_text())
rows=[]
labels=['Swagger','Continuous taxi takeover','Fast traffic weaving','Lamp-post impact','Ejection and evasive passersby','Yellow entry cone','Black loading transition','Seated welcome','Assisted kneeling reformer lunge','Assisted mat side stretch']
for x,label in zip(edit['shots'],labels):rows.append(f"| {x['start']:.1f}–{x['start']+x['duration']:.1f}s | {label} |")
readme=f'''# Goji GTA-style reel — animation v2

[**Play / download the {edit['duration']:g}s cut with sound effects**]({base}goji-v2-sfx-no-music.mp4) · [Silent cut for adding music]({base}goji-v2-silent.mp4) · [Editing pack]({base}goji-v2-editing-pack.zip)

1080 × 1920, 30 fps. No background music. The GIF below is a small silent 8 fps preview; use the MP4 to judge speed and sound.

![Revised reel preview](preview.gif)

## Changes in this pass

- Taxi takeover uses one continuous generated action instead of interpolating three different taxi drawings.
- Driving has six seconds in the edit, accelerated from a longer source take, with traffic and stronger evasive-action direction.
- Driving, impact and ejection use scene 3’s pale teal sky, green foliage and daylight. Matching crash keyframes share the same two bystanders.
- Reception includes a seated Goji team member welcoming the player.
- Reformer pose follows the actual Goji photo: kneeling lunge, hands on footbar, front foot on fixed platform and rear knee on carriage. The therapist supports the pelvis.
- Mat stretch has the therapist guiding the raised arm and stabilising the waist. Eleven seconds of gentle assisted movement give the calm section breathing room.
- Original dry game-style engines, traffic horns, skids and impact effects cut to quiet at the loading transition. No music or extracted GTA sound samples.

## Edit timing

| Time | Shot |
|---|---|
{chr(10).join(rows)}

## Individual clips and revised frames

The individual clips use native 24 fps timing. Rejected takeover and ejection tails have been removed; longer driving and physio takes retain handles. The edited MP4 uses faster outdoor timing; see [edit manifest](edit-timeline.json). These are editable AI prototype shots, not a physically simulated game scene.

'''
for j in json.loads((R/'jobs.json').read_text()):
 readme+=f"### {j['name']}\n\n[Source clip]({base}clips/{j['name']}.mp4)\n\n"
 p=Path(j['images'][0]['path'])
 if p.parent==R/'assets':readme+=f'![{j["name"]}](assets/{p.name})\n\n'
readme+='''## Source and reproducibility

[Animation prompts and seeds](jobs.json) · [Image prompts](assets/all-image-prompts.json) · [Model setup](setup.json) · [Render results](render-history.jsonl) · [Audio cue sheet](audio/cue-sheet.json) · [Scripts](scripts)

Keyframe revisions used the built-in image generator. Motion was generated locally on Tidepool using the existing LTX-2.5 distilled Q8 MLX installation. No new model download was needed. The editing ZIP contains individual source clips, five SFX stems, mix, manifests and scripts; master MP4s and keyframes are separate links to avoid duplicating large media.

The actual Goji pose and equipment reference is [the private-Pilates photo](../v5/references/goji-reformer-actual.webp). The characters are fictional. Lentor and Goji references ground the staging; the road geometry, traffic, lamp-post collision and antics remain fictional gameplay.
'''
if (R/'qa-notes.md').exists():readme+='\n## Review notes\n\n'+(R/'qa-notes.md').read_text()
(DEST/'README.md').write_text(readme)
parent=DEST.parent/'README.md';text=parent.read_text();link='[**Latest: revised animation v2 — expanded chaos, assisted physio, SFX and editing files**](animation-v2/README.md)\n\n'
if link not in text:parent.write_text(link+text)
print(DEST)
