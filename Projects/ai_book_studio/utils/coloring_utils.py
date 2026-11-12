"""Pillow-only helpers for coloring books: pure black-and-white line art, a small colored preview of the same picture,
a print-ready page, and a drawn (offline) fallback picture.

No numpy: every function works on ordinary Pillow images, so it runs wherever the rest of the app runs.
"""

from __future__ import annotations

import hashlib
import math
import random
from collections.abc import Sequence

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from config import COLORING_PAGE_SIZE

_THRESHOLD = 150  # grey level below which a pixel counts as a drawn line
_MIN_INK, _MAX_INK = 0.015, 0.42  # a usable page has some lines but is not a dark, shaded picture
_PAGE_MARGIN = 55
_BORDER_WIDTH = 7
_ICON_BAND = 360  # height of the preview strip at the top of a "page with icon" page
_ICON_SIZE = 290
_PAPER_TINT = (255, 249, 232)

# Warm, friendly colors for the small preview. Neighbouring areas get different colors because areas are numbered in reading order.
_PALETTE: tuple[tuple[int, int, int], ...] = (
    (239, 83, 80), (255, 167, 38), (255, 213, 79), (129, 199, 132), (79, 195, 247), (149, 117, 205),
    (240, 98, 146), (77, 182, 172), (255, 138, 101), (174, 213, 129), (100, 181, 246), (186, 104, 200),
)


# --------------------------------------------------------------------------------------
# Line art
# --------------------------------------------------------------------------------------
def to_line_art(image: Image.Image, size: tuple[int, int] | None = None, thicken: bool = False) -> Image.Image:
    """Pure black lines on pure white (mode "L", values 0 and 255 only) from any generated picture.

    Grey shading, paper texture and tiny specks are removed; with ``size`` the picture is first enlarged smoothly so the lines
    stay crisp. ``thicken`` makes every line one pixel bolder, which prints better on a large page.
    """
    gray = ImageOps.autocontrast(image.convert("L"), cutoff=1)
    if size and gray.size != size:
        gray = gray.resize(size, Image.Resampling.LANCZOS)
    binary = gray.point(lambda value: 0 if value < _THRESHOLD else 255, mode="L")
    binary = binary.filter(ImageFilter.MedianFilter(3))
    if thicken:
        binary = binary.filter(ImageFilter.MinFilter(3))
    return binary


def ink_ratio(line_art: Image.Image) -> float:
    """Share of the picture that is drawn in black (0 for an empty page, 1 for a black one)."""
    gray = line_art.convert("L")
    histogram = gray.histogram()
    dark = sum(histogram[:128])
    return dark / max(1, gray.width * gray.height)


def is_usable_line_art(line_art: Image.Image) -> tuple[bool, str]:
    """Reject blank pages and heavily shaded pictures, which are no use for coloring."""
    ratio = ink_ratio(line_art)
    if ratio < _MIN_INK:
        return False, "The picture is almost blank."
    if ratio > _MAX_INK:
        return False, "The picture is too dark or shaded to color."
    return True, ""


# --------------------------------------------------------------------------------------
# Colored preview of the same picture
# --------------------------------------------------------------------------------------
def colorize(line_art: Image.Image, width: int = _ICON_SIZE, seed: str = "") -> Image.Image:
    """A small colored version of the same picture: every closed area of the line art is filled with a color.

    The picture is the line art itself, so the preview always matches the page exactly. Lines stay dark.
    """
    gray = line_art.convert("L")
    height = max(1, round(width * gray.height / gray.width))
    # Thicken before shrinking so thin lines do not vanish and close small gaps; then keep only clear black and white.
    small = gray.filter(ImageFilter.MinFilter(5)).resize((width, height), Image.Resampling.BOX)
    small = small.point(lambda value: 0 if value < 200 else 255, mode="L")
    data = small.tobytes()
    labels = [0] * (width * height)
    offset = int(hashlib.sha1(seed.encode("utf-8")).hexdigest()[:4], 16) if seed else 0
    colors: dict[int, tuple[int, int, int]] = {}
    next_label = 0
    sizes: dict[int, int] = {}
    touches_border: dict[int, bool] = {}
    for start in range(width * height):
        if data[start] < 128 or labels[start]:
            continue
        next_label += 1
        stack = [start]
        labels[start] = next_label
        count = 0
        border = False
        while stack:
            position = stack.pop()
            count += 1
            y, x = divmod(position, width)
            if x == 0 or y == 0 or x == width - 1 or y == height - 1:
                border = True
            for neighbour, valid in (
                (position - 1, x > 0),
                (position + 1, x < width - 1),
                (position - width, y > 0),
                (position + width, y < height - 1),
            ):
                if valid and data[neighbour] >= 128 and not labels[neighbour]:
                    labels[neighbour] = next_label
                    stack.append(neighbour)
        sizes[next_label] = count
        touches_border[next_label] = border
    # The largest area that reaches the edge is the paper around the picture: it keeps a soft cream tone.
    background = max((label for label in sizes if touches_border[label]), key=lambda label: sizes[label], default=0)
    palette_index = offset
    for label in range(1, next_label + 1):
        if label == background:
            colors[label] = _PAPER_TINT
        else:
            colors[label] = _PALETTE[palette_index % len(_PALETTE)]
            palette_index += 5  # 5 and 12 share no factor, so colors cycle through the whole palette
    pixels = bytearray(width * height * 3)
    dark = (45, 38, 38)
    for position, label in enumerate(labels):
        r, g, b = colors[label] if label else dark
        pixels[position * 3 : position * 3 + 3] = bytes((r, g, b))
    return Image.frombytes("RGB", (width, height), bytes(pixels))


