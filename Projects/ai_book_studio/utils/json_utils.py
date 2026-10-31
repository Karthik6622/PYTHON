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
    # strict=False accepts raw line breaks inside strings, which models often produce in long non-English text.
    try:
        return json.loads(candidate, strict=False)
    except ValueError:
        return json.loads(_TRAILING_COMMA.sub(r"\1", candidate), strict=False)


def _close_open_json(text: str) -> str:
    """Close the string, objects and arrays that a cut-off reply left open."""
    stack: list[str] = []
    in_string = False
    escaped = False
    for char in text:
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
        elif char in "{[":
            stack.append("}" if char == "{" else "]")
        elif char in "}]" and stack:
            stack.pop()
    if escaped:
        text = text[:-1]
    closing = ('"' if in_string else "") + "".join(reversed(stack))
    return text + closing


def repair_truncated_json(text: str) -> Any:
    """Recover the complete part of a JSON reply that was cut off (for example by the token limit).

    Drops the unfinished trailing item step by step until what is left parses. Raises ``ValueError`` when nothing can be saved.
    """
    start = re.search(r"[{\[]", text)
    if not start:
        raise ValueError("no JSON start")
    body = text[start.start() :].rstrip()
    for _ in range(40):
        try:
            return _try_load(_close_open_json(body))
        except ValueError:
            pass
        cut = max(body.rfind(","), body.rfind("{"), body.rfind("["))
        if cut <= 0:
            break
        body = body[:cut].rstrip().rstrip(",")
    raise ValueError("cannot repair JSON")


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
            # The outermost block was never closed (cut-off reply). Do not fall back to a small block nested inside it.
            break
        try:
            return _try_load(block)
        except ValueError:
            continue
    try:
        return repair_truncated_json(cleaned)
    except ValueError:
        pass
    raise InvalidModelResponseError()


def extract_json_object(text: str) -> dict[str, Any]:
    """Like ``extract_json`` but the result must be a JSON object."""
    data = extract_json(text)
    if not isinstance(data, dict):
        raise InvalidModelResponseError("The model returned JSON, but not a JSON object.")
    return data
