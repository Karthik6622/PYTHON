"""Thumbnail for an episode (1280x720). Usage: make_thumbnail.py <title line> <subtitle> <badge text> <out file>"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import raju_lib as L  # noqa: E402
from raju_lib import Image, ImageDraw  # noqa: E402

TW, TH = 1280, 720
head, sub, badge, out = sys.argv[1:5]
bg = L.vgrad((TW, TH), (12, 14, 40), (70, 30, 14))
bg = L.glow(bg, (-200, 100, 700, 900), (255, 110, 20), 160, 170)
bg = L.glow(bg, (700, 0, 1500, 700), (30, 110, 255), 180, 150)
tiger = L.scene_closeup().crop((0, 700, L.W, 700 + 2052)).resize((800, 760), L.Image.LANCZOS)
ramp = L.np.clip(L.np.linspace(0, 1.6, 800) - 0.0, 0, 1)[None, :] * L.np.ones((760, 1))
mask = Image.fromarray((ramp * 255).astype("uint8"), "L")
bg.paste(tiger, (TW - 800, TH - 760), mask)
fr = bg.convert("RGBA")
d = ImageDraw.Draw(fr)
for i, (txt, size, col, y) in enumerate(((head, 168, (255, 214, 10), 150), (sub, 112, (255, 255, 255), 300))):
    d.text((50, y), txt, font=L.font("impact.ttf", size), fill=col, anchor="lm", stroke_width=14, stroke_fill=(0, 0, 0))
d.polygon([(40, 440), (700, 420), (680, 560), (30, 580)], fill=(220, 20, 30))
d.text((360, 505), badge, font=L.font("impact.ttf", 92), fill=(255, 255, 255), anchor="mm", stroke_width=6, stroke_fill=(90, 0, 0))
vig = L.vignette().resize((TW, TH))
fr.alpha_composite(vig)
fr.convert("RGB").save(out, quality=92)
print("wrote", out)
