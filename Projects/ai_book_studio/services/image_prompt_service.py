"""Steps 10-11: Nemotron writes image prompts. It never draws images."""

from __future__ import annotations

import re

from models.book_models import BookBible, BookPlan, ChapterPlan
from prompts.image_prompts import CHAPTER_IMAGE_PROMPT, COVER_IMAGE_PROMPT, NO_TEXT_SUFFIX
from services.book_bible import bible_excerpt
from services.nvidia_client import LLMClient
from utils.retry_utils import EmptyResponseError
from utils.text_utils import render_template, strip_reasoning

_LANDSCAPE = re.compile(
    r"(?i)\b(landscape|panoram\w*|vista|skyline|cityscape|horizon|ocean|sea|battle|journey|valley|wide shot|aerial|bridge)\b"
)
_PORTRAIT = re.compile(r"(?i)\b(portrait|close[- ]?up|hero|heroine|figure standing|character|tower|doorway|full[- ]body)\b")


def choose_orientation(chapter: ChapterPlan, book_type: str = "") -> str:
    """Pick portrait, landscape or square from the illustration concept and the book type."""
    concept = f"{chapter.image_concept} {chapter.title}"
    if _LANDSCAPE.search(concept):
        return "landscape"
    if _PORTRAIT.search(concept):
        return "portrait"
    if book_type == "Children's Book":
        return "landscape"
    return "square"


def _clean_prompt(text: str) -> str:
    cleaned = strip_reasoning(text).strip().strip("`").strip()
    cleaned = re.sub(r"^(image[- ]generation )?prompt\s*[:\-]\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = " ".join(cleaned.strip('"“”').split())
    if not cleaned:
        raise EmptyResponseError("The model returned an empty image prompt.")
    return cleaned


# AI Horde cuts prompts at 1000 characters, so the fixed part (style + characters) goes first and the scene is trimmed.
_PROMPT_BUDGET = 1000
_ANCHOR_LIMIT = 420
_PER_CHARACTER_LIMIT = 230


def _tidy(text: str) -> str:
    return " ".join(str(text).split()).strip(" .;,")


def _name_matches(name: str, text: str) -> bool:
    parts = [name] + [p for p in re.split(r"\s+", name) if len(p) >= 3]
    return any(re.search(rf"(?<!\w){re.escape(p)}(?!\w)", text, re.IGNORECASE) for p in parts if p)


def character_anchor(bible: BookBible | None, chapter: ChapterPlan | None = None) -> str:
    """Fixed, identical wording for the recurring characters of a scene.

    Characters named in the chapter title, summary or image concept are used; when none is named the lead character
    (the first in the bible) is used, so the same person is drawn in every illustration.
    """
    if bible is None or not bible.characters:
        return ""
    described = [c for c in bible.characters if c.name and (c.appearance or c.clothing)]
    if not described:
        return ""
    chosen = []
    if chapter is not None:
        haystack = f"{chapter.title} {chapter.summary} {chapter.image_concept}"
        chosen = [c for c in described if _name_matches(c.name, haystack)]
    chosen = (chosen or described[:1])[:3]
    entries = []
    for character in chosen:
        details = _tidy(character.appearance)
        if character.clothing:
            details += f", wearing {_tidy(character.clothing)}"
        entry = f"{_tidy(character.name)}: {details}"
        entries.append(entry[:_PER_CHARACTER_LIMIT].rstrip(" ,;"))
    return ". ".join(entries)[:_ANCHOR_LIMIT]


def _assemble(style: str, anchor: str, scene: str) -> str:
    """style + fixed character description + scene + no-text suffix, trimmed to the provider's prompt limit."""
    head = ""
    if style.strip():
        head += _tidy(style)[:120] + ". "
    if anchor:
        head += f"Same recurring character(s), identical look in every illustration: {anchor}. "
    room = max(250, _PROMPT_BUDGET - len(head) - len(NO_TEXT_SUFFIX))
    if len(scene) > room:
        scene = scene[:room].rsplit(" ", 1)[0].rstrip(" ,;")
    return head + scene + NO_TEXT_SUFFIX


def _character_rule(language: str, anchor: str) -> str:
    if not anchor:
        return "Keep every character's appearance consistent with the character details above."
    if (language or "English").strip().lower() == "english":
        return (
            "The fixed look of the recurring characters is added to the prompt automatically. Do NOT describe their face, hair, "
            "skin, age, build or clothing. Refer to them by name and describe only their pose, action, expression, the "
            "environment, objects, camera angle, lighting and mood. Keep the prompt under 600 characters."
        )
    return (
        "Describe each recurring character with exactly the appearance and clothing in the details above, translated into "
        "English with identical wording in every prompt. Keep the prompt under 800 characters."
    )


def cover_prompt(llm: LLMClient, plan: BookPlan, bible: BookBible | None) -> str:
    """Prompt for textless cover artwork (the title and author are added later with Pillow)."""
    prompt = render_template(
        COVER_IMAGE_PROMPT,
        book_title=plan.title,
        book_description=plan.description,
        book_type=plan.book_type,
        audience=plan.audience,
        main_theme=plan.main_theme,
        visual_style=plan.visual_style,
        relevant_book_bible_information=bible_excerpt(bible),
    )
    scene = _clean_prompt(llm.generate_text(prompt, "image_prompt"))
    anchor = character_anchor(bible) if (plan.language or "English").strip().lower() == "english" else ""
    return _assemble(plan.visual_style, anchor, scene)


def chapter_prompt(
    llm: LLMClient, plan: BookPlan, bible: BookBible | None, chapter: ChapterPlan, orientation: str
) -> str:
    """Prompt for one chapter illustration."""
    is_english = (plan.language or "English").strip().lower() == "english"
    anchor = character_anchor(bible, chapter)
    prompt = render_template(
        CHAPTER_IMAGE_PROMPT,
        book_title=plan.title,
        book_type=plan.book_type,
        audience=plan.audience,
        visual_style=plan.visual_style,
        relevant_book_bible_information=bible_excerpt(bible),
        character_sheet=anchor or "None",
        character_rule=_character_rule(plan.language, anchor),
        chapter_title=chapter.title,
        chapter_summary=chapter.summary,
        image_concept=chapter.image_concept or chapter.summary,
        orientation=orientation,
    )
    scene = _clean_prompt(llm.generate_text(prompt, "image_prompt"))
    return _assemble(plan.visual_style, anchor if is_english else "", scene)
