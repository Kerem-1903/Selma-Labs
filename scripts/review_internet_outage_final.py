from pathlib import Path
import json
import subprocess
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[1]
video=ROOT/'motion'/'output'/'internet-outage-24-saat-final.mp4'
data=json.loads((ROOT/'motion'/'public'/'internet-outage'/'data.json').read_text(encoding='utf-8'))
out=ROOT/'output'/'internet-final-review'
out.mkdir(parents=True,exist_ok=True)
times=[]
for chapter in data['chapters']:
    start=chapter['startMs']/1000; end=chapter['endMs']/1000
    times.extend([(start+1,chapter['id']+'-start'),((start+end)/2,chapter['id']+'-mid'),(max(start+1,end-1),chapter['id']+'-end')])
thumbs=[]
for index,(second,label) in enumerate(times):
    target=out/f'{index:02d}.jpg'
    subprocess.run(['ffmpeg','-loglevel','error','-y','-ss',f'{second:.3f}','-i',str(video),'-frames:v','1','-vf','scale=480:-1',str(target)],check=True)
    image=Image.open(target).convert('RGB'); image.thumbnail((480,240))
    canvas=Image.new('RGB',(480,270),'#07101c'); canvas.paste(image,((480-image.width)//2,0)); ImageDraw.Draw(canvas).text((10,247),label,fill='white'); thumbs.append(canvas)
sheet=Image.new('RGB',(5*492,9*282),'#02060c')
for i,image in enumerate(thumbs): sheet.paste(image,(6+(i%5)*492,6+(i//5)*282))
sheet.save(ROOT/'output'/'internet-final-review-sheet.jpg',quality=92)
print(len(thumbs))
