from pathlib import Path
import shutil,json,zipfile
R=Path(__file__).resolve().parents[1]
D=Path('/Users/tidepool/Projects/goji-reel-github/marketing/assets/goji-reel-prototype/animation-v8')
D.mkdir(parents=True,exist_ok=True)
for folder in ['assets','audio','overlays','scripts','clips','research','controls']:
 if (R/folder).exists():shutil.copytree(R/folder,D/folder,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','batch*.sh'))
for n in ['goji-v8-ui-silent.mp4','goji-v8-ui-sfx.mp4','preview.gif','edit-timeline.json','overlay-timing.json','setup.json','THIRD_PARTY_NOTICES.txt','render-history.jsonl','continuity.json']:
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
with zipfile.ZipFile(D/'goji-v8-editing-pack.zip','w',zipfile.ZIP_DEFLATED) as z:
 for folder in ['clips','audio','overlays','assets','research','controls','scripts']:
  if (D/folder).exists():
   for f in (D/folder).rglob('*'):
    if f.is_file():z.write(f,f.relative_to(D))
 for n in ['jobs.json','edit-timeline.json','overlay-timing.json','continuity.json','setup.json','THIRD_PARTY_NOTICES.txt']:z.write(D/n,n)
e=json.loads((R/'edit-timeline.json').read_text())
base='https://raw.githubusercontent.com/gojiphysio/goji/codex/goji-reel-mobile-handoff/marketing/assets/goji-reel-prototype/animation-v8/'
labels={'01-swagger':'Extended walking swagger','02-takeover':'Wrench open taxi door; driver falls out','03-drive':'Fast driving, trimmed before orientation glitch','04-arrival':'Arrival, cut at original 00:12.5','05-run':'Running, resumed at original 00:16','06-marker':'Yellow entrance cone','black-transition':'Loading transition','07-entry':'Seated Goji welcome','08b-mat':'Assisted stretch + Mobility popup','09-squat':'Spotted squat + Body Muscle popup'}
rows='\n'.join(f"| {x['start']:.1f}–{x['start']+x['duration']:.1f}s | {labels[x['shot']]} |" for x in e['shots'])
text=f'''# Goji reel — revision 8

[**Watch or download the {e['duration']:g}s cut**]({base}goji-v8-ui-sfx.mp4) · [Silent version]({base}goji-v8-ui-silent.mp4) · [Editing pack]({base}goji-v8-editing-pack.zip)

1080 × 1920 · 30 fps · original game-style sound effects · no music. The GIF is a lightweight 8 fps preview; use the MP4 to judge motion.

![Mobile preview](preview.gif)

## Changes

- **Half a second more to exit:** the arrival now runs through v6 **00:12.500**, then cuts to the same running frame at v6 **00:16.000**. This restores 15 frames of motion at 30 fps.
- All other v7 footage, black Goji uniforms, handbag HUD and popup wording remain unchanged. Sound effects follow the revised cut; no music.

## Timing

| Time | Action |
|---|---|
{rows}

## Clips for editing

'''
for j in jobs:text+=f"- [{labels[j['name']]}]({base}clips/{j['name']}.mp4)\n"
text+='''
## Uniform reference

The black fitted top and leggings follow the therapist's clothing in Goji's [official website treatment photo](https://www.gojiphysio.com/photos/services/prenatal-physiotherapy-warm.webp), linked from the [Goji homepage](https://www.gojiphysio.com/). The small chest mark uses Goji's supplied brand logo. The reference is used for clothing, not to replace the existing character's face or haircut.

[Welcome keyframe](assets/07-entry.png) · [Mat keyframe](assets/08b-mat-start.png) · [Squat keyframe](assets/09-squat.png)

## Editable sources

[Prompts](jobs.json) · [Keyframe prompts](assets/image-prompts.json) · [PNG/SVG overlays](overlays) · [Sound stems](audio) · [Timing](edit-timeline.json) · [Continuity record](continuity.json) · [LTX playbook](research/LTX_PLAYBOOK.md) · [Validation](validation.json)

Generated clips are 576 × 1024 at 24 fps. The precisely trimmed arrival and running excerpts are 1080 × 1920 at 30 fps, extracted from the previous edit. The final master is 1080 × 1920 at 30 fps. The pack contains clips, keyframes, separate overlays, ready-to-use SFX stems and editing scripts. Scripts retain Tidepool's local engine paths; audio conformation reads the previous v6 workspace. Original reference photographs stay local.

Animation uses the installed local LTX-2.5 distilled Q8 MLX model. Keyframes use the built-in image generator. No music or sampled GTA sound files are included; the short effects are original game-style approximations.

The action remains a stylised game parody; the popups are fictional game stats. This is a review cut, not an Instagram publication.
'''
if (R/'qa-notes.md').exists():text+='\n## Motion review\n\n'+(R/'qa-notes.md').read_text()
(D/'README.md').write_text(text)
p=D.parent/'README.md';s=p.read_text();link='[**Latest: revision 8 — half a second more to exit the taxi**](animation-v8/README.md)\n\n'
if link not in s:p.write_text(link+s)
print(D)
