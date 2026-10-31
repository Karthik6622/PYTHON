"""Agent base class: system prompt, validated input, structured output, retries, logging and context budgeting."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from ats.ai.client import ModelClient, estimate_tokens, extract_json, image_part
from ats.ai.prompts import get_prompt
from ats.config import get_settings
from ats.errors import ModelError, ModelResponseError
from ats.logging_setup import get_logger
from ats.security import mask

T = TypeVar("T", bound=BaseModel)
LOGGER = get_logger("ai.agent")

EventCallback = Callable[[str, str], None]


def shrink(value: Any, max_chars: int) -> Any:
    """Reduce a JSON-like value until its serialised size fits ``max_chars`` (long lists and strings are trimmed)."""
    size = len(json.dumps(value, ensure_ascii=False, default=str))
    if size <= max_chars:
        return value
    ratio = max(max_chars / size, 0.05)
    return _shrink(value, ratio)


def _shrink(value: Any, ratio: float) -> Any:
    if isinstance(value, str):
        limit = max(int(len(value) * ratio), 80)
        return value if len(value) <= limit else value[:limit] + "…[trimmed]"
    if isinstance(value, list):
        keep = max(int(len(value) * ratio), 3)
        return [_shrink(item, ratio ** 0.5) for item in value[:keep]]
    if isinstance(value, dict):
        return {key: _shrink(item, ratio ** 0.5) for key, item in value.items()}
    return value


class Agent:
    """One logical agent. Subclasses define ``name`` and call ``invoke`` with a task prompt and an output model."""

    name = "agent"
    thinking: bool | None = None  # None = use the global MODEL_ENABLE_THINKING setting
    temperature: float | None = None

    def __init__(self, client: ModelClient | None = None, repository: Any = None) -> None:
        self.client = client or ModelClient()
        self.repository = repository

    def invoke(
        self,
        task: str,
        payload: dict[str, Any],
        output_model: type[T],
        *,
        input_model: type[BaseModel] | None = None,
        project_id: str = "",
        images: list[bytes] | None = None,
        on_event: EventCallback | None = None,
        thinking: bool | None = None,
    ) -> T:
        if input_model is not None:
            payload = input_model.model_validate(payload).model_dump(mode="json")
        settings = get_settings().model
        budget_chars = settings.context_budget_tokens * 4
        schema = json.dumps(output_model.model_json_schema(), separators=(",", ":"))
        system = get_prompt(task) + f"\nOutput JSON schema (for validation):\n{schema[:6000]}"
        budget_chars -= len(system)
        user_text = json.dumps(shrink(payload, max(budget_chars, 8000)), ensure_ascii=False, default=str)
        content: Any = user_text
        if images and settings.use_vision:
            content = [{"type": "text", "text": user_text}, *[image_part(img) for img in images[:3]]]
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}, {"role": "user", "content": content}]

        started = time.time()
        attempts = 0
        prompt_tokens = completion_tokens = 0
        error: str = ""
        try:
            for attempts in range(1, settings.max_retries + 1):
                raw, usage = self.client.complete(
                    messages,
                    thinking=self.thinking if thinking is None else thinking,
                    temperature=self.temperature,
                    on_event=on_event,
                )
                prompt_tokens += usage.get("prompt_tokens", 0)
                completion_tokens += usage.get("completion_tokens", 0)
                try:
                    result = output_model.model_validate(extract_json(raw))
                    self._record(project_id, attempts, prompt_tokens, completion_tokens, started, True, "")
                    return result
                except (ValueError, ValidationError) as exc:
                    error = mask(str(exc))[:600]
                    LOGGER.warning("%s: invalid model output (attempt %s): %s", self.name, attempts, error[:200])
                    messages.extend(
                        [
                            {"role": "assistant", "content": raw[:6000]},
                            {
                                "role": "user",
                                "content": "Your reply was not valid for the required schema: "
                                f"{error}\nReturn ONLY the corrected JSON object.",
                            },
                        ]
                    )
            raise ModelResponseError("The AI model kept returning malformed output. Try again or simplify the request.")
        except ModelError as exc:
            self._record(project_id, max(attempts, 1), prompt_tokens, completion_tokens, started, False, str(exc))
            raise

    def _record(self, project_id: str, attempts: int, ptok: int, ctok: int, started: float, ok: bool, error: str) -> None:
        if self.repository is None:
            return
        try:
            self.repository.log_ai_call(
                project_id=project_id,
                agent=self.name,
                model=self.client.model_name,
                prompt_tokens=ptok,
                completion_tokens=ctok,
                attempts=attempts,
                ok=ok,
                seconds=round(time.time() - started, 2),
                error=error,
            )
        except Exception:  # noqa: BLE001 - auditing must never break the workflow
            LOGGER.warning("Could not record AI call", exc_info=True)


__all__ = ["Agent", "estimate_tokens", "shrink"]
