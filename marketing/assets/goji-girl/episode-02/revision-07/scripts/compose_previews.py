"""Compose editable native popup over approved art; no semantic image changes."""
from pathlib import Path
import subprocess,json
R=Path(__file__).resolve().parents[1]
def run(args):subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y']+args,check=True)
run(['-i',str(R/'frames/12-coaching-clean.png'),'-i',str(R/'overlays/safehouse-popup.png'),'-filter_complex','[0:v]scale=1080:1920:flags=lanczos[b];[b][1:v]overlay=0:0[v]','-map','[v]','-frames:v','1',str(R/'frames/12-safehouse-preview.png')])
# Visual review mask only; deliberately conservative proposal, not live Instagram UI.
run(['-i',str(R/'frames/12-safehouse-preview.png'),'-vf','drawbox=x=0:y=0:w=iw:h=280:color=red@0.22:t=fill,drawbox=x=900:y=280:w=180:h=1260:color=red@0.22:t=fill,drawbox=x=0:y=1540:w=iw:h=380:color=red@0.22:t=fill,drawbox=x=56:y=360:w=658:h=250:color=lime@0.8:t=3','-frames:v','1',str(R/'frames/12-ui-clearance-check.png')])
meta={'canvas':[1080,1920],'text':'You can save your game and lose the police at a safehouse.','previous_box':{'x':56,'y':360,'width':658,'height':250},'revised_box':{'x':56,'y':360,'width':658,'height':250},'delta_y_from_revision_4':0,'original_font':'Arial-Black','font_size':42,'fill':'#142725','opacity':.84,'text_fill':'#E1E4D9','episode_2_timing':{'in':41.5,'out':46.0},'review_reserves':{'top':280,'right_start_x':900,'bottom_start_y':1540},'actual_instagram_ui_verified':False,'copy_provenance':'Exact user-provided sentence in the established tutorial style.', 'note':'Proposed inset and review mask. Instagram chrome varies by device/view. Box clears stated reserves and all faces in supplied preview.'}
assert meta['revised_box']['y']>=meta['review_reserves']['top']
assert 56+658<900 and 360+250<1540
(R/'overlays/placement.json').write_text(json.dumps(meta,indent=2))
