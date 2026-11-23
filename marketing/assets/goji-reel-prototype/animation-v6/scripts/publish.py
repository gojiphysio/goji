from pathlib import Path
import shutil,json,zipfile
R=Path(__file__).resolve().parents[1]
D=Path('/Users/tidepool/Projects/goji-reel-github/marketing/assets/goji-reel-prototype/animation-v6')
D.mkdir(parents=True,exist_ok=True)
for folder in ['assets','audio','overlays','scripts','clips','research','controls']:
 if (R/folder).exists():shutil.copytree(R/folder,D/folder,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','batch*.sh'))
for n in ['goji-v6-ui-silent.mp4','goji-v6-ui-sfx.mp4','preview.gif','edit-timeline.json','overlay-timing.json','setup.json','THIRD_PARTY_NOTICES.txt','render-history.jsonl','continuity.json']:
 shutil.copy2(R/n,D/n)
shutil.copy2(R/'qa/validation.json',D/'validation.json')
jobs=json.loads((R/'jobs.json').read_text())
portable=json.loads(json.dumps(jobs))
for j in portable:
 for im in j['images']:
  source=Path(im['path']);target=D/'assets'/source.name
  if not target.exists():shutil.copy2(source,target)
  im['path']=str(target.relative_to(D))
(D/'jobs.json').write_text(json.dumps(portable,indent=2))
with zipfile.ZipFile(D/'goji-v6-editing-pack.zip','w',zipfile.ZIP_DEFLATED) as z:
 for folder in ['clips','audio','overlays','assets','research','controls','scripts']:
  if (D/folder).exists():
   for f in (D/folder).rglob('*'):
    if f.is_file():z.write(f,f.relative_to(D))
 for n in ['jobs.json','edit-timeline.json','overlay-timing.json','continuity.json','setup.json','THIRD_PARTY_NOTICES.txt']:z.write(D/n,n)
e=json.loads((R/'edit-timeline.json').read_text())
base='https://raw.githubusercontent.com/gojiphysio/goji/codex/goji-reel-mobile-handoff/marketing/assets/goji-reel-prototype/animation-v6/'
labels={'01-swagger':'Extended walking swagger','02-takeover':'Wrench open taxi door; driver falls out','03-drive':'Fast driving, trimmed before orientation glitch','04-bailout':'Continuous approach, stop and door bailout','05-recovery':'Retained get-up and run','06-marker':'Yellow entrance cone','black-transition':'Loading transition','07-entry':'Seated Goji welcome','08b-mat':'Assisted stretch + Mobility popup','09-squat':'Spotted squat + Body Muscle popup'}
rows='\n'.join(f"| {x['start']:.1f}–{x['start']+x['duration']:.1f}s | {labels[x['shot']]} |" for x in e['shots'])
text=f'''# Goji reel — revision 6

[**Watch or download the {e['duration']:g}s cut**]({base}goji-v6-ui-sfx.mp4) · [Silent version]({base}goji-v6-ui-silent.mp4) · [Editing pack]({base}goji-v6-editing-pack.zip)

1080 × 1920 · 30 fps · original game-style sound effects · no music. The GIF is a lightweight 8 fps preview; use the MP4 to judge motion.

![Mobile preview](preview.gif)

## Changes

- Walking lasts **4.3 seconds**, with additional generated walking motion.
- The player actively wrenches the taxi door open; the driver falls out. Cut before she gets into the car.
- The taxi references show separate front and rear doors, a fixed centre pillar and one near-side mirror. The stop and door bailout use one generated shot, with the camera side and taxi heading matched to the retained get-up/run footage.
- The HUD uses a black handbag with a gold clasp.
- The welcoming team member and physiotherapist have short hair, no ponytail, and a gentle smile.
- The reformer scene is removed.
- Mat work is **5 seconds**, one second shorter, with a new top-left **Mobility - Upgraded** popup. The ending Body Muscle popup remains on the squat scene.

## Timing

| Time | Action |
|---|---|
{rows}

## Clips for editing

'''
for j in jobs:text+=f"- [{labels[j['name']]}]({base}clips/{j['name']}.mp4)\n"
text+='''
## Taxi reference checks

[Closed four-door taxi](assets/04-four-door-closed.png) · [Open front door, rear door retained](assets/04-four-door-open.png) · [Takeover starting frame](assets/02-four-door-seated.png) · [Four-door keyframe prompts](assets/four-door-prompts.json)

## Editable sources

[Prompts](jobs.json) · [Keyframe prompts](assets/image-prompts.json) · [PNG/SVG overlays](overlays) · [Sound stems](audio) · [Timing](edit-timeline.json) · [Continuity record](continuity.json) · [LTX playbook](research/LTX_PLAYBOOK.md) · [Validation](validation.json)

Native clips are 576 × 1024 at 24 fps. The final edit is upscaled to 1080 × 1920 at 30 fps. The pack includes native clips, keyframes, independent HUD layers, sound stems and editing scripts. Scripts retain Tidepool's local engine/model paths. Original reference photographs stay local. Vehicle structure was checked against this [four-door Comfort taxi reference](https://sgclassicrides.blogspot.com/2019/06/more-than-old-car-105-toyota-crown.html).

Animation uses the installed local LTX-2.5 distilled Q8 MLX model. Keyframes use the built-in image generator. No music or sampled GTA sound files are included; the short effects are original game-style approximations.

The action remains a stylised game parody; the popups are fictional game stats. This is a review cut, not an Instagram publication.
'''
if (R/'qa-notes.md').exists():text+='\n## Motion review\n\n'+(R/'qa-notes.md').read_text()
(D/'README.md').write_text(text)
p=D.parent/'README.md';s=p.read_text();link='[**Latest: revision 6 — longer walk, door action, handbag HUD and mobility popup**](animation-v6/README.md)\n\n'
if link not in s:p.write_text(link+s)
print(D)
