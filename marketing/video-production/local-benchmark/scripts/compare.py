#!/usr/bin/env python3
"""Build unretimed review videos and exact-frame contact sheets from local takes."""
import argparse,json,subprocess
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1]
FONT='/System/Library/Fonts/Supplemental/Arial.ttf'
def run(args):subprocess.run(args,check=True,stdout=subprocess.DEVNULL)
def probe(path):
 return json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_streams','-of','json',str(path)]))['streams'][0]
def sheet(path,dest,label):
 info=probe(path);num,den=map(int,info['avg_frame_rate'].split('/'));fps=num/den
 frames=[0,round(fps),round(2*fps),round(3*fps),round(4*fps),int(info['nb_frames'])-1]
 out=Image.new('RGB',(288*6,552),'#171a1c');d=ImageDraw.Draw(out);font=ImageFont.truetype(FONT,18)
 for i,n in enumerate(frames):
  temp=dest.parent/f'.extract-{i}.png'
  run(['ffmpeg','-v','error','-y','-i',str(path),'-vf',f'select=eq(n\\,{n}),scale=288:512','-fps_mode','vfr','-frames:v','1',str(temp)])
  out.paste(Image.open(temp),(i*288,40));d.text((i*288+8,10),f'{label} | {n/fps:.2f}s',fill='white',font=font);temp.unlink()
 out.save(dest,quality=88)
def pair(path,dest,label):
 # Comparison uses the first five seconds of each source at its original speed.
 # 48 fps is a display cadence common to 16/24 fps; frames are repeated, never interpolated.
 header=dest.parent/'labels.png'
 im=Image.new('RGB',(720,40),'black');d=ImageDraw.Draw(im);f=ImageFont.truetype(FONT,19)
 d.text((10,10),'BLENDER GUIDE',font=f,fill='white');d.text((370,10),label,font=f,fill='white');im.save(header)
 filt=("[0:v]trim=duration=5,setpts=PTS-STARTPTS,scale=360:640,fps=48[a];"
       "[1:v]trim=duration=5,setpts=PTS-STARTPTS,scale=360:640:force_original_aspect_ratio=decrease,pad=360:640:(ow-iw)/2:(oh-ih)/2,fps=48[b];[a][b]hstack=inputs=2[c];[2:v]fps=48[h];[h][c]vstack=inputs=2:shortest=1[v]")
 run(['ffmpeg','-v','error','-y','-i',str(ROOT/'staging/guide.mp4'),'-i',str(path),'-loop','1','-i',str(header),'-filter_complex',filt,'-map','[v]','-an','-t','5','-c:v','libx264','-crf','20','-pix_fmt','yuv420p','-movflags','+faststart',str(dest)])

def main():
 p=argparse.ArgumentParser();p.add_argument('take');p.add_argument('label');a=p.parse_args()
 dest=ROOT/'results'/a.take
 sheet(dest/'raw.mp4',dest/'frames.jpg',a.label)
 pair(dest/'raw.mp4',dest/'with-guide.mp4',a.label)
if __name__=='__main__':main()
