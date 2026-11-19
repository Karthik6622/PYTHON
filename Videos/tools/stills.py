"""Render the still frames of every Part 1 scene so the artwork can be reviewed before the video is rendered."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import raju_lib as L  # noqa: E402

OUT = Path(__file__).parent.parent / "raju_bhai" / "episodes" / "part01" / "stills"
OUT.mkdir(parents=True, exist_ok=True)
for name in ("bus", "chase", "interior", "closeup", "shock", "cobra"):
    img = getattr(L, f"scene_{name}")()
    img.resize((540, 960), L.Image.LANCZOS).save(OUT / f"{name}.png")
    print("saved", name)
