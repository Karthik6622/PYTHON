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


def compose_cover(
    art_path: Path | None,
    title: str,
    subtitle: str,
    author: str,
    output_path: Path,
    language: str = "English",
) -> Path:
    """Create ``cover_final.png`` (1024x1536). The artwork is centre-cropped to fill the cover without distortion."""
    width, height = COVER_SIZE
    if art_path and Path(art_path).exists():
        with Image.open(art_path) as art:
            artwork = ImageOps.fit(art.convert("RGB"), COVER_SIZE, Image.LANCZOS, centering=(0.5, 0.5))
    else:
        artwork = make_placeholder_image(COVER_SIZE, seed=title)

    # Dark gradients behind the text areas keep white lettering readable on any artwork.
    shade = Image.new("RGBA", COVER_SIZE, (0, 0, 0, 0))
    shader = ImageDraw.Draw(shade)
    top_band, bottom_band = int(height * 0.42), int(height * 0.2)
    for y in range(top_band):
        shader.line([(0, y), (width, y)], fill=(0, 0, 0, int(205 * (1 - y / top_band) ** 1.4)))
    for y in range(bottom_band):
        shader.line([(0, height - 1 - y), (width, height - 1 - y)], fill=(0, 0, 0, int(215 * (1 - y / bottom_band) ** 1.2)))
    canvas = Image.alpha_composite(artwork.convert("RGBA"), shade)
    draw = ImageDraw.Draw(canvas)

    margin = int(width * 0.09)
    max_width = width - 2 * margin
    title_font, title_lines, title_lh = _fit_block(draw, title, language, True, max_width, int(height * 0.24), 118, 52)
    y = _draw_centered(draw, title_lines, title_font, title_lh, int(height * 0.07), width, (255, 255, 255), 4)
    if subtitle.strip():
        sub_font, sub_lines, sub_lh = _fit_block(draw, subtitle, language, False, max_width, int(height * 0.1), 46, 26)
        _draw_centered(draw, sub_lines, sub_font, sub_lh, y + 18, width, (238, 238, 248), 2)
    author_font, author_lines, author_lh = _fit_block(draw, author, language, True, max_width, int(height * 0.09), 56, 30)
    author_top = height - int(height * 0.075) - len(author_lines) * author_lh
    _draw_centered(draw, author_lines, author_font, author_lh, author_top, width, (255, 255, 255), 3)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp = output_path.with_name(output_path.stem + ".tmp.png")
    canvas.convert("RGB").save(temp, "PNG")
    os.replace(temp, output_path)
    return output_path
