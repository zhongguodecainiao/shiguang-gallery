"""Recolor the existing layered-photo mark for the dark, warm-gold interface."""
from pathlib import Path
import numpy as np
from PIL import Image

root = Path(__file__).resolve().parent.parent
source = Image.open(root / 'branding/shiguang-logo-master.png').convert('RGBA')
pixels = np.asarray(source).astype(np.float32)
rgb = pixels[:,:,:3]
alpha = pixels[:,:,3:4] / 255
green = np.clip((rgb[:,:,1:2] - rgb[:,:,0:1] * 1.03) / 38,0,1)
green *= np.clip((170 - rgb[:,:,0:1])/35,0,1)
light = np.clip((rgb[:,:,1:2] - 20)/140,0,1)
dark = np.array([14,14,16]) + light * np.array([34,28,23])
rgb[:] = rgb * (1-green) + dark * green
# The original cream artwork reads well against the new charcoal tile; a
# warmer metal tint ties its highlights to the controls without losing detail.
cream = np.clip((rgb[:,:,0:1]-170)/65,0,1) * (1-green)
rgb[:] = rgb*(1-cream*.18) + np.array([241,215,166])*cream*.18
result = Image.fromarray(np.uint8(np.clip(np.concatenate((rgb,pixels[:,:,3:4]),axis=2),0,255)),'RGBA')
result.resize((512,512),Image.Resampling.LANCZOS).save(root/'web/brand-icon.png')
result.save(root/'shiguang.ico',format='ICO',sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
(root/'web/favicon.ico').write_bytes((root/'shiguang.ico').read_bytes())
