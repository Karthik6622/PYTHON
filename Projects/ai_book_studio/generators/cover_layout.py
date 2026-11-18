"""Dynamic cover layouts: where the title, subtitle and author go, which colours and frame are used.

The first cover of a book follows one fixed structure (the classic title band / artwork / author band). When the user presses
*Generate Cover* with their own prompt, a layout is designed from that prompt instead: the model proposes the arrangement (text
zone, alignment, palette, frame ...) and a deterministic designer fills in whatever it did not answer. The same prompt pressed
again rotates to a different arrangement, so the cover never looks like the previous one just with new art.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import asdict, dataclass, field, fields
from typing import Any

from PIL import Image, ImageFilter, ImageStat

LOGGER = logging.getLogger("ai_book_studio.cover")

STRUCTURES = ("bands", "overlay", "poster")
ZONES = ("top", "center", "bottom", "auto")
ALIGNS = ("center", "left", "right")
CASES = ("keep", "upper", "title")
PALETTES = ("auto", "dark", "light", "gold", "ember", "ice", "neon", "forest")
FRAMES = ("double", "single", "corners", "none")
SCRIMS = ("gradient", "solid", "none")

# text colour, sub-text colour, accent, True when the palette is a light one (dark text on a light scrim)
PALETTE_COLORS: dict[str, tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int], bool]] = {
    "dark": ((255, 255, 255), (232, 232, 242), (214, 178, 94), False),
    "light": ((34, 30, 44), (82, 76, 98), (150, 108, 40), True),
    "gold": ((255, 228, 160), (240, 222, 190), (236, 190, 90), False),
    "ember": ((255, 240, 224), (255, 214, 176), (255, 138, 43), False),
    "ice": ((236, 249, 255), (200, 228, 245), (130, 206, 255), False),
    "neon": ((255, 255, 255), (214, 244, 255), (255, 64, 160), False),
    "forest": ((242, 255, 240), (206, 232, 200), (160, 212, 140), False),
}
# coloring-book palettes: title ink, card fill, card accent line
COLORING_PALETTES: dict[str, tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]] = {
    "dark": ((52, 41, 92), (255, 250, 238), (255, 167, 38)),
    "light": ((52, 41, 92), (255, 250, 238), (255, 167, 38)),
    "gold": ((92, 62, 16), (255, 247, 222), (236, 190, 90)),
    "ember": ((130, 38, 28), (255, 244, 232), (255, 112, 67)),
    "ice": ((24, 74, 112), (238, 250, 255), (79, 195, 247)),
    "neon": ((84, 22, 110), (255, 240, 252), (255, 64, 160)),
    "forest": ((28, 82, 52), (244, 255, 240), (129, 199, 132)),
}


@dataclass
class CoverLayout:
    structure: str = "bands"  # bands = the classic title band / artwork / author band; overlay and poster put text on the artwork
    title_zone: str = "top"
    author_zone: str = "bottom"
    align: str = "center"
    title_case: str = "keep"
    palette: str = "auto"
    frame: str = "double"
    scrim: str = "gradient"
    rule: bool = True
    title_scale: float = 1.0
    source: str = ""  # fingerprint of the prompt this layout was designed from
    variant: int = 0
    note: str = ""  # one line shown to the user

    @property
    def is_default(self) -> bool:
        return self == CoverLayout()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> CoverLayout:
        """Tolerant: unknown keys are ignored and every choice is clamped to the allowed values."""
        data = data or {}
        allowed = {f.name for f in fields(cls)}
        layout = cls(**{k: v for k, v in data.items() if k in allowed})

        def pick(value: Any, choices: tuple[str, ...], default: str) -> str:
            text = str(value or "").strip().lower()
            return text if text in choices else default

        layout.structure = pick(layout.structure, STRUCTURES, "bands")
        layout.title_zone = pick(layout.title_zone, ZONES, "top")
        layout.author_zone = pick(layout.author_zone, ("top", "bottom"), "bottom")
        layout.align = pick(layout.align, ALIGNS, "center")
        layout.title_case = pick(layout.title_case, CASES, "keep")
        layout.palette = pick(layout.palette, PALETTES, "auto")
        layout.frame = pick(layout.frame, FRAMES, "double")
        layout.scrim = pick(layout.scrim, SCRIMS, "gradient")
        layout.rule = bool(layout.rule)
        try:
            layout.title_scale = min(max(float(layout.title_scale), 0.75), 1.25)
        except (TypeError, ValueError):
            layout.title_scale = 1.0
        layout.variant = int(layout.variant) if str(layout.variant).lstrip("-").isdigit() else 0
        layout.source = str(layout.source or "")[:40]
        layout.note = " ".join(str(layout.note or "").split())[:140]
        return layout


def fingerprint(prompt: str) -> str:
    return hashlib.sha1(" ".join((prompt or "").lower().split()).encode("utf-8")).hexdigest()[:16]


# ------------------------------------------------------------------ the designer
_MOODS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("dark", re.compile(r"(?i)\b(dark|gritty|noir|horror|grim|shadow\w*|night|storm\w*|winter|snow|war|battle|dragon|throne|epic|brooding|moody|cinematic)\b")),
    ("light", re.compile(r"(?i)\b(pastel|soft|gentle|cozy|cosy|light|bright|sunny|cheerful|whimsical|children|kids?|baby|spring|watercolou?r)\b")),
    ("neon", re.compile(r"(?i)\b(neon|cyber\w*|sci[- ]?fi|futuristic|space|robot\w*|synthwave|hologram|tech\w*)\b")),
    ("nature", re.compile(r"(?i)\b(forest|jungle|garden|nature|mountain\w*|river|ocean|sea|meadow|botanical)\b")),
    ("romance", re.compile(r"(?i)\b(romance|romantic|love|wedding|rose\w*|sunset|dream\w*)\b")),
    ("minimal", re.compile(r"(?i)\b(minimal\w*|clean|modern|simple|flat|geometric|abstract|vector)\b")),
    ("classic", re.compile(r"(?i)\b(vintage|classic|antique|victorian|historical|ancient|parchment|retro|old[- ]school)\b")),
)
# arrangement candidates per mood: (structure, title zone, align, palette, frame, scrim, title case)
_RECIPES: dict[str, list[tuple[str, str, str, str, str, str, str]]] = {
    "dark": [
        ("overlay", "bottom", "center", "dark", "single", "gradient", "upper"),
        ("poster", "center", "center", "gold", "corners", "gradient", "upper"),
        ("overlay", "top", "left", "ice", "none", "gradient", "upper"),
        ("overlay", "bottom", "left", "ember", "single", "gradient", "keep"),
    ],
    "light": [
        ("overlay", "top", "center", "light", "single", "solid", "title"),
        ("poster", "center", "center", "light", "none", "gradient", "title"),
        ("overlay", "bottom", "center", "light", "corners", "gradient", "title"),
    ],
    "neon": [
        ("overlay", "top", "left", "neon", "none", "gradient", "upper"),
        ("poster", "center", "center", "neon", "corners", "gradient", "upper"),
        ("overlay", "bottom", "right", "ice", "single", "gradient", "upper"),
    ],
    "nature": [
        ("overlay", "bottom", "center", "forest", "single", "gradient", "title"),
        ("overlay", "top", "center", "forest", "double", "gradient", "title"),
        ("poster", "center", "center", "light", "none", "gradient", "title"),
    ],
    "romance": [
        ("poster", "center", "center", "ember", "double", "gradient", "title"),
        ("overlay", "bottom", "center", "gold", "single", "gradient", "title"),
        ("overlay", "top", "center", "light", "single", "solid", "title"),
    ],
    "minimal": [
        ("overlay", "bottom", "left", "light", "none", "none", "keep"),
        ("overlay", "top", "left", "dark", "none", "solid", "upper"),
        ("overlay", "top", "right", "dark", "none", "gradient", "keep"),
    ],
    "classic": [
        ("bands", "top", "center", "gold", "double", "solid", "title"),
        ("overlay", "top", "center", "gold", "double", "gradient", "title"),
        ("poster", "center", "center", "gold", "double", "gradient", "title"),
    ],
}
_DEFAULT_RECIPES = [
    ("overlay", "bottom", "center", "dark", "single", "gradient", "keep"),
    ("overlay", "top", "left", "dark", "none", "gradient", "upper"),
    ("poster", "center", "center", "gold", "corners", "gradient", "upper"),
    ("overlay", "top", "center", "ember", "double", "gradient", "title"),
]


def mood_of(prompt: str) -> str:
    scores = {name: len(pattern.findall(prompt or "")) for name, pattern in _MOODS}
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] else "default"


def layout_from_prompt(prompt: str, kind: str = "ebook", variant: int = 0) -> CoverLayout:
    """Deterministic designer: the mood of the prompt chooses a family of arrangements, its fingerprint (plus ``variant``) one of them."""
    mood = mood_of(prompt)
    recipes = _RECIPES.get(mood, _DEFAULT_RECIPES)
    index = (int(fingerprint(prompt)[:6], 16) + variant) % len(recipes)
    structure, zone, align, palette, frame, scrim, case = recipes[index]
    layout = CoverLayout(
        structure=structure, title_zone=zone, author_zone="top" if zone == "bottom" and structure == "poster" else "bottom", align=align,
        title_case=case, palette=palette, frame=frame, scrim=scrim, rule=frame != "none", title_scale=1.0,
        source=fingerprint(prompt), variant=variant,
        note=f"Designed from your prompt ({mood if mood != 'default' else 'general'} mood): title {zone}, {align}-aligned, {palette} palette.",
    )
    if kind == "coloring":  # the coloring cover always keeps a card; only its place, colours and frame change
        layout.structure = "overlay"
        layout.title_zone = {"top": "top", "bottom": "bottom", "center": "center"}.get(zone, "top")
        layout.palette = palette if palette in COLORING_PALETTES else "ember"
    return layout


_DESIGN_PROMPT = """You are a book-cover art director. Choose the TEXT LAYOUT for a {kind} cover. The artwork is made separately from the prompt below;
the title, subtitle and author are drawn on top by the app, so choose where they go so they never hide the main subject and fit the mood.

