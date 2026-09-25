"""Build high-contrast left/right cursors for fullscreen photo navigation."""
from pathlib import Path
from PIL import Image,ImageDraw

root=Path(__file__).resolve().parent.parent/'web'
for direction in ('left','right'):
    image=Image.new('RGBA',(192,192),(0,0,0,0))
    pen=ImageDraw.Draw(image)
    pen.ellipse((9,9,183,183),fill=(20,19,22,228),outline=(229,169,59,240),width=5)
    points=[(105,48),(66,96),(105,144)] if direction=='left' else [(87,48),(126,96),(87,144)]
    pen.line(points,fill=(255,212,132,255),width=14,joint='curve')
    pen.line((66,96,136,96) if direction=='left' else (56,96,126,96),fill=(255,212,132,255),width=12)
    image.resize((48,48),Image.Resampling.LANCZOS).save(root/f'cursor-{direction}.png')
