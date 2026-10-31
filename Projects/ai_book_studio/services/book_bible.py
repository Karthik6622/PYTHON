"""Step 5: generate the story or content bible."""

from __future__ import annotations

from typing import Any

from config import JSON_TOKENS
from models.book_models import BookBible, BookPlan
from prompts.bible_prompts import BIBLE_PROMPT
from services.nvidia_client import LLMClient
from utils.language_utils import language_rules
from utils.retry_utils import ContentPolicyError, InvalidModelResponseError
from utils.text_utils import compact_json, render_template


def _validate_bible(data: dict[str, Any]) -> BookBible:
    if data.get("refused"):
        raise ContentPolicyError(str(data.get("reason") or "The model declined this request."))
    bible = BookBible.model_validate(data)
    if not bible.model_dump(exclude_defaults=True):
        raise InvalidModelResponseError("The model returned an empty continuity bible.")
    return bible


def generate_bible(llm: LLMClient, plan: BookPlan) -> BookBible:
    """Create the continuity bible supplied with every chapter request."""
    prompt = render_template(
        BIBLE_PROMPT, book_plan_json=compact_json(plan), language=plan.language, language_rules=language_rules(plan.language)
    )
    tokens = 6000 if plan.language == "English" else max(8000, 2 * JSON_TOKENS.get(plan.language, 3500))
    return llm.generate_json(prompt, "bible", max_tokens=tokens, validator=_validate_bible)


def bible_excerpt(bible: BookBible | None, limit: int = 3000) -> str:
    """The parts of the bible useful for illustrations: characters, locations and objects."""
    if bible is None:
        return "No additional continuity details."
    data = bible.model_dump(mode="json", exclude_defaults=True)
    focus = {key: data[key] for key in ("characters", "locations", "important_objects", "world_rules") if key in data}
    return compact_json(focus or data, limit)
