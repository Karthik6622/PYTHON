"""Pillow helpers: font discovery, placeholder art, image validation and normalisation."""

from __future__ import annotations

import colorsys
import hashlib
import os
from collections.abc import Iterator
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageStat

from config import FONTS_DIR

ORIENTATIONS = ("portrait", "landscape", "square")
ORIENTATION_SIZES: dict[str, tuple[int, int]] = {
    "portrait": (768, 1152),
    "landscape": (1152, 768),
    "square": (1024, 1024),
}
COVER_SIZE = (1024, 1536)  # 2:3, matches the 6x9 inch PDF page

# --------------------------------------------------------------------------------------
# Fonts
# --------------------------------------------------------------------------------------
_WIN = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
_DEJAVU = Path("/usr/share/fonts/truetype/dejavu")
_LIBERATION = Path("/usr/share/fonts/truetype/liberation")
_NOTO = Path("/usr/share/fonts/truetype/noto")
_MAC = Path("/System/Library/Fonts/Supplemental")

_Family = dict[str, Path]


def _family(directory: Path, regular: str, bold: str = "", italic: str = "", bold_italic: str = "") -> _Family:
    family: _Family = {"regular": directory / regular}
    if bold:
        family["bold"] = directory / bold
    if italic:
        family["italic"] = directory / italic
    if bold_italic:
        family["bold_italic"] = directory / bold_italic
    return family


SCRIPT_BY_LANGUAGE = {"Tamil": "tamil", "Hindi": "devanagari", "Japanese": "japanese"}

FONT_FAMILIES: dict[str, list[_Family]] = {
    "latin": [
        _family(FONTS_DIR, "NotoSerif-Regular.ttf", "NotoSerif-Bold.ttf", "NotoSerif-Italic.ttf", "NotoSerif-BoldItalic.ttf"),
        _family(_WIN, "georgia.ttf", "georgiab.ttf", "georgiai.ttf", "georgiaz.ttf"),
        _family(_WIN, "times.ttf", "timesbd.ttf", "timesi.ttf", "timesbi.ttf"),
        _family(_MAC, "Georgia.ttf", "Georgia Bold.ttf", "Georgia Italic.ttf", "Georgia Bold Italic.ttf"),
        _family(_DEJAVU, "DejaVuSerif.ttf", "DejaVuSerif-Bold.ttf", "DejaVuSerif-Italic.ttf", "DejaVuSerif-BoldItalic.ttf"),
        _family(_LIBERATION, "LiberationSerif-Regular.ttf", "LiberationSerif-Bold.ttf", "LiberationSerif-Italic.ttf", "LiberationSerif-BoldItalic.ttf"),
    ],
    "tamil": [
        _family(FONTS_DIR, "NotoSansTamil-Regular.ttf", "NotoSansTamil-Bold.ttf"),
        _family(_WIN, "Nirmala.ttf", "NirmalaB.ttf"),
        _family(_NOTO, "NotoSansTamil-Regular.ttf", "NotoSansTamil-Bold.ttf"),
        _family(Path("/usr/share/fonts/truetype/lohit-tamil"), "Lohit-Tamil.ttf"),
    ],
    "devanagari": [
        _family(FONTS_DIR, "NotoSansDevanagari-Regular.ttf", "NotoSansDevanagari-Bold.ttf"),
        _family(_WIN, "Nirmala.ttf", "NirmalaB.ttf"),
        _family(_WIN, "mangal.ttf", "mangalb.ttf"),
        _family(_NOTO, "NotoSansDevanagari-Regular.ttf", "NotoSansDevanagari-Bold.ttf"),
    ],
    "japanese": [
        _family(FONTS_DIR, "NotoSansJP-Regular.ttf", "NotoSansJP-Bold.ttf"),
        _family(_WIN, "msgothic.ttc"),
        _family(_WIN, "meiryo.ttc", "meiryob.ttc"),
        _family(_WIN, "YuGothR.ttc", "YuGothB.ttc"),
        _family(Path("/usr/share/fonts/opentype/noto"), "NotoSansCJK-Regular.ttc", "NotoSansCJK-Bold.ttc"),
        _family(_NOTO, "NotoSansCJK-Regular.ttc", "NotoSansCJK-Bold.ttc"),
    ],
}


def script_for(language: str) -> str:
    """Script group used to pick fonts for a language."""
    return SCRIPT_BY_LANGUAGE.get(language, "latin")


def iter_font_families(language: str) -> Iterator[_Family]:
    """Yield installed font families (regular file exists) for the language, best first."""
    for family in FONT_FAMILIES[script_for(language)]:
        if family["regular"].exists():
            yield family