Artwork prompt: {prompt}
Title: {title}
Subtitle: {subtitle}
Author: {author}

Answer with ONE JSON object and nothing else, using only these values:
{{"structure": "overlay|poster|bands", "title_zone": "top|center|bottom|auto", "author_zone": "top|bottom", "align": "center|left|right",
 "title_case": "keep|upper|title", "palette": "dark|light|gold|ember|ice|neon|forest", "frame": "double|single|corners|none",
 "scrim": "gradient|solid|none", "rule": true, "title_scale": 1.0, "note": "one short sentence saying why"}}
Guidance: overlay = text over the picture at the top or bottom; poster = title in the middle; bands = classic top and bottom bands.
Put the title in the emptiest area of the described scene (a figure in the centre -> title top or bottom; a wide landscape -> top).
Use a light palette only for bright, soft or childlike art; neon/ice for sci-fi or cold scenes; ember/gold for warm, epic or romantic art.
Vary the arrangement: do not always choose the same answer. title_scale is 0.8 to 1.2."""


def design_layout(llm: Any, prompt: str, title: str, subtitle: str, author: str, kind: str = "ebook", previous: CoverLayout | None = None) -> CoverLayout:
    """Layout for a cover whose artwork comes from ``prompt``. Never raises: without the model the deterministic designer answers."""
    same = previous is not None and previous.source == fingerprint(prompt)
    variant = (previous.variant + 1) if same and previous is not None else 0
    fallback = layout_from_prompt(prompt, kind, variant)
    if llm is None:
        return fallback
    try:
        text = _DESIGN_PROMPT.format(kind="coloring-book" if kind == "coloring" else "book", prompt=" ".join(prompt.split())[:700], title=title, subtitle=subtitle or "-", author=author)
        data = llm.generate_json(text, "image_prompt", 500)
        if isinstance(data, str):
            data = json.loads(data)
        layout = CoverLayout.from_dict(data if isinstance(data, dict) else {})
    except Exception as exc:  # noqa: BLE001 - a cover must never fail because the layout designer did
        LOGGER.info("Layout designer unavailable (%s); using the deterministic designer", type(exc).__name__)
        return fallback
    if same and layout.to_dict() | {"source": "", "variant": 0, "note": ""} == (previous.to_dict() | {"source": "", "variant": 0, "note": ""}):
        return fallback  # pressing Generate again with the same prompt must give a different arrangement
    layout.source, layout.variant = fingerprint(prompt), variant
    layout.note = layout.note or fallback.note
    if kind == "coloring":
        layout.structure = "overlay"
        layout.title_zone = layout.title_zone if layout.title_zone in {"top", "center", "bottom"} else "top"
        layout.palette = layout.palette if layout.palette in COLORING_PALETTES else fallback.palette
    return layout


# ------------------------------------------------------------------ reading the artwork
@dataclass
class ArtZones:
    busy: dict[str, float] = field(default_factory=dict)  # edge-detail score per zone (lower = calmer)
    bright: dict[str, float] = field(default_factory=dict)  # mean brightness 0..255 per zone


def analyse_art(art: Image.Image) -> ArtZones:
    """How busy and how bright the top, middle and bottom thirds of the artwork are (used to place text on the calmest area)."""
    small = art.convert("L").resize((96, 144))
    edges = small.filter(ImageFilter.FIND_EDGES)
    zones = ArtZones()
    for name, (a, b) in {"top": (0, 48), "center": (48, 96), "bottom": (96, 144)}.items():
        zones.busy[name] = ImageStat.Stat(edges.crop((0, a, 96, b))).mean[0]
        zones.bright[name] = ImageStat.Stat(small.crop((0, a, 96, b))).mean[0]
    return zones


def resolve(layout: CoverLayout, art: Image.Image) -> CoverLayout:
    """Replace the 'auto' choices with concrete ones using the artwork."""
    zones = analyse_art(art)
    resolved = CoverLayout.from_dict(layout.to_dict())
    if resolved.title_zone == "auto":
        resolved.title_zone = "top" if zones.busy["top"] <= zones.busy["bottom"] else "bottom"
    if resolved.palette == "auto":
        resolved.palette = "light" if zones.bright[resolved.title_zone] > 175 else "dark"
    return resolved
