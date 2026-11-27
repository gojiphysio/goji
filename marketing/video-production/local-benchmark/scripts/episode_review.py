#!/usr/bin/env python3
"""Episode 1 context plus native-speed model takes; H3 composites stay private."""
import argparse, json, subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from compare import sheet, probe

BASE=Path(__file__).resolve().parents[1]/'episode1'
FONT='/System/Library/Fonts/Supplemental/Arial.ttf'
LABELS={'ltx-first-01':'LTX | 1 frame','wan14-lightning-01':'WAN 14B | 1 frame',
        'h3-turbo-01':'H3 | 1 frame'}

def details(path,dest):
    info=probe(path);num,den=map(int,info['avg_frame_rate'].split('/'))
    fps=num/den
    im=Image.new('RGB',(1440,1400),'#171a1c');draw=ImageDraw.Draw(im)
    font=ImageFont.truetype(FONT,18)
    for i in range(21):
        n=min(round(i*.25*fps),int(info['nb_frames'])-1)
        temp=dest.parent/f'.detail-{i}.png'
        subprocess.run(['ffmpeg','-v','error','-y','-i',str(path),'-vf',
            f'select=eq(n\\,{n}),crop=576:500:0:400,scale=288:250',
            '-fps_mode','vfr','-frames:v','1',str(temp)],check=True)
        x=i%5*288;y=i//5*280
        with Image.open(temp) as frame: im.paste(frame,(x,y+30))
        draw.text((x+8,y+6),f'{n/fps:.2f}s',fill='white',font=font);temp.unlink()
    im.save(dest,quality=90)

def composite(paths,labels,dest,columns):
    dest.parent.mkdir(parents=True,exist_ok=True)
    args=['ffmpeg','-v','error','-y']
    for path in paths: args+=['-i',str(path)]
    for i,label in enumerate(labels):
        header=dest.parent/f'{dest.stem}-label-{i}.png'
        im=Image.new('RGB',(576,88),'#171a1c');draw=ImageDraw.Draw(im)
        for row,line in enumerate(label.split('\n')):
            draw.text((12,10+row*36),line,font=ImageFont.truetype(FONT,28),fill='white')
        im.save(header);args+=['-loop','1','-i',str(header)]
    filters=[];n=len(paths)
    for i in range(n):
        # Only the shorter reference is extended. Generated clips all exceed 5 s.
        filters.append(f'[{i}:v]setpts=PTS-STARTPTS,fps=48,tpad=stop_mode=clone:stop_duration=1,trim=duration=5[p{i}]')
        filters.append(f'[{i+n}:v]fps=48[h{i}]')
        filters.append(f'[h{i}][p{i}]vstack=inputs=2:shortest=1[t{i}]')
    layout='|'.join(f'{(i%columns)*576}_{(i//columns)*1112}' for i in range(n))
    filters.append(''.join(f'[t{i}]' for i in range(n))+f'xstack=inputs={n}:layout={layout}[v]')
    args+=['-filter_complex',';'.join(filters),'-map','[v]','-an','-t','5',
           '-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(dest)]
    subprocess.run(args,check=True)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('take',nargs='?',choices=list(LABELS))
    parser.add_argument('--all',action='store_true')
    parser.add_argument('--compose-only',action='store_true',help='Build final grids from already reviewed takes')
    a=parser.parse_args()
    if a.compose_only and not a.all: parser.error('--compose-only requires --all')
    takes=list(LABELS) if a.all else [a.take] if a.take else []
    if not takes: parser.error('Specify a take or --all')
    ref=BASE/'inputs/episode1-takeover.mp4'
    ref_label='EP1 CONTEXT | 2 frames\nLast frame held after 4.04s'
    for take in ([] if a.compose_only else takes):
        dest=BASE/'results'/take;path=dest/'raw.mp4'
        info=probe(path)
        if (info['width'],info['height'])!=(576,1024): raise ValueError(f'Unexpected canvas: {take}')
        subprocess.run(['ffmpeg','-v','error','-i',str(path),'-f','null','-'],check=True)
        sheet(path,dest/'frames.jpg',LABELS[take].split(' |')[0])
        details(path,dest/'contact-detail.jpg')
        composite([ref,path],[ref_label,LABELS[take]+'\nNative speed; first 5s'],dest/'with-episode1.mp4',2)
    if a.all:
        paths=[ref]+[BASE/'results'/t/'raw.mp4' for t in takes]
        labels=[ref_label]+[LABELS[t]+'\nNative speed; first 5s' for t in takes]
        composite(paths,labels,BASE/'private-review/episode1-all-models.mp4',2)
        composite(paths[1:3],labels[1:3],BASE/'comparison/ltx-wan.mp4',2)
        summary=[]
        for take in takes:
            directory=BASE/'results'/take
            data=json.loads((directory/'run.json').read_text())
            info=probe(directory/'raw.mp4')
            entry={k:data[k] for k in ['profile','prompt','inputs','wall_seconds','status']}
            entry['output']={k:info[k] for k in ['width','height','avg_frame_rate','nb_frames','duration']}
            if (directory/'review.json').exists():
                entry['review']=json.loads((directory/'review.json').read_text())
            summary.append(entry)
        (BASE/'summary.json').write_text(json.dumps(summary,indent=2))

if __name__=='__main__':main()
