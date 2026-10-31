"""Test doubles for the AI model. No network access is ever attempted."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any


class FakeClient:
    """Stands in for ``ModelClient``. ``handlers`` maps a role name found in the system prompt ("Failure Analysis Agent")
    to a dict / list (returned as JSON) or a callable ``(system, payload) -> dict | str``."""

    model_name = "fake-model"

    def __init__(self, handlers: dict[str, Any] | None = None) -> None:
        self.handlers = handlers or {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def complete(self, messages: list[dict[str, Any]], **_kwargs: Any) -> tuple[str, dict[str, int]]:
        system = messages[0]["content"]
        content = messages[1]["content"]
        text = content if isinstance(content, str) else next(p["text"] for p in content if p.get("type") == "text")
        try:
            payload = json.loads(text)
        except ValueError:
            payload = {}
        for role, handler in self.handlers.items():
            if role in system:
                self.calls.append((role, payload))
                result = handler(system, payload) if isinstance(handler, Callable) else handler
                return (result if isinstance(result, str) else json.dumps(result)), {"prompt_tokens": 1, "completion_tokens": 1}
        raise AssertionError(f"No fake handler for this prompt: {system[:120]!r}")

    def count(self, role: str) -> int:
        return sum(1 for r, _ in self.calls if r == role)
