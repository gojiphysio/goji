"""Export close samples around both overtakes; this is not playback verification."""
import argparse
import json
import subprocess
from fractions import Fraction
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

p=argparse.ArgumentParser()
p.add_argument('video',type=Path)
p.add_argument('reference',type=Path)
p.add_argument('destination',type=Path)
a=p.parse_args()
a.destination.mkdir(parents=True,exist_ok=False)
times=[0,.5,1,1.25,1.5,1.75,2,2.5,3,3.25,3.5,3.75,4,4.5,5]
records=[]
for name,path in [('guide',a.reference),('output',a.video)]:
    folder=a.destination/name;folder.mkdir()
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_streams','-of','json',str(path)],text=True))['streams'][0]
    fps=Fraction(probe['avg_frame_rate']);count=int(probe['nb_frames'])
    indices=[min(count-1,int(t*fps+.5)) for t in times]
    expr='+'.join(f'eq(n\\,{i})' for i in sorted(set(indices)))
    subprocess.run(['ffmpeg','-v','error','-i',str(path),'-vf','select='+expr,'-fps_mode','passthrough',str(folder/'%03d.png')],check=True)
    files={i:folder/f'{n+1:03d}.png' for n,i in enumerate(sorted(set(indices)))}
    records.append({'role':name,'path':str(path.resolve()),'probe':probe,'indices':indices,'sample_times':[float(i/fps) for i in indices], 'files':[str(files[i]) for i in indices]})
font=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf',16)
for group in range(3):
    canvas=Image.new('RGB',(960,742),'#101820');draw=ImageDraw.Draw(canvas)
    for row,record in enumerate(records):
        for col,index in enumerate(range(group*5,group*5+5)):
            x,y=col*192,row*371
            thumb=Image.open(record['files'][index]).convert('RGB').resize((192,341),Image.Resampling.LANCZOS)
            canvas.paste(thumb,(x,y+30))
            draw.text((x+5,y+7),f"{record['role']} {record['sample_times'][index]:.3f}s",font=font,fill='white')
    canvas.save(a.destination/f'contact-{group+1}.jpg',quality=94)
(a.destination/'samples.json').write_text(json.dumps({'note':'Timed sample inspection, not normal-speed playback','sources':records},indent=2))
print(a.destination)
