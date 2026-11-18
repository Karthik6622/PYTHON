"""Compose the final cover: textless artwork plus readable title, subtitle and author text (Pillow).

The first cover of a book uses the classic structure (title band on top, artwork in the middle, author band at the bottom). A cover made
from the user's own prompt is arranged by a ``CoverLayout`` (see ``generators.cover_layout``): text zone, alignment, palette, frame.
"""

from __future__ import annotations

import math
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from config import COLORING_PAGE_SIZE
from generators.cover_layout import COLORING_PALETTES, PALETTE_COLORS, CoverLayout, resolve
from utils.image_utils import COVER_SIZE, make_placeholder_image, wrap_by_width
from utils.text_shaping import load_text_font


def _fit_block(
    text: str,
    language: str,
    bold: bool,
    max_width: int,
    max_height: int,
    start_size: int,
    min_size: int,
):
    """Find the largest font size at which the wrapped text fits the box."""
    size = start_size
    while True:
        font = load_text_font(size, language, bold)
        lines = wrap_by_width(text, font.width, max_width)
        line_height = font.line_height
        if len(lines) * line_height <= max_height or size <= min_size:
            return font, lines, line_height
        size -= 4


def _draw_centered(
    canvas: Image.Image,
    lines: list[str],
    font,
    line_height: int,
    top: int,
    width: int,
    fill: tuple[int, int, int],
) -> int:
    y = top
    for line in lines:
        font.draw(canvas, (width - font.width(line)) / 2, y, line, fill)
        y += line_height
    return y


def _draw_aligned(canvas: Image.Image, lines: list[str], font, line_height: int, top: int, width: int, fill: tuple[int, int, int], align: str, margin: int) -> int:
    """Like ``_draw_centered`` but also left- or right-aligned inside the margins."""
    y = top
    for line in lines:
        x = {"left": margin, "right": width - margin - font.width(line)}.get(align, (width - font.width(line)) / 2)
        font.draw(canvas, x, y, line, fill)
        y += line_height
    return y


def _apply_case(text: str, case: str) -> str:
    if case == "upper":
        return text.upper()
    if case == "title":
        return text.title() if text.islower() or text.isupper() else text
    return text


def _panel_color(artwork: Image.Image) -> tuple[int, int, int]:
    """A dark shade of the artwork's average colour, used for the text bands so they blend with the picture."""
    r, g, b = artwork.resize((1, 1), Image.BOX).getpixel((0, 0))
    return int(r * 0.22) + 6, int(g * 0.22) + 6, int(b * 0.22) + 8


def _light_panel_color(artwork: Image.Image) -> tuple[int, int, int]:
    r, g, b = artwork.resize((1, 1), Image.BOX).getpixel((0, 0))
    return min(int(r * 0.2) + 200, 255), min(int(g * 0.2) + 196, 255), min(int(b * 0.2) + 190, 255)


def _draw_frame(draw: ImageDraw.ImageDraw, width: int, height: int, style: str, accent: tuple[int, int, int]) -> None:
    """The printed-look frame: double line, single line, corner marks or none."""
    dim = tuple(int(c * 0.7) for c in accent)
    if style == "double":
        draw.rectangle([18, 18, width - 19, height - 19], outline=accent, width=3)
        draw.rectangle([28, 28, width - 29, height - 29], outline=dim, width=1)
    elif style == "single":
        draw.rectangle([24, 24, width - 25, height - 25], outline=accent, width=3)
    elif style == "corners":
        arm = int(width * 0.09)
        for x, y, dx, dy in ((26, 26, 1, 1), (width - 27, 26, -1, 1), (26, height - 27, 1, -1), (width - 27, height - 27, -1, -1)):
            draw.line([(x, y), (x + dx * arm, y)], fill=accent, width=4)
            draw.line([(x, y), (x, y + dy * arm)], fill=accent, width=4)


