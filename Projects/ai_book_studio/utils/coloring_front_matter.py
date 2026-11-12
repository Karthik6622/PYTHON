"""Optional front pages of a coloring book (title, copyright, "this book belongs to", welcome and coloring tips).

Each page is a plain US Letter picture drawn with Pillow, in the same black-on-white style as the coloring pages.
The text is fixed (no AI call) and written for the audience of the book.
"""

from __future__ import annotations

from datetime import datetime

from PIL import Image, ImageDraw

from config import COLORING_EXTRA_PAGES, COLORING_PAGE_SIZE
from utils.image_utils import load_pil_font, wrap_text

_INK = (20, 20, 20)
_PAPER = (255, 255, 255)
_MARGIN = 90
_TEXT_WIDTH = COLORING_PAGE_SIZE[0] - 2 * (_MARGIN + 60)

_TIPS = [
    "Start with light pressure, then go darker where you want richer color.",
    "Color the large areas first and the small details last.",
    "Try colors that touch each other: warm next to cool makes a picture pop.",
    "Use a spare sheet of paper behind the page so markers do not bleed through.",
    "There are no wrong colors. Purple dinosaurs and blue suns are welcome!",
    "Take breaks, and finish a page only when you are happy with it.",
]


def _frame(draw: ImageDraw.ImageDraw) -> None:
    width, height = COLORING_PAGE_SIZE
    draw.rounded_rectangle((_MARGIN, _MARGIN, width - _MARGIN, height - _MARGIN), radius=40, outline=_INK, width=8)
    draw.rounded_rectangle((_MARGIN + 24, _MARGIN + 24, width - _MARGIN - 24, height - _MARGIN - 24), radius=28, outline=_INK, width=3)


def _centered(draw: ImageDraw.ImageDraw, text: str, y: int, size: int, bold: bool = False, gap: int = 14) -> int:
    """Draw wrapped, centered text from ``y`` and return the y below it."""
    font = load_pil_font(size, bold=bold)
    for line in wrap_text(draw, text, font, _TEXT_WIDTH):
        width = draw.textlength(line, font=font)
        draw.text(((COLORING_PAGE_SIZE[0] - width) / 2, y), line, font=font, fill=_INK)
        y += size + gap
    return y


def _page(title: str, author: str, key: str) -> Image.Image:
    image = Image.new("RGB", COLORING_PAGE_SIZE, _PAPER)
    draw = ImageDraw.Draw(image)
    _frame(draw)
    width, height = COLORING_PAGE_SIZE
    label = COLORING_EXTRA_PAGES[key]

    if key == "title_page":
        y = _centered(draw, title, 430, 110, bold=True, gap=24)
        draw.line((width // 2 - 220, y + 30, width // 2 + 220, y + 30), fill=_INK, width=6)
        _centered(draw, "A Coloring Book", y + 90, 56)
        if author:
            _centered(draw, f"by {author}", height - 420, 56)
    elif key == "copyright_page":
        year = datetime.now().year
        lines = [f"Copyright \u00a9 {year} {author}".strip(), "All rights reserved."]
        lines.append("No part of this book may be reproduced or sold without written permission from the author, except for personal coloring.")
        y = height // 2 - 220
        for index, text in enumerate(lines):
            y = _centered(draw, text, y, 52 if index < 2 else 40, bold=index == 0, gap=18) + 24
        _centered(draw, title, height - 360, 40)
    elif key == "belongs_page":
        y = _centered(draw, "This Book Belongs To", 430, 96, bold=True, gap=22)
        for row in range(2):
            line_y = y + 220 + row * 170
            draw.line((_MARGIN + 160, line_y, width - _MARGIN - 160, line_y), fill=_INK, width=5)
        _centered(draw, "Name", y + 235, 40)
        _centered(draw, "Date", y + 405, 40)
    elif key == "welcome_page":
        y = _centered(draw, "Welcome!", 330, 110, bold=True, gap=24) + 40
        text = (
            f"Thank you for choosing {title}. Inside are pictures made just for you to color. "
            "Grab your favorite pencils, crayons or markers, find a comfortable spot and let your imagination lead the way. "
            "Color as slowly or as boldly as you like, and have fun!"
        )
        _centered(draw, text, y, 54, gap=26)
        if author:
            _centered(draw, f"- {author}", height - 420, 52)
    else:  # tips_page
        y = _centered(draw, label, 290, 100, bold=True, gap=22) + 50
        font = load_pil_font(46)
        for number, tip in enumerate(_TIPS, start=1):
            lines = wrap_text(draw, tip, font, _TEXT_WIDTH - 90)
            draw.text((_MARGIN + 90, y), f"{number}.", font=load_pil_font(46, bold=True), fill=_INK)
            for line in lines:
                draw.text((_MARGIN + 170, y), line, font=font, fill=_INK)
                y += 46 + 14
            y += 40
    return image


def render_front_pages(keys: list[str], title: str, author: str) -> list[tuple[str, Image.Image]]:
    """(key, picture) for every selected extra page, in the fixed order of ``COLORING_EXTRA_PAGES``."""
    return [(key, _page(title, author, key)) for key in COLORING_EXTRA_PAGES if key in keys]
