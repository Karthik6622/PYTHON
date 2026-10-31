"""Draw complex-script text (Tamil, Devanagari) with correct letter shaping.

Pillow without the Raqm library lays Tamil and Hindi out letter by letter, so vowel signs and conjuncts break apart or
show as boxes. HarfBuzz (``uharfbuzz``) does the shaping; the glyph outlines are then filled with Pillow.

Everything here degrades gracefully: when ``uharfbuzz`` or a suitable font file is missing, ``load_text_font`` returns a
plain Pillow font and the cover is still produced.
"""

from __future__ import annotations

import logging
import math
import struct
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from PIL import Image, ImageDraw, ImageFont

from utils.image_utils import SHAPED_SCRIPTS, iter_font_families, load_pil_font, script_for

LOGGER = logging.getLogger(__name__)

try:  # optional dependency
    import uharfbuzz as hb
except ImportError:  # pragma: no cover - exercised only where the package is missing
    hb = None

SUPERSAMPLE = 3  # glyphs are filled at 3x resolution and scaled down, which gives smooth edges
CURVE_STEPS = 10
BOLD_WEIGHT = 600
REGULAR_WEIGHT = 400


class TextFont(Protocol):
    """What the cover generator needs from a font, whether it is shaped or plain Pillow."""

    size: int
    line_height: int

    def width(self, text: str) -> float: ...

    def draw(self, canvas: Image.Image, x: float, y: float, text: str, fill: tuple[int, int, int]) -> None: ...


def shaping_available() -> bool:
    return hb is not None


# ------------------------------------------------------------------------------------------------
# Plain Pillow font (Latin, Japanese and the fallback)
# ------------------------------------------------------------------------------------------------
class PilTextFont:
    def __init__(self, font: ImageFont.ImageFont | ImageFont.FreeTypeFont, size: int) -> None:
        self.font = font
        self.size = size
        self.line_height = int(size * 1.18)

    def width(self, text: str) -> float:
        return float(self.font.getlength(text))

    def draw(self, canvas: Image.Image, x: float, y: float, text: str, fill: tuple[int, int, int]) -> None:
        ImageDraw.Draw(canvas).text((x, y), text, font=self.font, fill=fill)


# ------------------------------------------------------------------------------------------------
# HarfBuzz-shaped font
# ------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class _FaceSource:
    path: Path
    index: int


@lru_cache(maxsize=16)
def _load_face(path: str, index: int):
    return hb.Face(hb.Blob.from_file_path(path), index)


def _face_weight(face) -> int | None:
    try:
        table = bytes(face.reference_table("OS/2").data)
        return struct.unpack(">H", table[4:6])[0] if len(table) >= 6 else None
    except Exception:  # noqa: BLE001 - a face without an OS/2 table is simply treated as unknown
        return None


@lru_cache(maxsize=32)
def _pick_face_index(path: str, bold: bool) -> int:
    """For a font collection (``.ttc``): the face whose weight is closest to regular or bold."""
    if not path.lower().endswith((".ttc", ".otc")):
        return 0
    target = BOLD_WEIGHT + 100 if bold else REGULAR_WEIGHT
    best, best_gap = 0, None
    for index in range(12):
        try:
            face = _load_face(path, index)
        except Exception:  # noqa: BLE001
            break
        if face.upem <= 0 or face.glyph_count <= 0:
            break
        weight = _face_weight(face)
        if weight is None:
            continue
        gap = abs(weight - target)
        if best_gap is None or gap < best_gap:
            best, best_gap = index, gap
    return best


def find_shaping_font(language: str, bold: bool) -> _FaceSource | None:
    """The first installed font for the language, with the right face chosen for bold or regular."""
    for family in iter_font_families(language):
        path = family.get("bold") if bold else None
        if path is None or not path.exists():
            path = family["regular"]
        try:
            return _FaceSource(path, _pick_face_index(str(path), bold))
        except Exception:  # noqa: BLE001
            continue
    return None


class _OutlinePen:
    """Collects glyph outlines as lists of points (curves are flattened to short line segments)."""

    def __init__(self) -> None:
        self.contours: list[list[tuple[float, float]]] = []
        self._current: list[tuple[float, float]] = []

    def moveTo(self, pt):  # noqa: N802 - fontTools pen interface
        self._flush()
        self._current = [(float(pt[0]), float(pt[1]))]

    def lineTo(self, pt):  # noqa: N802
        self._current.append((float(pt[0]), float(pt[1])))

    def qCurveTo(self, *points):  # noqa: N802
        if not self._current or not points:
            return
        start = self._current[-1]
        # TrueType: several off-curve points imply on-curve points halfway between them.
        controls, end = list(points[:-1]), points[-1]
        for i, control in enumerate(controls):
            target = end if i == len(controls) - 1 else (
                (control[0] + controls[i + 1][0]) / 2,
                (control[1] + controls[i + 1][1]) / 2,
            )
            for step in range(1, CURVE_STEPS + 1):
                t = step / CURVE_STEPS
                u = 1 - t
                self._current.append(
                    (
                        u * u * start[0] + 2 * u * t * control[0] + t * t * target[0],
                        u * u * start[1] + 2 * u * t * control[1] + t * t * target[1],
                    )
                )
            start = target
        if not controls:
            self._current.append((float(end[0]), float(end[1])))

    def curveTo(self, *points):  # noqa: N802
        if not self._current or len(points) < 3:
            return
        (x1, y1), (x2, y2), (x3, y3) = points[-3:]
        x0, y0 = self._current[-1]
        for step in range(1, CURVE_STEPS + 1):
            t = step / CURVE_STEPS
            u = 1 - t
            self._current.append(
                (
                    u**3 * x0 + 3 * u * u * t * x1 + 3 * u * t * t * x2 + t**3 * x3,
                    u**3 * y0 + 3 * u * u * t * y1 + 3 * u * t * t * y2 + t**3 * y3,
                )
            )

    def closePath(self):  # noqa: N802
        self._flush()

    def endPath(self):  # noqa: N802
        self._flush()

    def _flush(self) -> None:
        if len(self._current) >= 3:
            self.contours.append(self._current)
        self._current = []