# --------------------------------------------------------------------------------------
# Page
# --------------------------------------------------------------------------------------
def _fit(image: Image.Image, box_width: int, box_height: int) -> Image.Image:
    scale = min(box_width / image.width, box_height / image.height)
    return image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.Resampling.LANCZOS)


def compose_page(
    line_art: Image.Image,
    with_icon: bool = False,
    seed: str = "",
    page_size: tuple[int, int] = COLORING_PAGE_SIZE,
) -> Image.Image:
    """The printable page (white paper, a clean frame, the line art; optionally the colored preview at the top). No text."""
    width, height = page_size
    page = Image.new("RGB", page_size, "white")
    draw = ImageDraw.Draw(page)
    draw.rounded_rectangle(
        (_PAGE_MARGIN, _PAGE_MARGIN, width - _PAGE_MARGIN, height - _PAGE_MARGIN),
        radius=36,
        outline="black",
        width=_BORDER_WIDTH,
    )
    inner = _PAGE_MARGIN + _BORDER_WIDTH + 28
    top = inner
    if with_icon:
        icon = colorize(line_art, _ICON_SIZE, seed)
        icon = _fit(icon, _ICON_SIZE, _ICON_BAND - 70)
        frame_x = (width - icon.width) // 2
        frame_y = inner + 6
        draw.rounded_rectangle(
            (frame_x - 14, frame_y - 14, frame_x + icon.width + 14, frame_y + icon.height + 14),
            radius=18,
            fill=(255, 255, 255),
            outline=(45, 38, 38),
            width=4,
        )
        page.paste(icon, (frame_x, frame_y))
        top = inner + _ICON_BAND
        draw.line((inner + 40, top - 22, width - inner - 40, top - 22), fill=(45, 38, 38), width=3)
    art = _fit(line_art.convert("L"), width - 2 * inner, height - inner - top)
    page.paste(art.convert("RGB"), ((width - art.width) // 2, top + (height - inner - top - art.height) // 2))
    return page


# --------------------------------------------------------------------------------------
# Drawn fallback (no network, no model)
# --------------------------------------------------------------------------------------
def _petal(centre: tuple[float, float], angle: float, distance: float, length: float, breadth: float) -> list[tuple[float, float]]:
    px = centre[0] + distance * math.cos(angle)
    py = centre[1] + distance * math.sin(angle)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    points = []
    for step in range(36):
        t = 2 * math.pi * step / 36
        lx, ly = length * math.cos(t), breadth * math.sin(t)
        points.append((px + lx * cos_a - ly * sin_a, py + lx * sin_a + ly * cos_a))
    return points


def make_line_art_placeholder(size: tuple[int, int], seed: str = "coloring") -> Image.Image:
    """A mandala drawn from closed outlines. Used only when no image model can be reached; the result is a real coloring page."""
    rng = random.Random(hashlib.sha1(seed.encode("utf-8")).digest())
    width, height = size
    image = Image.new("L", size, 255)
    draw = ImageDraw.Draw(image)
    centre = (width / 2, height / 2)
    radius = min(width, height) * 0.46
    line = max(4, int(min(width, height) / 170))

    def outline(points: Sequence[tuple[float, float]]) -> None:
        draw.polygon(list(points), fill=255)
        draw.line([*points, points[0]], fill=0, width=line, joint="curve")

    def circle(r: float) -> None:
        draw.ellipse((centre[0] - r, centre[1] - r, centre[0] + r, centre[1] + r), fill=255, outline=0, width=line)

    circle(radius)
    rings = rng.randint(3, 4)
    for ring in range(rings):
        fraction = 0.86 - ring * (0.62 / rings)
        count = rng.choice((8, 10, 12, 14)) + ring * 2
        distance = radius * fraction * 0.78
        length = radius * 0.30 * (1 - ring * 0.12)
        breadth = length * rng.uniform(0.34, 0.5)
        offset = rng.uniform(0, math.pi)
        for index in range(count):
            outline(_petal(centre, offset + 2 * math.pi * index / count, distance, length, breadth))
        circle(radius * (fraction - 0.2))
    circle(radius * 0.14)
    circle(radius * 0.06)
    return image
