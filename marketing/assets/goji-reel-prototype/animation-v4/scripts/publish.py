from pathlib import Path
import shutil,json,zipfile,subprocess
R=Path(__file__).resolve().parents[1];D=Path('/Users/tidepool/Projects/goji-reel-github/marketing/assets/goji-reel-prototype/animation-v4');D.mkdir(parents=True,exist_ok=True)
for folder in ['assets','audio','overlays','scripts']:
 shutil.copytree(R/folder,D/folder,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','batch*.sh','prepare_jobs.py'))
(D/'clips').mkdir(exist_ok=True)
jobs=json.loads((R/'jobs.json').read_text())
for j in jobs:
 s=R/'clips'/(j['name']+'.mp4');t=D/'clips'/s.name
 if j.get('source_start') or j.get('source_duration'):
  cmd=['ffmpeg','-hide_banner','-loglevel','error','-y','-ss',str(j.get('source_start',0)),'-i',str(s)]
  if 'source_duration' in j:cmd+=['-t',str(j['source_duration'])]
  subprocess.run(cmd+['-an','-c:v','libx264','-preset','fast','-crf','18','-movflags','+faststart',str(t)],check=True)
 else:shutil.copy2(s,t)
for name in ['goji-v4-ui-silent.mp4','goji-v4-ui-sfx.mp4','preview.gif','jobs.json','edit-timeline.json','overlay-timing.json','setup.json','THIRD_PARTY_NOTICES.txt','render-history.jsonl']:shutil.copy2(R/name,D/name)
shutil.copy2(R/'qa/reformer-preview.gif',D/'reformer-preview.gif')
shutil.copy2(R/'edit-notes.json',D/'edit-notes.json')
# Make the exported keyframe manifest self-contained rather than Tidepool-only.
portable_jobs=json.loads(json.dumps(jobs))
for j in portable_jobs:
 for im in j['images']:
  source=Path(im['path']);target=D/'assets'/source.name
  if not target.exists():shutil.copy2(source,target)
  im['path']=str(target.relative_to(D))
(D/'jobs.json').write_text(json.dumps(portable_jobs,indent=2))
with zipfile.ZipFile(D/'goji-v4-editing-pack.zip','w',zipfile.ZIP_DEFLATED) as z:
 for folder in ['clips','audio','overlays','assets']:
  for f in (D/folder).rglob('*'):
   if f.is_file():z.write(f,f.relative_to(D))
 for n in ['jobs.json','edit-timeline.json','overlay-timing.json','THIRD_PARTY_NOTICES.txt']:z.write(D/n,n)
e=json.loads((R/'edit-timeline.json').read_text());base='https://raw.githubusercontent.com/gojiphysio/goji/codex/goji-reel-mobile-handoff/marketing/assets/goji-reel-prototype/animation-v4/'
labels={'01-swagger':'Swagger','02-takeover':'Pull driver clear and enter taxi','03-drive':'Sparse traffic, aggressive player driving','04-crash-eject':'Moving approach, pole impact and ejection','05-recovery':'Get up and run toward mall','06-marker':'Yellow entrance cone','black-transition':'Loading transition','07-entry':'Seated Goji welcome','08a-warrior':'Overhead stretch to Warrior II on static reformer','08b-mat':'Assisted mat stretch','09-squat':'Spotted squat at reference rack'}
rows='\n'.join(f"| {x['start']:.1f}–{x['start']+x['duration']:.1f}s | {labels.get(x['shot'],x['shot'])} |" for x in e['shots'])
text=f'''# Goji reel — revised action and squat-rack ending

[**Watch / download the {e['duration']:g}s cut with SFX**]({base}goji-v4-ui-sfx.mp4) · [Silent UI cut]({base}goji-v4-ui-silent.mp4) · [Editing pack]({base}goji-v4-editing-pack.zip)

1080 × 1920 · 30 fps · no music. GIF is a small silent 8 fps preview; judge movement and sound using the MP4.

**Latest correction:** the player stands on the stationary reformer. [Watch the reformer clip]({base}clips/08a-warrior.mp4).

![Mobile preview](preview.gif)

## Changes

- Takeover follows her upright pull, pivot, step into the driver seat and door closure. Driver remains visible outside.
- Lighter traffic; ordinary cars mostly continue along their lanes while the taxi weaves past.
- Moving approach before contact; the impact shot carries her from the seat into the front windscreen exit. The following shot starts from its actual final frame.
- Recovery continues from the preceding shot's actual frame so the player can get up and run before the entrance marker.
- Player transitions from overhead reach to Warrior II **on the reformer**, with its carriage, frame and footbar stationary. Therapist supports her hip from the floor.
- Mat support uses a simpler palm and finger arrangement.
- New six-second spotted squat, matching the six-second mat scene. Black MATRIX rack, mirror, safety arms and plate storage follow the supplied photo; the left window is replaced with oak shelving. Fictional player and therapist replace the people in the reference. The supplied original photo is retained locally and not republished.
- GTA SA-style UI remains separate. Gameplay HUD hides indoors; the reference-worded Body Muscle popup moves to the squat-rack ending. No music.

## Timing

| Time | Action |
|---|---|
{rows}

## Individual clips

Native 24 fps clips are provided for editing, without HUD. Selected trims are recorded in the [edit timeline](edit-timeline.json). The assembled cut retimes outdoor action.

'''
for j in jobs:
 text+=f"### {labels.get(j['name'],j['name'])}\n\n[Download clip]({base}clips/{j['name']}.mp4)\n\n"
 p=Path(j['images'][0]['path'])
 if p.parent==R/'assets':text+=f"![{j['name']}](assets/{p.name})\n\n"
text+='''## Editing and reproducibility

[Animation prompts](jobs.json) · [Selected keyframe prompts](assets/selected-keyframe-prompts.json) · [Earlier prompt history](assets/image-prompts.json) · [Overlay timing](overlay-timing.json) · [PNG/SVG overlays](overlays) · [SFX stems](audio) · [Local model setup](setup.json) · [Scripts](scripts)

Built-in image generation produced revised keyframes; the existing local LTX-2.5 Q8 MLX installation generated motion on Tidepool. No new model install was required. The ending's squat rack uses the user-supplied reference. Lentor street layout and collision are fictional gameplay staging. The minimap remains illustrative, not route-tracked. Earlier versions remain available for comparison.
'''
if (R/'qa-notes.md').exists():text+='\n## Review notes\n\n'+(R/'qa-notes.md').read_text()
(D/'README.md').write_text(text)
p=D.parent/'README.md';s=p.read_text();link='[**Latest: revised action continuity, static-reformer stretch and spotted squat**](animation-v4/README.md)\n\n'
if link not in s:p.write_text(link+s)
print(D)