def _scrim(canvas: Image.Image, top: int, bottom: int, rgb: tuple[int, int, int], mode: str, edge: str) -> Image.Image:
    """Colour veil behind text that fades into the picture. ``edge`` = where it is anchored: top, bottom or mid (feathered both ways)."""
    if mode == "none" or bottom <= top:
        return canvas
    peak = 0.94 if mode == "solid" else 0.82
    veil = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    shader = ImageDraw.Draw(veil)
    span = bottom - top
    for y in range(max(top, 0), min(bottom, canvas.size[1])):
        t = (y - top) / span
        if edge == "top":
            fade = 1.0 if (mode == "solid" and t < 0.7) else (1 - t) ** 1.4 if mode != "solid" else 1 - ((t - 0.7) / 0.3) ** 1.2
        elif edge == "bottom":
            fade = 1.0 if (mode == "solid" and t > 0.3) else t**1.4 if mode != "solid" else (t / 0.3) ** 1.2
        else:
            fade = math.sin(math.pi * t) ** (0.6 if mode == "solid" else 0.9)
        shader.line([(0, y), (canvas.size[0], y)], fill=rgb + (int(255 * peak * max(min(fade, 1.0), 0.0)),))
    return Image.alpha_composite(canvas, veil)


def _shadowed(canvas: Image.Image, lines: list[str], font, line_height: int, top: int, width: int, fill: tuple[int, int, int], align: str, margin: int) -> Image.Image:
    """Text with a soft dark shadow, for text that has no veil behind it."""
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    _draw_aligned(shadow, lines, font, line_height, top + 4, width, (0, 0, 0), align, margin)
    canvas = Image.alpha_composite(canvas, shadow.filter(ImageFilter.GaussianBlur(7)))
    _draw_aligned(canvas, lines, font, line_height, top, width, fill, align, margin)
    return canvas


