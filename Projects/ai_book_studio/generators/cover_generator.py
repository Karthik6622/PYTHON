"""Compose the final cover: textless artwork plus readable title, subtitle and author text (Pillow)."""

from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from config import COLORING_PAGE_SIZE
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


def _panel_color(artwork: Image.Image) -> tuple[int, int, int]:
    """A dark shade of the artwork's average colour, used for the text bands so they blend with the picture."""
    r, g, b = artwork.resize((1, 1), Image.BOX).getpixel((0, 0))
    return int(r * 0.22) + 6, int(g * 0.22) + 6, int(b * 0.22) + 8


def compose_cover(
    art_path: Path | None,
    title: str,
    subtitle: str,
    author: str,
    output_path: Path,
    language: str = "English",
) -> Path:
    """Create ``cover_final.png`` (1024x1536).

    Layout: title band on top, artwork in the middle, author band at the bottom. The text sits on solid bands that fade
    into the picture, so it never covers the characters' faces or the focal subject.
    """
    width, height = COVER_SIZE
    if art_path and Path(art_path).exists():
        with Image.open(art_path) as art:
            artwork = art.convert("RGB")
    else:
        artwork = make_placeholder_image(COVER_SIZE, seed=title).convert("RGB")

    panel = _panel_color(artwork)
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
    gold = (214, 178, 94)

    title_font, title_lines, title_lh = _fit_block(title, language, True, max_width, int(height * 0.15), 108, 44)
    y = _draw_centered(canvas, title_lines, title_font, title_lh, int(height * 0.045), width, (255, 255, 255))
    if subtitle.strip():
        sub_font, sub_lines, sub_lh = _fit_block(subtitle, language, False, max_width, int(height * 0.06), 40, 22)
        y = _draw_centered(canvas, sub_lines, sub_font, sub_lh, y + 10, width, (232, 232, 242))
    rule_y = min(y + 14, title_solid - 6)
    draw.line([(width * 0.38, rule_y), (width * 0.62, rule_y)], fill=gold, width=3)

    band_h = height - art_bottom
    author_font, author_lines, author_lh = _fit_block(author, language, True, max_width, int(band_h * 0.7), 52, 28)
    author_top = art_bottom + (band_h - len(author_lines) * author_lh) // 2
    draw.line([(width * 0.38, art_bottom + 12), (width * 0.62, art_bottom + 12)], fill=gold, width=3)
    _draw_centered(canvas, author_lines, author_font, author_lh, author_top + 8, width, (255, 255, 255))

    # A fine double gold frame gives the cover a finished, printed look. It sits outside every text margin.
    draw.rectangle([18, 18, width - 19, height - 19], outline=gold, width=3)
    draw.rectangle([28, 28, width - 29, height - 29], outline=(150, 124, 66), width=1)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp = output_path.with_name(output_path.stem + ".tmp.png")
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
) -> Path:
    """Create the coloring-book cover (1275x1650, the same size as the pages).

    Full-bleed colorful artwork, a cream title card with a rainbow edge, a pill badge ("20 coloring pages") and an author
    ribbon. All text sits on solid panels, so it stays readable on any artwork. The title and author are drawn by the app,
    never by the image model, so the spelling is always correct.
    """
    width, height = COLORING_PAGE_SIZE
    if art_path and Path(art_path).exists():
        with Image.open(art_path) as art:
            artwork = art.convert("RGB")
    else:
        artwork = make_placeholder_image(COLORING_PAGE_SIZE, seed=title).convert("RGB")
    canvas = ImageOps.fit(artwork, COLORING_PAGE_SIZE, Image.LANCZOS, centering=(0.5, 0.45)).convert("RGBA")

    margin = 120
    inner_width = width - 2 * margin - 120
    title_font, title_lines, title_lh = _fit_block(title, language, True, inner_width, int(height * 0.19), 124, 52)
    sub_font = sub_lines = None
    sub_lh = 0
    if subtitle.strip():
        sub_font, sub_lines, sub_lh = _fit_block(subtitle, language, False, inner_width, int(height * 0.07), 48, 26)
    pad = 54
    card_height = pad * 2 + len(title_lines) * title_lh + (len(sub_lines) * sub_lh + 20 if sub_lines else 0)
    card = (margin, 118, width - margin, 118 + card_height)

    shadow = Image.new("RGBA", COLORING_PAGE_SIZE, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((card[0] + 6, card[1] + 14, card[2] + 6, card[3] + 14), radius=56, fill=(0, 0, 0, 110))
    canvas = Image.alpha_composite(canvas, shadow.filter(ImageFilter.GaussianBlur(14)))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(card, radius=56, fill=(255, 250, 238, 255), outline=_INK, width=7)
    draw.rounded_rectangle((card[0] + 14, card[1] + 14, card[2] - 14, card[3] - 14), radius=44, outline=(255, 167, 38, 255), width=4)

    y = _draw_centered(canvas, title_lines, title_font, title_lh, card[1] + pad, width, _INK)
    if sub_lines:
        _draw_centered(canvas, sub_lines, sub_font, sub_lh, y + 16, width, (96, 84, 130))
    # A row of colored dots under the card, like paint drops.
    dots_y = card[3] + 38
    for index, color in enumerate(_ACCENTS):
        cx = width // 2 + (index - (len(_ACCENTS) - 1) / 2) * 62
        draw.ellipse((cx - 17, dots_y - 17, cx + 17, dots_y + 17), fill=color + (255,), outline=(255, 255, 255, 255), width=4)

    if badge.strip():
        badge_font, badge_lines, badge_lh = _fit_block(badge.strip().upper(), language, True, inner_width, 70, 44, 24)
        text_width = max(badge_font.width(line) for line in badge_lines)
        box_width = text_width + 110
        top = height - 330
        _pill(draw, (int((width - box_width) / 2), top, int((width + box_width) / 2), top + 100), (255, 167, 38, 255), (255, 255, 255, 255), 6)
        _draw_centered(canvas, badge_lines, badge_font, badge_lh, top + (100 - badge_lh) // 2, width, (255, 255, 255))

    if author.strip():
        author_font, author_lines, author_lh = _fit_block(author, language, True, width - 2 * margin - 160, 80, 56, 28)
        box_height = len(author_lines) * author_lh + 56
        top = height - 150 - box_height // 2
        draw.rounded_rectangle((margin + 60, top, width - margin - 60, top + box_height), radius=34, fill=_INK + (240,), outline=(255, 255, 255, 255), width=5)
        _draw_centered(canvas, author_lines, author_font, author_lh, top + 28, width, (255, 255, 255))

    # A white print border with a fine gold line inside it.
    draw.rectangle([0, 0, width - 1, height - 1], outline=(255, 255, 255, 255), width=30)
    draw.rounded_rectangle([34, 34, width - 35, height - 35], radius=30, outline=(214, 178, 94, 255), width=4)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp = output_path.with_name(output_path.stem + ".tmp.png")
    canvas.convert("RGB").save(temp, "PNG")
    os.replace(temp, output_path)
    return output_path
