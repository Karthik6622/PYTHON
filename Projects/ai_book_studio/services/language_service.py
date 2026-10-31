"""Keeps generated text in the book's language: rewrites paragraphs that contain English or stray scripts, then cleans symbols."""

from __future__ import annotations

import logging
import re
from typing import Any

from prompts.language_prompts import LANGUAGE_FIX_PROMPT
from services.nvidia_client import LLMClient
from utils.language_utils import (
    NATIVE_SCRIPT_LANGUAGES,
    drop_latin_glosses,
    fault_count,
    has_language_faults,
    is_code_block,
    sanitize_text,
    split_paragraphs,
    strip_latin,
    uses_native_script,
)
from utils.retry_utils import AIBookError, NvidiaAuthError, NvidiaKeyMissingError
from utils.text_utils import chapter_max_tokens, render_template

LOGGER = logging.getLogger("ai_book_studio.language")

_GROUP_CHARS = 1800  # characters of faulty paragraphs rewritten per request
_MAX_REQUESTS = 60  # per text, so a badly broken chapter cannot loop for long
_ROUNDS = 2
_SENTENCE_END = re.compile(r"(?<=[.!?\u0964\u3002])\s+")


def _groups(paragraphs: list[str], language: str) -> list[list[int]]:
    """Indexes of faulty paragraphs, grouped so that neighbours are fixed together within a size limit."""
    groups: list[list[int]] = []
    current: list[int] = []
    size = 0
    for index, paragraph in enumerate(paragraphs):
        faulty = not is_code_block(paragraph) and has_language_faults(paragraph, language)
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
    raw = result.text.strip()
    # Accept the rewrite only when it is complete and really has fewer wrong-language words than the original.
    if len(raw) < 0.5 * len(passage) or len(raw) > 2.5 * len(passage) + 200:
        return None
    if fault_count(raw, language) >= fault_count(passage, language):
        return None
    return raw


def _repair_sentences(llm: LLMClient, paragraphs: list[str], language: str, budget: int) -> int:
    """Rewrite single faulty sentences (models handle a short passage better than a long one). Returns requests used."""
    used = 0
    for index, paragraph in enumerate(paragraphs):
        if is_code_block(paragraph) or not has_language_faults(paragraph, language):
            continue
        parts = re.split(r"((?<=[.!?\u0964\u3002])\s+)", paragraph)  # sentences at even positions, separators at odd ones
        changed = False
        for position in range(0, len(parts), 2):
            if not has_language_faults(parts[position], language):
                continue
            if used >= budget:
                break
            used += 1
            fixed = _rewrite(llm, parts[position], language)
            if fixed is not None:
                parts[position] = " ".join(fixed.split())
                changed = True
        if changed:
            paragraphs[index] = "".join(parts)
    return used


def ensure_language(llm: LLMClient, text: str, language: str) -> str:
    """Return ``text`` cleaned for ``language``.

    For Tamil, Hindi and Japanese the wrong-language parts (English or romanised words, letters of other scripts) are
    first rewritten by the model, paragraph by paragraph and then sentence by sentence. Anything the model could not
    fix is removed at the end, and junk symbols and invisible characters are always cleaned.
    """
    language = language or "English"
    if not uses_native_script(language):
        return sanitize_text(text, language)
    paragraphs = split_paragraphs(text)
    requests = 0
    for _ in range(_ROUNDS):
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
        if not changed:
            break
    if any(has_language_faults(p, language) for p in paragraphs if not is_code_block(p)):
        requests += _repair_sentences(llm, paragraphs, language, max(_MAX_REQUESTS - requests, 10))
    cleaned = drop_latin_glosses(sanitize_text("\n\n".join(paragraphs), language), language)
    final = [p if is_code_block(p) else strip_latin(p, language) for p in split_paragraphs(cleaned)]
    result = "\n\n".join(final)
    if result != cleaned:
        LOGGER.warning("Removed %d leftover wrong-language word(s) that the model could not rewrite.", fault_count(cleaned, language))
    return result


def clean_structure(llm: LLMClient, data: Any, language: str, skip: frozenset[str] = frozenset()) -> Any:
    """Apply ``ensure_language`` to every text inside nested dicts and lists (keys in ``skip`` are left unchanged)."""
    if isinstance(data, str):
        return ensure_language(llm, data, language) if data.strip() else data
    if isinstance(data, list):
        return [clean_structure(llm, item, language, skip) for item in data]
    if isinstance(data, dict):
        return {key: value if key in skip else clean_structure(llm, value, language, skip) for key, value in data.items()}
    return data