def _compose_dynamic(artwork: Image.Image, title: str, subtitle: str, author: str, language: str, layout: CoverLayout) -> Image.Image:
    """Overlay and poster covers: full-bleed artwork with the text placed by the layout."""
    width, height = COVER_SIZE
    layout = resolve(layout, artwork)
    text_color, sub_color, accent, light = PALETTE_COLORS[layout.palette]
    veil = _light_panel_color(artwork) if light else _panel_color(artwork)
    canvas = ImageOps.fit(artwork, COVER_SIZE, Image.LANCZOS, centering=(0.5, 0.4)).convert("RGBA")

    margin = int(width * 0.09)
    max_width = width - 2 * margin
    scale = layout.title_scale
    title = _apply_case(title, layout.title_case)
    t_font, t_lines, t_lh = _fit_block(title, language, True, max_width, int(height * 0.18 * scale), int(112 * scale), 44)
    s_font = s_lines = None
    s_lh = 0
    if subtitle.strip():
        s_font, s_lines, s_lh = _fit_block(subtitle, language, False, max_width, int(height * 0.06), 40, 22)
    a_font, a_lines, a_lh = _fit_block(author, language, True, max_width, int(height * 0.08), 52, 28)

    rule_gap = 30 if layout.rule else 0
    title_h = len(t_lines) * t_lh + (len(s_lines) * s_lh + 12 if s_lines else 0) + rule_gap
    author_h = len(a_lines) * a_lh
    pad = int(height * 0.035)
    zone = layout.title_zone
    author_zone = layout.author_zone if zone != "bottom" or layout.author_zone == "top" else "bottom"
    if zone == "top" and author_zone == "top":
        author_zone = "bottom"
    a_top = int(height * 0.045) if author_zone == "top" else height - int(height * 0.05) - author_h
    if zone == "top":
        t_top = int(height * 0.05)
    elif zone == "bottom":
        t_top = (a_top - pad if author_zone == "bottom" else height - int(height * 0.07)) - title_h
    else:
        t_top = (height - title_h) // 2 - int(height * 0.04)

    mode = layout.scrim
    if zone == "top":
        canvas = _scrim(canvas, 0, t_top + title_h + pad * 2, veil, mode, "top")
    elif zone == "bottom":
        canvas = _scrim(canvas, t_top - pad * 2, height, veil, mode, "bottom")
    else:
        canvas = _scrim(canvas, t_top - pad * 2, t_top + title_h + pad * 2, veil, mode, "mid")
    if author_zone == "bottom" and zone != "bottom":
        canvas = _scrim(canvas, a_top - pad * 2, height, veil, mode, "bottom")
    elif author_zone == "top" and zone != "top":
        canvas = _scrim(canvas, 0, a_top + author_h + pad * 2, veil, mode, "top")

    draw_text = _shadowed if mode == "none" else None

    def put(lines, font, lh, top, fill):  # noqa: ANN001, ANN202
        nonlocal canvas
        if draw_text:
            canvas = draw_text(canvas, lines, font, lh, top, width, fill, layout.align, margin)
        else:
            _draw_aligned(canvas, lines, font, lh, top, width, fill, layout.align, margin)
        return top + len(lines) * lh

    y = put(t_lines, t_font, t_lh, t_top, text_color)
    if s_lines:
        y = put(s_lines, s_font, s_lh, y + 12, sub_color)
    draw = ImageDraw.Draw(canvas)
    if layout.rule:
        length = int(width * 0.24)
        x0 = {"left": margin, "right": width - margin - length}.get(layout.align, (width - length) // 2)
        draw.line([(x0, y + 14), (x0 + length, y + 14)], fill=accent, width=3)
    put(a_lines, a_font, a_lh, a_top, text_color)
    _draw_frame(draw, width, height, layout.frame, accent)
    return canvas.convert("RGB")


def compose_cover(
    art_path: Path | None,
    title: str,
    subtitle: str,
    author: str,
    output_path: Path,
    language: str = "English",
    layout: CoverLayout | None = None,
) -> Path:
    """Create ``cover_final.png`` (1024x1536).

    Default layout: title band on top, artwork in the middle, author band at the bottom. The text sits on solid bands that fade
    into the picture, so it never covers the characters' faces or the focal subject. Any other ``layout`` rearranges the text.
    """
    width, height = COVER_SIZE
    if art_path and Path(art_path).exists():
        with Image.open(art_path) as art:
            artwork = art.convert("RGB")
    else:
        artwork = make_placeholder_image(COVER_SIZE, seed=title).convert("RGB")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp = output_path.with_name(output_path.stem + ".tmp.png")
    if layout is not None and layout.structure in {"overlay", "poster"}:
        _compose_dynamic(artwork, title, subtitle, author, language, layout).save(temp, "PNG")
        os.replace(temp, output_path)
        return output_path

    layout = layout or CoverLayout()
    text_color, sub_color, gold, light = PALETTE_COLORS.get(layout.palette, PALETTE_COLORS["dark"])
    title = _apply_case(title, layout.title_case)
    panel = _light_panel_color(artwork) if light else _panel_color(artwork)
    art_top, art_bottom = int(height * 0.2), int(height * 0.9)
    title_solid, title_fade = int(height * 0.27), int(height * 0.06)
    author_fade = int(height * 0.07)

    # Artwork fills the middle area; the crop leans slightly upwards because faces sit in the upper half of a portrait.
    canvas = Image.new("RGBA", COVER_SIZE, panel + (255,))
    middle = ImageOps.fit(artwork, (width, art_bottom - art_top), Image.LANCZOS, centering=(0.5, 0.4))
    canvas.paste(middle.convert("RGBA"), (0, art_top))

    fade = Image.new("RGBA", COVER_SIZE, (0, 0, 0, 0))
    shader = ImageDraw.Draw(fade)
    shader.rectangle([0, 0, width, title_solid], fill=panel + (255,))
    for i in range(title_fade):
        shader.line([(0, title_solid + i), (width, title_solid + i)], fill=panel + (int(255 * (1 - i / title_fade) ** 1.6),))
    shader.rectangle([0, art_bottom, width, height], fill=panel + (255,))
    for i in range(author_fade):
        shader.line([(0, art_bottom - 1 - i), (width, art_bottom - 1 - i)], fill=panel + (int(255 * (1 - i / author_fade) ** 1.6),))
    canvas = Image.alpha_composite(canvas, fade)
    draw = ImageDraw.Draw(canvas)

    margin = int(width * 0.09)
    max_width = width - 2 * margin

    title_font, title_lines, title_lh = _fit_block(title, language, True, max_width, int(height * 0.15), 108, 44)
    y = _draw_centered(canvas, title_lines, title_font, title_lh, int(height * 0.045), width, text_color)
    if subtitle.strip():
        sub_font, sub_lines, sub_lh = _fit_block(subtitle, language, False, max_width, int(height * 0.06), 40, 22)
        y = _draw_centered(canvas, sub_lines, sub_font, sub_lh, y + 10, width, sub_color)
    rule_y = min(y + 14, title_solid - 6)
    if layout.rule:
        draw.line([(width * 0.38, rule_y), (width * 0.62, rule_y)], fill=gold, width=3)

    band_h = height - art_bottom
    author_font, author_lines, author_lh = _fit_block(author, language, True, max_width, int(band_h * 0.7), 52, 28)
    author_top = art_bottom + (band_h - len(author_lines) * author_lh) // 2
    if layout.rule:
        draw.line([(width * 0.38, art_bottom + 12), (width * 0.62, art_bottom + 12)], fill=gold, width=3)
    _draw_centered(canvas, author_lines, author_font, author_lh, author_top + 8, width, text_color)

    # A fine double gold frame gives the cover a finished, printed look. It sits outside every text margin.
    _draw_frame(draw, width, height, layout.frame, gold)

    canvas.convert("RGB").save(temp, "PNG")
    os.replace(temp, output_path)
    return output_path


# --------------------------------------------------------------------------------------
# Coloring book cover
# --------------------------------------------------------------------------------------
_INK = (52, 41, 92)  # deep indigo for the title
_ACCENTS = ((239, 83, 80), (255, 167, 38), (255, 213, 79), (129, 199, 132), (79, 195, 247), (149, 117, 205))


def _pill(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill, outline=None, width: int = 0) -> None:
    draw.rounded_rectangle(box, radius=(box[3] - box[1]) // 2, fill=fill, outline=outline, width=width)


def compose_coloring_cover(
    art_path: Path | None,
    title: str,
    subtitle: str,
    author: str,
    output_path: Path,
    badge: str = "",
    language: str = "English",
    layout: CoverLayout | None = None,
) -> Path:
    """Create the coloring-book cover (1275x1650, the same size as the pages).

    Full-bleed colorful artwork, a cream title card with a rainbow edge, a pill badge ("20 coloring pages") and an author
    ribbon. All text sits on solid panels, so it stays readable on any artwork. The title and author are drawn by the app,
    never by the image model, so the spelling is always correct. A ``layout`` moves the card (top / middle / bottom), changes
    the colours and the frame; without one the classic arrangement is used.
    """
    width, height = COLORING_PAGE_SIZE
    if art_path and Path(art_path).exists():
        with Image.open(art_path) as art:
            artwork = art.convert("RGB")
    else:
        artwork = make_placeholder_image(COLORING_PAGE_SIZE, seed=title).convert("RGB")
    canvas = ImageOps.fit(artwork, COLORING_PAGE_SIZE, Image.LANCZOS, centering=(0.5, 0.45)).convert("RGBA")

    dynamic = layout is not None and not layout.is_default
    layout = layout or CoverLayout()
    ink, card_fill, card_accent = COLORING_PALETTES.get(layout.palette, COLORING_PALETTES["dark"]) if dynamic else (_INK, (255, 250, 238), (255, 167, 38))
    title = _apply_case(title, layout.title_case) if dynamic else title
    zone = layout.title_zone if dynamic and layout.title_zone in {"top", "center", "bottom"} else "top"

    margin = 120
    inner_width = width - 2 * margin - 120
    scale = layout.title_scale if dynamic else 1.0
    title_font, title_lines, title_lh = _fit_block(title, language, True, inner_width, int(height * 0.19 * scale), int(124 * scale), 52)
    sub_font = sub_lines = None
    sub_lh = 0
    if subtitle.strip():
        sub_font, sub_lines, sub_lh = _fit_block(subtitle, language, False, inner_width, int(height * 0.07), 48, 26)
    pad = 54
    card_height = pad * 2 + len(title_lines) * title_lh + (len(sub_lines) * sub_lh + 20 if sub_lines else 0)
    card_top = {"top": 118, "center": (height - card_height) // 2 - 70, "bottom": height - 440 - card_height}[zone]
    card = (margin, card_top, width - margin, card_top + card_height)

    shadow = Image.new("RGBA", COLORING_PAGE_SIZE, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((card[0] + 6, card[1] + 14, card[2] + 6, card[3] + 14), radius=56, fill=(0, 0, 0, 110))
    canvas = Image.alpha_composite(canvas, shadow.filter(ImageFilter.GaussianBlur(14)))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(card, radius=56, fill=card_fill + (255,), outline=ink, width=7)
    draw.rounded_rectangle((card[0] + 14, card[1] + 14, card[2] - 14, card[3] - 14), radius=44, outline=card_accent + (255,), width=4)

    y = _draw_centered(canvas, title_lines, title_font, title_lh, card[1] + pad, width, ink)
    if sub_lines:
        _draw_centered(canvas, sub_lines, sub_font, sub_lh, y + 16, width, tuple(min(c + 44, 255) for c in ink))
    # A row of colored dots under the card, like paint drops.
    if layout.rule or not dynamic:
        dots_y = card[3] + 38
        for index, color in enumerate(_ACCENTS):
            cx = width // 2 + (index - (len(_ACCENTS) - 1) / 2) * 62
            draw.ellipse((cx - 17, dots_y - 17, cx + 17, dots_y + 17), fill=color + (255,), outline=(255, 255, 255, 255), width=4)

    if badge.strip():
        badge_font, badge_lines, badge_lh = _fit_block(badge.strip().upper(), language, True, inner_width, 70, 44, 24)
        text_width = max(badge_font.width(line) for line in badge_lines)
        box_width = text_width + 110
        top = 150 if zone == "bottom" else height - 330
        _pill(draw, (int((width - box_width) / 2), top, int((width + box_width) / 2), top + 100), card_accent + (255,), (255, 255, 255, 255), 6)
        _draw_centered(canvas, badge_lines, badge_font, badge_lh, top + (100 - badge_lh) // 2, width, (255, 255, 255))

    if author.strip():
        author_font, author_lines, author_lh = _fit_block(author, language, True, width - 2 * margin - 160, 80, 56, 28)
        box_height = len(author_lines) * author_lh + 56
        top = height - 150 - box_height // 2
        draw.rounded_rectangle((margin + 60, top, width - margin - 60, top + box_height), radius=34, fill=ink + (240,), outline=(255, 255, 255, 255), width=5)
        _draw_centered(canvas, author_lines, author_font, author_lh, top + 28, width, (255, 255, 255))

    # A white print border with a fine gold line inside it.
    if not dynamic or layout.frame != "none":
        draw.rectangle([0, 0, width - 1, height - 1], outline=(255, 255, 255, 255), width=30)
    if not dynamic or layout.frame in {"double", "corners"}:
        draw.rounded_rectangle([34, 34, width - 35, height - 35], radius=30, outline=(214, 178, 94, 255), width=4)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp = output_path.with_name(output_path.stem + ".tmp.png")
    canvas.convert("RGB").save(temp, "PNG")
    os.replace(temp, output_path)
    return output_path
