"""Pillow-only helpers for coloring books: pure black-and-white line art, a small colored preview of the same picture,
a print-ready page, and a drawn (offline) fallback picture.

No numpy: every function works on ordinary Pillow images, so it runs wherever the rest of the app runs.
"""

from __future__ import annotations

import hashlib
import math
import random
from collections.abc import Sequence

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

from config import COLORING_PAGE_SIZE, COMPLEXITY_EASY, COMPLEXITY_HARD, COMPLEXITY_MEDIUM

_THRESHOLD = 150  # grey level below which a pixel counts as a drawn line
_MIN_INK = 0.015  # a usable page has some lines ...
_MAX_INK = 0.42  # ... but is not a dark, shaded picture
_PAGE_MARGIN = 55
_BORDER_WIDTH = 7
_ICON_SIZE = 270  # the small colored preview in the top-left corner of a "page with preview" page
_ICON_PAD = 12
_PAPER_TINT = (255, 249, 232)
_SMALL_AREA = 4  # areas of the preview smaller than this many pixels are drawn as ink, not as a color

# What a good page of each complexity looks like, measured on a small copy of the picture.
# max_ink: share of black; min_open: share of the page that is white areas big enough to color; min_area: size of such an area
# (share of the page); min_regions: how many such areas there must be at least.
_LIMITS: dict[str, dict[str, float]] = {
    COMPLEXITY_EASY: {"max_ink": 0.20, "min_open": 0.62, "min_area": 0.004, "min_regions": 4},
    COMPLEXITY_MEDIUM: {"max_ink": 0.28, "min_open": 0.50, "min_area": 0.002, "min_regions": 8},
    COMPLEXITY_HARD: {"max_ink": 0.36, "min_open": 0.38, "min_area": 0.001, "min_regions": 15},
}
_ANALYSIS_WIDTH = 320

# Warm, friendly colors for the small preview. Neighbouring areas get different colors because areas are numbered in reading order.
_PALETTE: tuple[tuple[int, int, int], ...] = (
    (239, 83, 80), (255, 167, 38), (255, 213, 79), (129, 199, 132), (79, 195, 247), (149, 117, 205),
    (240, 98, 146), (77, 182, 172), (255, 138, 101), (174, 213, 129), (100, 181, 246), (186, 104, 200),
)


# --------------------------------------------------------------------------------------
# Line art
# --------------------------------------------------------------------------------------
def to_line_art(image: Image.Image, size: tuple[int, int] | None = None, thicken: bool = False, hollow: bool = False) -> Image.Image:
    """Pure black lines on pure white (mode "L", values 0 and 255 only) from any generated picture.

    Grey shading, paper texture and tiny specks are removed; with ``size`` the picture is first enlarged smoothly so the lines
    stay crisp. ``thicken`` makes every line one pixel bolder, which prints better on a large page. ``hollow`` turns solid
    black areas into outlines, so every shape has white space inside that can be colored.
    """
    gray = ImageOps.autocontrast(image.convert("L"), cutoff=1)
    if size and gray.size != size:
        gray = gray.resize(size, Image.Resampling.LANCZOS)
    binary = gray.point(lambda value: 0 if value < _THRESHOLD else 255, mode="L")
    binary = binary.filter(ImageFilter.MedianFilter(3))
    if thicken:
        binary = binary.filter(ImageFilter.MinFilter(3))
    if hollow:
        binary = hollow_solid_areas(binary)
    return binary


