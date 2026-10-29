"""Compose the final cover: textless artwork plus readable title, subtitle and author text (Pillow)."""

from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from utils.image_utils import COVER_SIZE, load_pil_font, make_placeholder_image, wrap_text


def _fit_block(
    draw: ImageDraw.ImageDraw,
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
        font = load_pil_font(size, language, bold)
        lines = wrap_text(draw, text, font, max_width)
        line_height = int(size * 1.18)
        if len(lines) * line_height <= max_height or size <= min_size:
            return font, lines, line_height
        size -= 4


def _draw_centered(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    font,
    line_height: int,
    top: int,
    width: int,
    fill: tuple[int, int, int],
    stroke: int,
) -> int:
    y = top
    for line in lines:
        line_width = draw.textlength(line, font=font)
        draw.text(
            ((width - line_width) / 2, y),
            line,
            font=font,
            fill=fill,
            stroke_width=stroke,
            stroke_fill=(0, 0, 0),
        )
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

    title_font, title_lines, title_lh = _fit_block(draw, title, language, True, max_width, int(height * 0.15), 108, 44)
    y = _draw_centered(draw, title_lines, title_font, title_lh, int(height * 0.045), width, (255, 255, 255), 0)
    if subtitle.strip():
        sub_font, sub_lines, sub_lh = _fit_block(draw, subtitle, language, False, max_width, int(height * 0.06), 40, 22)
        y = _draw_centered(draw, sub_lines, sub_font, sub_lh, y + 10, width, (232, 232, 242), 0)
    rule_y = min(y + 14, title_solid - 6)
    draw.line([(width * 0.38, rule_y), (width * 0.62, rule_y)], fill=gold, width=3)

    band_h = height - art_bottom
    author_font, author_lines, author_lh = _fit_block(draw, author, language, True, max_width, int(band_h * 0.7), 52, 28)
    author_top = art_bottom + (band_h - len(author_lines) * author_lh) // 2
    draw.line([(width * 0.38, art_bottom + 12), (width * 0.62, art_bottom + 12)], fill=gold, width=3)
    _draw_centered(draw, author_lines, author_font, author_lh, author_top + 8, width, (255, 255, 255), 0)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp = output_path.with_name(output_path.stem + ".tmp.png")
    canvas.convert("RGB").save(temp, "PNG")
    os.replace(temp, output_path)
    return output_path
