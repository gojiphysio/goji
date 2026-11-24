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

def composite(paths,labels,dest,columns):
    dest.parent.mkdir(parents=True,exist_ok=True)
    args=['ffmpeg','-v','error','-y']
    for path in paths: args+=['-i',str(path)]
    for i,label in enumerate(labels):
        header=dest.parent/f'{dest.stem}-label-{i}.png'
        im=Image.new('RGB',(360,64),'#171a1c');draw=ImageDraw.Draw(im)
        for row,line in enumerate(label.split('\n')):
            draw.text((8,6+row*25),line,font=ImageFont.truetype(FONT,19),fill='white')
        im.save(header);args+=['-loop','1','-i',str(header)]
    filters=[];n=len(paths)
    for i in range(n):
        # Only the shorter reference is extended. Generated clips all exceed 5 s.
        filters.append(f'[{i}:v]setpts=PTS-STARTPTS,scale=360:640,fps=48,tpad=stop_mode=clone:stop_duration=1,trim=duration=5[p{i}]')
        filters.append(f'[{i+n}:v]fps=48[h{i}]')
        filters.append(f'[h{i}][p{i}]vstack=inputs=2:shortest=1[t{i}]')
    layout='|'.join(f'{(i%columns)*360}_{(i//columns)*704}' for i in range(n))
    filters.append(''.join(f'[t{i}]' for i in range(n))+f'xstack=inputs={n}:layout={layout}[v]')
    args+=['-filter_complex',';'.join(filters),'-map','[v]','-an','-t','5',
           '-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(dest)]
    subprocess.run(args,check=True)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('take',nargs='?',choices=list(LABELS))
    parser.add_argument('--all',action='store_true');a=parser.parse_args()
    takes=list(LABELS) if a.all else [a.take] if a.take else []
    if not takes: parser.error('Specify a take or --all')
    ref=BASE/'inputs/episode1-takeover.mp4'
    ref_label='EP1 CONTEXT | 2 frames\nLast frame held after 4.04s'
    for take in takes:
        dest=BASE/'results'/take;path=dest/'raw.mp4'
        info=probe(path)
        if (info['width'],info['height'])!=(576,1024): raise ValueError(f'Unexpected canvas: {take}')
        subprocess.run(['ffmpeg','-v','error','-i',str(path),'-f','null','-'],check=True)
        sheet(path,dest/'frames.jpg',LABELS[take].split(' |')[0])
        composite([ref,path],[ref_label,LABELS[take]+'\nNative speed; first 5s'],dest/'with-episode1.mp4',2)
    if a.all:
        paths=[ref]+[BASE/'results'/t/'raw.mp4' for t in takes]
        labels=[ref_label]+[LABELS[t]+'\nNative speed; first 5s' for t in takes]
        composite(paths,labels,BASE/'private-review/episode1-all-models.mp4',2)
        composite(paths[1:3],labels[1:3],BASE/'comparison/ltx-wan.mp4',2)
        summary=[]
        for take in takes:
            data=json.loads((BASE/'results'/take/'run.json').read_text())
            summary.append({k:data[k] for k in ['profile','prompt','inputs','wall_seconds','status']})
        (BASE/'summary.json').write_text(json.dumps(summary,indent=2))

if __name__=='__main__':main()
