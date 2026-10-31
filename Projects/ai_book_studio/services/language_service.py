"""Keeps generated text in the book's language: rewrites paragraphs that contain English or stray scripts, then cleans symbols."""

from __future__ import annotations

import logging

from prompts.language_prompts import LANGUAGE_FIX_PROMPT
from services.nvidia_client import LLMClient
from utils.language_utils import (
    NATIVE_SCRIPT_LANGUAGES,
    drop_latin_glosses,
    has_leftover_english,
    is_code_block,
    latin_words,
    sanitize_text,
    split_paragraphs,
    uses_native_script,
)
from utils.retry_utils import AIBookError, NvidiaAuthError, NvidiaKeyMissingError
from utils.text_utils import chapter_max_tokens, render_template

LOGGER = logging.getLogger("ai_book_studio.language")

_GROUP_CHARS = 1800  # characters of faulty paragraphs rewritten per request
_MAX_REQUESTS = 40  # per text, so a badly broken chapter cannot loop for long
_ROUNDS = 2


def _groups(paragraphs: list[str], language: str) -> list[list[int]]:
    """Indexes of faulty paragraphs, grouped so that neighbours are fixed together within a size limit."""
    groups: list[list[int]] = []
    current: list[int] = []
    size = 0
    for index, paragraph in enumerate(paragraphs):
        faulty = not is_code_block(paragraph) and has_leftover_english(paragraph, language)
        if not faulty:
            continue
        if current and (index != current[-1] + 1 or size + len(paragraph) > _GROUP_CHARS):
            groups.append(current)
            current, size = [], 0
        current.append(index)
        size += len(paragraph)
    if current:
        groups.append(current)
    return groups


def _rewrite(llm: LLMClient, passage: str, language: str) -> str | None:
    """Ask the model to rewrite one passage; None when the answer cannot be trusted."""
    prompt = render_template(
        LANGUAGE_FIX_PROMPT, language=language, script=NATIVE_SCRIPT_LANGUAGES.get(language, language), passage=passage
    )
    try:
        result = llm.generate(prompt, "language_fix", max_tokens=chapter_max_tokens(max(len(passage.split()), 60), language))
    except (NvidiaAuthError, NvidiaKeyMissingError):
        raise
    except AIBookError as exc:
        LOGGER.warning("Language repair request failed: %s", type(exc).__name__)
        return None
    fixed = sanitize_text(result.text, language)
    # Accept the rewrite only when it is complete and really has less English than the original.
    if len(fixed) < 0.5 * len(passage) or len(fixed) > 2.5 * len(passage) + 200:
        return None
    if len(latin_words(fixed)) >= len(latin_words(passage)):
        return None
    return fixed


def ensure_language(llm: LLMClient, text: str, language: str) -> str:
    """Return ``text`` cleaned for ``language``.

    Always removes junk symbols and characters of unrelated scripts. For Tamil, Hindi and Japanese, paragraphs that still
    contain English words are rewritten by the model (at most twice), and leftover bracketed English notes are dropped.
    """
    language = language or "English"
    cleaned = sanitize_text(text, language)
    if not uses_native_script(language):
        return cleaned
    requests = 0
    for _ in range(_ROUNDS):
        paragraphs = split_paragraphs(cleaned)
        groups = _groups(paragraphs, language)
        if not groups or requests >= _MAX_REQUESTS:
            break
        changed = False
        for group in reversed(groups):  # last first, so the indexes of earlier groups stay valid
            if requests >= _MAX_REQUESTS:
                break
            requests += 1
            fixed = _rewrite(llm, "\n\n".join(paragraphs[i] for i in group), language)
            if fixed is not None:
                paragraphs[group[0] : group[-1] + 1] = split_paragraphs(fixed)
                changed = True
        cleaned = "\n\n".join(paragraphs)
        if not changed:
            break
    return drop_latin_glosses(cleaned, language)