def load_pil_font(size: int, language: str = "English", bold: bool = False) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    """Load a Unicode-capable TrueType font for Pillow, falling back to Pillow's default font."""
    for family in iter_font_families(language):
        path = family.get("bold") if bold else family["regular"]
        if not path or not path.exists():
            path = family["regular"]
        try:
            return ImageFont.truetype(str(path), size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # very old Pillow
        return ImageFont.load_default()


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    """Wrap text to a pixel width. Languages without spaces are wrapped per character."""
    tokens = text.split(" ") if " " in text.strip() else list(text.strip())
    joiner = " " if " " in text.strip() else ""
    lines: list[str] = []
    current = ""
    for token in tokens:
        candidate = f"{current}{joiner}{token}" if current else token
        if draw.textlength(candidate, font=font) <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = token
    if current:
        lines.append(current)
    return lines


# --------------------------------------------------------------------------------------
# Placeholder art
# --------------------------------------------------------------------------------------
def _hsv(h: float, s: float, v: float) -> tuple[int, int, int]:
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
    return int(r * 255), int(g * 255), int(b * 255)


def make_placeholder_image(size: tuple[int, int], seed: str = "placeholder") -> Image.Image:
    """Create abstract gradient artwork. The same seed always gives the same picture."""
    digest = hashlib.sha256(seed.encode("utf-8", "ignore")).digest()
    hue = digest[0] / 255
    start = _hsv(hue, 0.55, 0.45)
    end = _hsv(hue + 0.12 + digest[1] / 255 * 0.25, 0.65, 0.95)
    width, height = size
    base = Image.new("RGB", size)
    painter = ImageDraw.Draw(base)
    for y in range(height):
        t = y / max(height - 1, 1)
        painter.line([(0, y), (width, y)], fill=tuple(int(start[i] + (end[i] - start[i]) * t) for i in range(3)))
    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    shapes = ImageDraw.Draw(overlay)
    for i in range(7):
        radius = int(min(width, height) * (0.15 + digest[2 + i] / 255 * 0.35))
        cx = int(digest[10 + i] / 255 * width)
        cy = int(digest[18 + i] / 255 * height)
        colour = _hsv(hue + digest[26 + i % 5] / 255 * 0.3, 0.4, 1.0) + (70,)
        shapes.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=colour)
    overlay = overlay.filter(ImageFilter.GaussianBlur(radius=max(width, height) // 30))
    return Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")


# --------------------------------------------------------------------------------------
# Validation and normalisation
# --------------------------------------------------------------------------------------
def validate_image(path: str | Path) -> tuple[bool, str]:
    """Check that a file exists, opens in Pillow, is not tiny and is not a single flat colour."""
    file = Path(path)
    if not file.exists():
        return False, "file does not exist"
    if file.stat().st_size == 0:
        return False, "file is empty"
    try:
        with Image.open(file) as probe:
            probe.verify()
        with Image.open(file) as image:
            image.load()
            width, height = image.size
            if width < 64 or height < 64:
                return False, "image is too small"
            extrema = image.convert("RGB").getextrema()
            if all(low == high for low, high in extrema):
                return False, "image is blank"
    except Exception as exc:  # noqa: BLE001
        return False, f"image is unreadable ({type(exc).__name__})"
    return True, ""


def sharpness_score(path: str | Path) -> float:
    """Edge-contrast score (variance of a Laplacian filter on a 512 px greyscale copy). Soft or blurry pictures score low."""
    with Image.open(path) as image:
        grey = image.convert("L")
    grey.thumbnail((512, 512), Image.LANCZOS)
    edges = grey.filter(ImageFilter.Kernel((3, 3), [0, -1, 0, -1, 4, -1, 0, -1, 0], scale=1, offset=128))
    return float(ImageStat.Stat(edges).var[0])


def normalize_png(path: str | Path, max_size: tuple[int, int]) -> Path:
    """Convert to RGB, shrink to fit ``max_size`` without distortion and save as PNG in place."""
    file = Path(path)
    with Image.open(file) as image:
        image.load()
        if image.mode in ("RGBA", "LA") or "transparency" in image.info:
            rgba = image.convert("RGBA")
            flattened = Image.new("RGB", rgba.size, (255, 255, 255))
            flattened.paste(rgba, mask=rgba.split()[3])
            rgb = flattened
        else:
            rgb = image.convert("RGB")
    rgb.thumbnail(max_size, Image.LANCZOS)
    temp = file.with_name(file.stem + ".tmp.png")
    rgb.save(temp, "PNG")
    os.replace(temp, file)
    return file


def image_size(path: str | Path) -> tuple[int, int]:
    """Pixel size of an image."""
    with Image.open(path) as image:
        return image.size
