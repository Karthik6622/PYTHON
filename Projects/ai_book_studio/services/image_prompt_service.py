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
    return cleaned[:3500] + NO_TEXT_SUFFIX


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
    return _clean_prompt(llm.generate_text(prompt, "image_prompt"))


def chapter_prompt(
    llm: LLMClient, plan: BookPlan, bible: BookBible | None, chapter: ChapterPlan, orientation: str
) -> str:
    """Prompt for one chapter illustration."""
    prompt = render_template(
        CHAPTER_IMAGE_PROMPT,
        book_title=plan.title,
        book_type=plan.book_type,
        audience=plan.audience,
        visual_style=plan.visual_style,
        relevant_book_bible_information=bible_excerpt(bible),
        chapter_title=chapter.title,
        chapter_summary=chapter.summary,
        image_concept=chapter.image_concept or chapter.summary,
        orientation=orientation,
    )
    return _clean_prompt(llm.generate_text(prompt, "image_prompt"))
