"""Agent base class: system prompt, validated input, structured output, retries, logging and context budgeting."""

from __future__ import annotations

import json
import re
import time
import typing
from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from ats.ai.client import ModelClient, estimate_tokens, extract_json, image_part, json_candidates
from ats.ai.prompts import get_prompt
from ats.config import get_settings
from ats.errors import ModelError, ModelResponseError, ModelTruncatedError
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


def _list_field(model: type[BaseModel]) -> str | None:
    """The one list-of-items field of an output model such as ``TestCaseList.test_cases`` (None for any other shape)."""
    lists = [name for name, f in model.model_fields.items() if typing.get_origin(f.annotation) is list]
    others = [name for name, f in model.model_fields.items() if f.is_required() and name not in lists]
    return lists[0] if len(lists) == 1 and not others else None


def _key(text: str) -> str:
    return re.sub(r"[^a-z]", "", text.lower())


def reshape(value: Any, model: type[BaseModel]) -> Any:
    """Bring common shape mistakes into the expected form: a bare list, or the list under a differently named key
    (``testCases``, ``cases``, ``items``...)."""
    field = _list_field(model)
    if field is None:
        return value
    if isinstance(value, list):
        return {field: value}
    if isinstance(value, dict) and field not in value:
        wanted = _key(field)
        for key, item in value.items():
            if isinstance(item, list) and (_key(key) == wanted or _key(key).rstrip("s") == wanted.rstrip("s")):
                return {**value, field: item}
        lists = [item for item in value.values() if isinstance(item, list) and item and isinstance(item[0], dict)]
        if len(lists) == 1:
            return {**value, field: lists[0]}
    return value


def validate_items(value: Any, model: type[T]) -> tuple[T | None, int]:
    """For list outputs: keep every item that is valid and drop the broken ones. Returns (result or None, dropped count)."""
    field = _list_field(model)
    if field is None or not isinstance(value, dict) or not isinstance(value.get(field), list):
        return None, 0
    item_model = typing.get_args(model.model_fields[field].annotation)[0]
    good, dropped = [], 0
    for item in value[field]:
        try:
            good.append(item_model.model_validate(item) if isinstance(item_model, type) and issubclass(item_model, BaseModel) else item)
        except ValidationError:
            dropped += 1
    if not good:
        return None, dropped
    try:
        return model.model_validate({**value, field: good}), dropped
    except ValidationError:
        return None, dropped


def salvage_items(text: str) -> list[dict[str, Any]]:
    """The complete objects at the start of a JSON list that was cut off (an answer that hit the output limit)."""
    start = text.find("[")
    if start < 0:
        return []
    decoder = json.JSONDecoder()
    items: list[dict[str, Any]] = []
    index = start + 1
    while index < len(text):
        while index < len(text) and text[index] in " \t\r\n,":
            index += 1
        if index >= len(text) or text[index] != "{":
            break
        try:
            item, index = decoder.raw_decode(text, index)
        except ValueError:
            break  # the last object was cut off
        if isinstance(item, dict):
            items.append(item)
    return items


class Agent:
    """One logical agent. Subclasses define ``name`` and call ``invoke`` with a task prompt and an output model."""

    name = "agent"
    thinking: bool | None = None  # None = use the global MODEL_ENABLE_THINKING setting
    temperature: float | None = None
    model_role = "main"  # "main" (reasoning), "fast" (short text tasks); screenshots always use the vision model

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
        role = self.model_role
        if images and settings.use_vision:
            content = [{"type": "text", "text": user_text}, *[image_part(img) for img in images[:3]]]
            role = "vision"
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
                    role=role,
                )
                prompt_tokens += usage.get("prompt_tokens", 0)
                completion_tokens += usage.get("completion_tokens", 0)
                truncated = bool(usage.get("truncated"))
                parsed: Any = None
                try:
                    # reasoning text can contain small JSON examples before the real answer: the last valid candidate wins
                    candidates = json_candidates(raw)
                    if not candidates:
                        raise ValueError("no JSON value found in the model response")
                    result = None
                    for candidate in reversed(candidates):
                        try:
                            parsed = reshape(candidate, output_model)
                            result = output_model.model_validate(parsed)
                            break
                        except (ValueError, ValidationError) as exc:
                            error = mask(str(exc))[:600]
                    if result is None:
                        parsed = reshape(candidates[-1], output_model)  # partial salvage below works on the final answer
                        raise ValueError(error)
                    self._record(project_id, attempts, prompt_tokens, completion_tokens, started, True, "")
                    return result
                except (ValueError, ValidationError) as exc:
                    error = mask(str(exc))[:600]
                # a list answer with a few broken items, or one that was cut off: keep every complete, valid item
                partial, dropped = validate_items(parsed, output_model) if parsed is not None else (None, 0)
                if partial is None and _list_field(output_model):
                    partial, dropped = validate_items({_list_field(output_model): salvage_items(raw)}, output_model)
                if partial is not None:
                    LOGGER.warning("%s: kept the valid part of the answer (dropped %s item(s), cut off: %s)", self.name, dropped, truncated)
                    self._record(project_id, attempts, prompt_tokens, completion_tokens, started, True, f"partial answer, {dropped} item(s) dropped")
                    if hasattr(partial, "_partial"):
                        partial._partial = True
                    return partial
                if truncated:
                    raise ModelTruncatedError("The AI model's answer was too long and was cut off. Ask for less at a time.")
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
