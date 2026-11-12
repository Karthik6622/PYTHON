"""Coloring-book prompts: the plan (Nemotron) and the picture prompts (image model).

Nemotron only writes text, so it plans the book: title, cover scene and one scene per page. The pictures themselves are
drawn by the configured image model; the prompts for it are built here from the plan, so every page costs no extra text call.
"""

from __future__ import annotations

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
6. Detail level for this audience: {detail}
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

_LINE_ART_STYLE = (
    "black and white coloring book page, clean continuous black outlines only on a plain pure white background, "
    "closed shapes that are easy to color in, no shading, no gray tones, no filled black areas, no color, "
    "no text, no letters, no numbers, no watermark, no signature"
)
_COVER_STYLE = (
    "professional children's book cover illustration, vibrant colors, polished digital painting, centered subject, "
    "balanced composition with empty space at the top and the bottom, soft rich background, "
    "no text, no letters, no words, no watermark"
)


def detail_for(audience: str) -> str:
    return DETAIL_BY_AUDIENCE.get(audience, DETAIL_BY_AUDIENCE["Children"])


def page_prompt(scene: str, audience: str) -> str:
    """The prompt for one coloring page (kept well under 1000 characters, the AI Horde limit)."""
    detail = {"Children": "thick bold lines, very simple", "Teenagers": "medium lines, moderate detail", "Adults": "fine lines, intricate detailed patterns"}
    style = detail.get(audience, detail["Children"])
    return f"{scene.strip().rstrip('.')}. {_LINE_ART_STYLE}, {style}."[:950]


def cover_art_prompt(concept: str, title: str) -> str:
    """The prompt for the colored cover artwork. The title is added later by the app, never by the image model."""
    scene = concept.strip().rstrip(".") or title
    return f"{scene}. {_COVER_STYLE}."[:950]
