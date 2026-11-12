"""Coloring-book prompts: the plan (Nemotron) and the picture prompts (image model).

Nemotron only writes text, so it plans the book: title, cover scene and one scene per page. The pictures themselves are
drawn by the configured image model; the prompts for it are built here from the plan, so every page costs no extra text call.
"""

from __future__ import annotations

from config import COMPLEXITY_EASY, COMPLEXITY_HARD, COMPLEXITY_MEDIUM

COLORING_PLAN_PROMPT = """You are a professional coloring-book designer and art director.

Plan a COLORING BOOK. It contains only black-and-white drawings to color in: no story, no chapters and no text on any page.

THEME / REQUEST FROM THE USER:
{book_idea}

PREFERRED TITLE:
{preferred_title}

TARGET AUDIENCE:
{audience}

NUMBER OF COLORING PAGES:
{page_count}

Instructions:

1. Write a short, catchy book title in correct English (use the preferred title when one is given) and an optional short subtitle.
2. Write a one-sentence description of the book.
3. Describe the cover as a single rich, colorful scene (cover_concept) that shows the theme at its best: a clear focal subject, a lively background, no text.
4. Create exactly {page_count} different page scenes. Every scene is one picture that can be drawn with clean outlines: a clear main subject, a simple background and a short description of what is drawn.
5. Vary the subjects, poses, viewpoints and compositions so that no two pages look alike. Stay on the theme.
6. Complexity chosen by the user (follow it for every scene): {detail}
   Every scene must be easy to color: clearly separated shapes with white space inside, never dense hatching, solid black areas or tiny crowded details.
7. Scenes must be wholesome, safe and suitable for the audience. Never describe text, letters, numbers, logos, brands or real people.
8. If the request is unsafe or asks to copy a specific copyrighted character or book, return {"refused": true, "reason": "..."} instead.

Return ONLY valid JSON in exactly this shape (no markdown, no commentary):

{"title": "...", "subtitle": "...", "description": "...", "cover_concept": "...", "pages": [{"title": "Short page name", "scene": "One sentence describing what is drawn"}]}
"""

MORE_SCENES_PROMPT = """You are planning the pages of a coloring book titled "{title}" about: {book_idea}.

These page scenes already exist (do not repeat them):
{existing}

Write {count} MORE different page scenes for the same book. Each scene is one picture with a clear main subject and a simple background, described in one sentence, with no text or letters in the picture. Detail level: {detail}

Return ONLY valid JSON: {"pages": [{"title": "Short page name", "scene": "One sentence describing what is drawn"}]}
"""

# What the picture should look like, by audience: bolder and simpler for small children, finer for adults.
DETAIL_BY_AUDIENCE: dict[str, str] = {
    "Children": "very simple: one big friendly subject, bold thick outlines, large open areas that are easy to color, almost no tiny details.",
    "Teenagers": "medium detail: a clear subject with some patterns and background elements, medium-thick outlines.",
    "Adults": "intricate and relaxing: fine decorative patterns, many small areas and rich detail, thin to medium outlines.",
}

# What the picture should look like, by complexity chosen by the user (the audience only sets the tone of the subjects).
DETAIL_BY_COMPLEXITY: dict[str, str] = {
    COMPLEXITY_EASY: "EASY: exactly one big, friendly main subject with at most two or three simple extra shapes, no background clutter, "
    "big open areas that are easy to color.",
    COMPLEXITY_MEDIUM: "MEDIUM: a clear main subject with a few supporting elements and a simple background, a moderate number of "
    "medium-sized areas to color.",
    COMPLEXITY_HARD: "HARD: a rich, intricate scene with several subjects, decorative patterns and many small areas to color, "
    "while every area stays clearly separated.",
}

_STYLE_BY_COMPLEXITY: dict[str, str] = {
    COMPLEXITY_EASY: "very simple, one big subject, few large shapes, thick bold outlines, lots of white space, empty plain background",
    COMPLEXITY_MEDIUM: "moderate detail, clear subject with a simple background, medium outlines, shapes big enough to color with crayons",
    COMPLEXITY_HARD: "very intricate and detailed, zentangle style patterns, many small shapes, fine clean outlines, every shape closed",
}

_LINE_ART_STYLE = (
    "black and white coloring book page, clean continuous black outlines only on a plain pure white background, "
    "every shape is a closed outline with empty white space inside to color, no shading, no hatching, no gray tones, "
    "no solid black filled areas, no color, no text, no letters, no numbers, no watermark, no signature"
)
_COVER_STYLE = (
    "professional children's book cover illustration, vibrant colors, polished digital painting, centered subject, "
    "balanced composition with empty space at the top and the bottom, soft rich background, "
    "no text, no letters, no words, no watermark"
)


def detail_for(audience: str, complexity: str | None = None) -> str:
    """Detail level for the page scenes: the chosen complexity, or (for older callers) a level suited to the audience."""
    if complexity in DETAIL_BY_COMPLEXITY:
        return DETAIL_BY_COMPLEXITY[complexity]
    return DETAIL_BY_AUDIENCE.get(audience, DETAIL_BY_AUDIENCE["Children"])


def page_prompt(scene: str, audience: str, complexity: str | None = None) -> str:
    """The prompt for one coloring page (kept well under 1000 characters, the AI Horde limit)."""
    if complexity in _STYLE_BY_COMPLEXITY:
        style = _STYLE_BY_COMPLEXITY[complexity]
    else:
        style = {"Children": "thick bold lines, very simple", "Teenagers": "medium lines, moderate detail", "Adults": "fine lines, intricate detailed patterns"}.get(audience, "thick bold lines, very simple")
    return f"{scene.strip().rstrip('.')}. {style}. {_LINE_ART_STYLE}."[:950]


def cover_art_prompt(concept: str, title: str) -> str:
    """The prompt for the colored cover artwork. The title is added later by the app, never by the image model."""
    scene = concept.strip().rstrip(".") or title
    return f"{scene}. {_COVER_STYLE}."[:950]