def _area(points: list[tuple[float, float]]) -> float:
    total = 0.0
    for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1]):
        total += x1 * y2 - x2 * y1
    return total / 2


class ShapedTextFont:
    """A HarfBuzz-shaped font at one pixel size. Implements the same interface as :class:`PilTextFont`."""

    def __init__(self, source: _FaceSource, size: int) -> None:
        self.source = source
        self.size = size
        self._key = (str(source.path), source.index)
        face = _load_face(*self._key)
        self._font = hb.Font(face)
        self._scale = size / float(face.upem)
        extents = self._font.get_font_extents("ltr")
        self.ascent = max(extents.ascender, int(face.upem * 0.8)) * self._scale
        self.descent = max(-extents.descender, int(face.upem * 0.2)) * self._scale
        self.line_height = int(max(size * 1.2, (self.ascent + self.descent) * 1.02))

    # -- layout
    def _shape(self, text: str):
        buffer = hb.Buffer()
        buffer.add_str(text)
        buffer.guess_segment_properties()
        hb.shape(self._font, buffer)
        return list(zip(buffer.glyph_infos, buffer.glyph_positions))

    def width(self, text: str) -> float:
        if not text:
            return 0.0
        return sum(pos.x_advance for _, pos in self._shape(text)) * self._scale

    @lru_cache(maxsize=2048)  # noqa: B019 - the font objects live for a single cover
    def _outline(self, gid: int) -> tuple[tuple[tuple[float, float], ...], ...]:
        pen = _OutlinePen()
        self._font.draw_glyph_with_pen(gid, pen)
        pen._flush()
        return tuple(tuple(contour) for contour in pen.contours)

    # -- drawing
    def draw(self, canvas: Image.Image, x: float, y: float, text: str, fill: tuple[int, int, int]) -> None:
        if not text.strip():
            return
        shaped = self._shape(text)
        scale = self._scale
        pad = int(self.size * 0.3) + 2
        box_w = int(math.ceil(sum(pos.x_advance for _, pos in shaped) * scale)) + 2 * pad
        box_h = int(math.ceil(self.ascent + self.descent)) + 2 * pad
        s = SUPERSAMPLE
        mask = Image.new("L", (box_w * s, box_h * s), 0)
        painter = ImageDraw.Draw(mask)
        baseline = (pad + self.ascent) * s
        pen_x = pad * s
        for info, pos in shaped:
            ox = pen_x + pos.x_offset * scale * s
            oy = baseline - pos.y_offset * scale * s
            contours = self._outline(info.codepoint)
            if contours:
                outer_sign = 1 if _area(list(max(contours, key=lambda c: abs(_area(list(c)))))) > 0 else -1
                holes = []
                for contour in contours:
                    points = [(ox + px * scale * s, oy - py * scale * s) for px, py in contour]
                    if (1 if _area(list(contour)) > 0 else -1) == outer_sign:
                        painter.polygon(points, fill=255)
                    else:
                        holes.append(points)
                for points in holes:
                    painter.polygon(points, fill=0)
            pen_x += pos.x_advance * scale * s
        mask = mask.resize((box_w, box_h), Image.LANCZOS)
        left, top = int(round(x)) - pad, int(round(y)) - pad
        layer = Image.new("RGBA", (box_w, box_h), fill + (255,))
        layer.putalpha(mask)
        canvas.alpha_composite(layer, dest=(max(left, 0), max(top, 0)), source=(max(-left, 0), max(-top, 0)))


def load_text_font(size: int, language: str = "English", bold: bool = False) -> TextFont:
    """Best available font for ``language``: HarfBuzz-shaped for Tamil and Hindi, plain Pillow otherwise."""
    if hb is not None and script_for(language) in SHAPED_SCRIPTS:
        source = find_shaping_font(language, bold)
        if source is not None:
            try:
                return ShapedTextFont(source, size)
            except Exception:  # noqa: BLE001 - never let a font problem stop the cover
                LOGGER.warning("Could not use %s for shaped text; falling back to Pillow", source.path, exc_info=True)
    return PilTextFont(load_pil_font(size, language, bold), size)