def hollow_solid_areas(line_art: Image.Image, rim: int | None = None) -> Image.Image:
    """Keep only a rim of ``rim`` pixels along the edge of every thick black area, so it becomes an outline that can be colored.

    Lines thinner than twice the rim are untouched; only filled shapes (black leaves, black backgrounds, heavy shading) change.
    """
    gray = line_art.convert("L")
    rim = rim or max(4, max(gray.size) // 220)
    interior = gray
    for _ in range(rim):
        interior = interior.filter(ImageFilter.MaxFilter(3))  # grows the white, so the black shrinks from every edge
    # Where black still exists after shrinking, the pixel was deep inside a solid area: make it white.
    return ImageChops.lighter(gray, ImageChops.invert(interior))


def ink_ratio(line_art: Image.Image) -> float:
    """Share of the picture that is drawn in black (0 for an empty page, 1 for a black one)."""
    gray = line_art.convert("L")
    histogram = gray.histogram()
    dark = sum(histogram[:128])
    return dark / max(1, gray.width * gray.height)


def is_usable_line_art(line_art: Image.Image, complexity: str | None = None) -> tuple[bool, str]:
    """Reject blank pages, shaded pictures and (when ``complexity`` is given) pages with too little room to color.

    A good coloring page has clearly separated white areas that are big enough to color; the limits depend on the complexity.
    """
    ratio = ink_ratio(line_art)
    if ratio < _MIN_INK:
        return False, "The picture is almost blank."
    if ratio > _MAX_INK:
        return False, "The picture is too dark or shaded to color."
    limits = _LIMITS.get(complexity or "")
    if limits is None:
        return True, ""
    if ratio > limits["max_ink"]:
        return False, "The picture has too many dark lines to color comfortably."
    open_share, regions = open_areas(line_art, limits["min_area"])
    if regions < limits["min_regions"]:
        return False, "The picture has too few separate areas to color."
    if open_share < limits["min_open"]:
        return False, "Most of the picture is crowded with lines, so there is no room to color."
    return True, ""


def _label_regions(data: bytes, width: int, height: int) -> tuple[list[int], dict[int, int], dict[int, bool]]:
    """Connected white areas of a black-and-white picture (bytes, dark = line): per-pixel labels, area sizes and edge contact."""
    labels = [0] * (width * height)
    sizes: dict[int, int] = {}
    touches_border: dict[int, bool] = {}
    next_label = 0
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
    return labels, sizes, touches_border


def open_areas(line_art: Image.Image, min_area: float) -> tuple[float, int]:
    """(share of the page covered by white areas of at least ``min_area`` of the page, number of such areas)."""
    gray = line_art.convert("L")
    width = _ANALYSIS_WIDTH
    height = max(1, round(width * gray.height / gray.width))
    small = gray.resize((width, height), Image.Resampling.BOX).point(lambda value: 0 if value < 215 else 255, mode="L")
    _, sizes, _ = _label_regions(small.tobytes(), width, height)
    threshold = min_area * width * height
    big = [size for size in sizes.values() if size >= threshold]
    return sum(big) / (width * height), len(big)


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
    labels, sizes, touches_border = _label_regions(small.tobytes(), width, height)
    next_label = len(sizes)
    offset = int(hashlib.sha1(seed.encode("utf-8")).hexdigest()[:4], 16) if seed else 0
    colors: dict[int, tuple[int, int, int]] = {}
    # The largest area that reaches the edge is the paper around the picture: it keeps a soft cream tone.
    background = max((label for label in sizes if touches_border[label]), key=lambda label: sizes[label], default=0)
    palette_index = offset
    for label in range(1, next_label + 1):
        if label == background:
            colors[label] = _PAPER_TINT
        elif sizes[label] < _SMALL_AREA:
            colors[label] = (45, 38, 38)  # specks would only look like noise, so they join the lines
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
    """The printable page (white paper, a clean frame, the line art; optionally the colored preview in the top-left corner). No text."""
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
    area_w, area_h = width - 2 * inner, height - 2 * inner
    if not with_icon:
        art = _fit(line_art.convert("L"), area_w, height - inner - inner)
        page.paste(art.convert("RGB"), ((width - art.width) // 2, inner + (area_h - art.height) // 2))
        return page

    icon = _fit(colorize(line_art, _ICON_SIZE, seed), _ICON_SIZE, _ICON_SIZE)
    frame = (inner, inner, inner + icon.width + 2 * _ICON_PAD, inner + icon.height + 2 * _ICON_PAD)
    draw.rounded_rectangle(frame, radius=18, fill=(255, 255, 255), outline=(45, 38, 38), width=4)
    page.paste(icon, (inner + _ICON_PAD, inner + _ICON_PAD))

    # The drawing uses the whole page (also the space next to the preview). It is cropped to its content, made as big as possible
    # and placed so that none of its lines touch the preview frame.
    gray = line_art.convert("L")
    box = ImageOps.invert(gray).getbbox()
    if box:
        pad = 8
        gray = gray.crop((max(0, box[0] - pad), max(0, box[1] - pad), min(gray.width, box[2] + pad), min(gray.height, box[3] + pad)))
    keep_out = (frame[0] - 14, frame[1] - 14, frame[2] + 14, frame[3] + 14)
    options: list[tuple[Image.Image, int, int]] = []
    full = _fit(gray, area_w, area_h)
    x = inner + (area_w - full.width) // 2
    for y in (inner + (area_h - full.height) // 2, inner + area_h - full.height):
        if not _has_ink_in(full, x, y, keep_out):
            options.append((full, x, y))
            break
    if not options:
        below = _fit(gray, area_w, area_h - (keep_out[3] - inner))  # under the preview, full width
        right = _fit(gray, area_w - (keep_out[2] - inner), area_h)  # beside the preview, full height
        options = [
            (below, inner + (area_w - below.width) // 2, inner + area_h - below.height),
            (right, inner + area_w - right.width, inner + (area_h - right.height) // 2),
        ]
        options = [max(options, key=lambda option: option[0].width * option[0].height)]
    art, x, y = options[0]
    page.paste(art.convert("RGB"), (x, y))
    return page


def _has_ink_in(art: Image.Image, left: int, top: int, rect: tuple[int, int, int, int]) -> bool:
    """True when a line of ``art`` (placed at left, top) lies inside ``rect``."""
    x0, y0 = max(rect[0], left), max(rect[1], top)
    x1, y1 = min(rect[2], left + art.width), min(rect[3], top + art.height)
    if x0 >= x1 or y0 >= y1:
        return False
    return art.crop((x0 - left, y0 - top, x1 - left, y1 - top)).getextrema()[0] < 140


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


def make_line_art_placeholder(size: tuple[int, int], seed: str = "coloring", complexity: str = COMPLEXITY_MEDIUM) -> Image.Image:
    """A mandala drawn from closed outlines. Used only when no image model can be reached; the result is a real coloring page.

    Easy has two rings of a few big petals, medium three or four rings, hard five rings with many small petals.
    """
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
    rings = {COMPLEXITY_EASY: 2, COMPLEXITY_HARD: 5}.get(complexity) or rng.randint(3, 4)
    counts = {COMPLEXITY_EASY: (6, 8), COMPLEXITY_HARD: (12, 14, 16)}.get(complexity, (8, 10, 12, 14))
    for ring in range(rings):
        fraction = 0.86 - ring * (0.62 / rings)
        count = rng.choice(counts) + ring * (3 if complexity == COMPLEXITY_HARD else 2)
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
