from pathlib import Path
import shutil,json,zipfile
R=Path(__file__).resolve().parents[1]
D=Path('/Users/tidepool/Projects/goji-reel-github/marketing/assets/goji-reel-prototype/animation-v5');D.mkdir(parents=True,exist_ok=True)
for folder in ['assets','audio','overlays','scripts','clips','research','controls']:
 shutil.copytree(R/folder,D/folder,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','batch*.sh'))
for n in ['goji-v5-ui-silent.mp4','goji-v5-ui-sfx.mp4','preview.gif','edit-timeline.json','overlay-timing.json','setup.json','THIRD_PARTY_NOTICES.txt','render-history.jsonl','continuity.json']:
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
with zipfile.ZipFile(D/'goji-v5-editing-pack.zip','w',zipfile.ZIP_DEFLATED) as z:
 for folder in ['clips','audio','overlays','assets','research','controls']:
  for f in (D/folder).rglob('*'):
   if f.is_file():z.write(f,f.relative_to(D))
 for n in ['jobs.json','edit-timeline.json','overlay-timing.json','continuity.json','THIRD_PARTY_NOTICES.txt']:z.write(D/n,n)
e=json.loads((R/'edit-timeline.json').read_text())
base='https://raw.githubusercontent.com/gojiphysio/goji/codex/goji-reel-mobile-handoff/marketing/assets/goji-reel-prototype/animation-v5/'
labels={'01-swagger':'Swagger','02-takeover':'Pull driver clear, cut before entry','03-drive':'Selected drive before orientation glitch','04-bailout':'Moving approach and door bailout','05-recovery':'Ground tumble, get up and run','06-marker':'Yellow entrance cone','black-transition':'Loading transition','07-entry':'Seated Goji welcome','08a-warrior':'Stretch on stationary reformer','08b-mat':'Gentle downward-left assisted stretch','09-squat':'Spotted squat'}
rows='\n'.join(f"| {x['start']:.1f}–{x['start']+x['duration']:.1f}s | {labels[x['shot']]} |" for x in e['shots'])
text=f'''# Goji reel with door bailout

[**Watch or download the {e['duration']:g}s cut**]({base}goji-v5-ui-sfx.mp4) · [Silent version]({base}goji-v5-ui-silent.mp4) · [Editing pack]({base}goji-v5-editing-pack.zip)

1080 × 1920 · 30 fps · original SFX · no music. The GIF is an 8 fps preview; use the MP4 to judge motion.

![Mobile preview](preview.gif)

## Changes

- The driver pull ends before seat entry. Forearm contact replaces the sleeve grip; the handbag is not part of the action prompt.
- The driving is trimmed before the orientation glitch. The continuation carries video context from the clean driving tail.
- The windscreen ejection is removed. The player bails out through the open driver door before the pole, followed by the retained ground recovery and run.
- Mat assistance moves down and toward screen left into a deeper stretch, with the therapist's palm above the arm.
- The stationary reformer, seated welcome, squat scene and ending popup remain.

## Continuity and model controls

[Read the LTX continuity playbook](research/LTX_PLAYBOOK.md) · [Exact continuity record](continuity.json)

The earlier version used a single extracted frame between impact and tumble, while driving-to-impact used separate references. This version tests the installed runtime's **25-frame video-tail continuation**, plus a bailout pose guide. The local distilled extension mode is experimental. The transition into the retained ground-recovery clip is an editorial action cut, not a claim of one continuous simulated take.

## Timing

| Time | Action |
|---|---|
{rows}

## Individual clips

'''
for j in jobs:
 text+=f"- [{labels[j['name']]}]({base}clips/{j['name']}.mp4)\n"
text+='''
## Editing sources

[Animation prompts](jobs.json) · [Keyframe prompts](assets/image-prompts.json) · [Overlays](overlays) · [SFX stems](audio) · [Local model setup](setup.json) · [Validation](validation.json)

Revised keyframes use the built-in image generator. Animation uses the existing local LTX-2.5 Q8 MLX installation on Tidepool. HUD, wording and SFX remain separate from the native clips. The editing pack contains selected clips, keyframes, overlay sources, audio stems and manifests. The original squat-rack photo remains local.
'''
if (R/'qa-notes.md').exists():text+='\n## Review notes\n\n'+(R/'qa-notes.md').read_text()
(D/'README.md').write_text(text)
p=D.parent/'README.md';s=p.read_text();link='[**Latest: door bailout and corrected assisted stretch**](animation-v5/README.md)\n\n'
if link not in s:p.write_text(link+s)
print(D)
