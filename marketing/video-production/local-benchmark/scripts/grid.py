#!/usr/bin/env python3
"""Export a synchronous review grid; H3-containing media stays in ignored storage."""
import argparse,json,subprocess
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1]
FONT='/System/Library/Fonts/Supplemental/Arial.ttf'

def main():
    p=argparse.ArgumentParser();p.add_argument('--h3',action='store_true');a=p.parse_args()
    entries=[('Blender guide',ROOT/'staging/guide.mp4'),('LTX first frame',ROOT/'results/ltx-first-01/raw.mp4'),('Wan 14B Lightning',ROOT/'results/wan14-lightning-02/raw.mp4'),('Wan 5B 448x800',ROOT/'results/wan5-01/raw.mp4')]
    if a.h3:
        entries += [('MiniMax H3 Turbo',ROOT/'results/h3-turbo-02/raw.mp4'),('LTX + SIX GUIDES',ROOT/'results/ltx-guided-01/raw.mp4')]
    cols=3 if a.h3 else 2
    dest=ROOT/'results'/('h3-comparison' if a.h3 else 'comparison');dest.mkdir(exist_ok=True)
    cmd=['ffmpeg','-v','error','-y'];filters=[];font=ImageFont.truetype(FONT,18)
    for _,path in entries:cmd+=['-i',str(path)]
    for i,(name,path) in enumerate(entries):
        label=Image.new('RGB',(360,40),'#171a1c');ImageDraw.Draw(label).text((8,11),name,font=font,fill='white');label.save(dest/f'label-{i}.png')
        cmd+=['-loop','1','-i',str(dest/f'label-{i}.png')]
        filters += [f'[{i}:v]trim=duration=5,setpts=PTS-STARTPTS,scale=360:640:force_original_aspect_ratio=decrease,pad=360:640:(ow-iw)/2:(oh-ih)/2,fps=48[v{i}]',f'[{len(entries)+i}:v]fps=48[h{i}]',f'[h{i}][v{i}]vstack=inputs=2:shortest=1[p{i}]']
    layout='|'.join(f'{i%cols*360}_{i//cols*680}' for i in range(len(entries)))
    filters+=[''.join(f'[p{i}]' for i in range(len(entries)))+f'xstack=inputs={len(entries)}:layout={layout}:shortest=1[out]']
    cmd+=['-filter_complex',';'.join(filters),'-map','[out]','-an','-t','5','-c:v','libx264','-crf','19','-pix_fmt','yuv420p','-movflags','+faststart',str(dest/'side-by-side.mp4')]
    subprocess.run(cmd,check=True)
    # Same crop and same three-second sample time across all models, supplementing full-frame video.
    still=Image.new('RGB',(cols*432,2*328),'#171a1c');draw=ImageDraw.Draw(still)
    for i,(name,path) in enumerate(entries):
        probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_streams','-of','json',str(path)]))['streams'][0]
        num,den=map(int,probe['avg_frame_rate'].split('/'));n=round(3*num/den);tmp=dest/f'frame-{i}.png'
        subprocess.run(['ffmpeg','-v','error','-y','-i',str(path),'-vf',f'select=eq(n\\,{n}),scale=576:1024','-fps_mode','vfr','-frames:v','1',str(tmp)],check=True)
        crop=Image.open(tmp).crop((0,400,576,800)).resize((432,300));x=i%cols*432;y=i//cols*328;still.paste(crop,(x,y+28));draw.text((x+8,y+5),name+' | 3.00s',font=font,fill='white');tmp.unlink()
    still.save(dest/'interaction-at-3s.jpg',quality=90)
    (dest/'comparison.json').write_text(json.dumps({'entries':[{'label':name,'source':str(path.relative_to(ROOT))} for name,path in entries],'trim_seconds':5,'display_fps':48,'retimed':False,'motion_interpolation':False,'audio':'omitted from grid; raw sources retained','detail_frame_time':3,'detail_crop_on_576x1024':[0,400,576,800]},indent=2))

if __name__=='__main__':main()
