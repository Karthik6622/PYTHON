"""Robust extraction of JSON from model output."""

from __future__ import annotations

import json
import re
from typing import Any

from utils.retry_utils import InvalidModelResponseError
from utils.text_utils import strip_reasoning

_FENCE = re.compile(r"^```[a-zA-Z0-9]*\s*\n?|\n?```\s*$")
_TRAILING_COMMA = re.compile(r",\s*([}\]])")


def _balanced_slice(text: str, start: int) -> str | None:
    """Return the balanced {...} or [...] block that begins at ``start``."""
    opening = text[start]
    closing = "}" if opening == "{" else "]"
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _try_load(candidate: str) -> Any:
    try:
        return json.loads(candidate)
    except ValueError:
        return json.loads(_TRAILING_COMMA.sub(r"\1", candidate))


def extract_json(text: str) -> Any:
    """Parse the first JSON object or array found in ``text``.

    Handles Markdown code fences, reasoning blocks, commentary around the JSON and trailing commas.
    Raises ``InvalidModelResponseError`` when nothing parseable is found.
    """
    cleaned = _FENCE.sub("", strip_reasoning(text or "").strip()).strip()
    if not cleaned:
        raise InvalidModelResponseError("The model returned an empty response instead of JSON.")
    try:
        return _try_load(cleaned)
    except ValueError:
        pass
    for match in re.finditer(r"[{\[]", cleaned):
        block = _balanced_slice(cleaned, match.start())
        if not block:
            continue
        try:
            return _try_load(block)
        except ValueError:
            continue
    raise InvalidModelResponseError()


def extract_json_object(text: str) -> dict[str, Any]:
    """Like ``extract_json`` but the result must be a JSON object."""
    data = extract_json(text)
    if not isinstance(data, dict):
        raise InvalidModelResponseError("The model returned JSON, but not a JSON object.")
    return data
