"""OpenAI-compatible chat client used by every agent (Nemotron by default, streaming, retries, JSON extraction)."""

from __future__ import annotations

import base64
import json
import re
import time
from collections.abc import Callable
from typing import Any

from ats.config import ModelSettings, get_settings
from ats.errors import ConfigurationError, ModelError
from ats.logging_setup import get_logger
from ats.security import mask

LOGGER = get_logger("ai.client")

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_FENCE = re.compile(r"^```(?:json|JSON)?\s*|\s*```$")


def estimate_tokens(text: str) -> int:
    """Cheap token estimate (about 4 characters per token) used for context budgeting."""
    return max(len(text) // 4, 1)


def extract_json(text: str) -> Any:
    """Find the first JSON object/array in model output (tolerates thinking blocks and markdown fences)."""
    cleaned = _THINK_BLOCK.sub("", text or "").strip()
    cleaned = _FENCE.sub("", cleaned).strip()
    decoder = json.JSONDecoder()
    for index, char in enumerate(cleaned):
        if char in "{[":
            try:
                value, _ = decoder.raw_decode(cleaned[index:])
                return value
            except ValueError:
                continue
    raise ValueError("no JSON value found in the model response")


def image_part(data: bytes, mime: str = "image/png") -> dict[str, Any]:
    encoded = base64.b64encode(data).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}}


class ModelClient:
    """Thin wrapper around the OpenAI SDK. Configuration comes from ``ModelSettings`` only."""

    def __init__(self, settings: ModelSettings | None = None) -> None:
        self.settings = settings or get_settings().model
        self._client: Any = None

    @property
    def model_name(self) -> str:
        return self.settings.name

    def _sdk(self) -> Any:
        if not self.settings.configured:
            raise ConfigurationError("The AI model is not configured. Set MODEL_API_KEY (or NVIDIA_API_KEY) in .env.")
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                base_url=self.settings.base_url,
                api_key=self.settings.api_key,
                timeout=self.settings.timeout_seconds,
                max_retries=0,  # retries are handled here so they can be logged
            )
        return self._client

    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        thinking: bool | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        on_event: Callable[[str, str], None] | None = None,
    ) -> tuple[str, dict[str, int]]:
        """Stream a completion. Returns ``(content, usage)``. ``on_event('reasoning'|'content', text)`` is optional."""
        import openai

        settings = self.settings
        last_error: Exception | None = None
        for attempt in range(1, settings.max_retries + 1):
            try:
                return self._stream_once(messages, thinking, temperature, max_tokens, on_event)
            except (openai.APIConnectionError, openai.APITimeoutError, openai.RateLimitError, openai.InternalServerError) as exc:
                last_error = exc
                delay = min(2 ** attempt, 20)
                LOGGER.warning("Model call failed (attempt %s/%s): %s. Retrying in %ss", attempt, settings.max_retries, type(exc).__name__, delay)
                if attempt < settings.max_retries:
                    time.sleep(delay)
            except openai.AuthenticationError as exc:
                raise ModelError("The model API key was rejected. Check MODEL_API_KEY.") from exc
            except openai.BadRequestError as exc:
                raise ModelError(f"The model rejected the request: {mask(str(exc))[:300]}") from exc
            except openai.APIStatusError as exc:
                raise ModelError(f"The model service returned an error ({exc.status_code}).") from exc
        raise ModelError("The model service is unavailable or rate limited. Try again in a moment.") from last_error

    def _stream_once(
        self,
        messages: list[dict[str, Any]],
        thinking: bool | None,
        temperature: float | None,
        max_tokens: int | None,
        on_event: Callable[[str, str], None] | None,
    ) -> tuple[str, dict[str, int]]:
        settings = self.settings
        enable = settings.enable_thinking if thinking is None else thinking
        kwargs: dict[str, Any] = {
            "model": settings.name,
            "messages": messages,
            "temperature": settings.temperature if temperature is None else temperature,
            "top_p": settings.top_p,
            "max_tokens": max_tokens or settings.max_tokens,
            "stream": True,
        }
        if settings.seed is not None:
            kwargs["seed"] = settings.seed
        if settings.provider.lower() in {"nvidia", "nemotron"}:
            kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": bool(enable)}}
        stream = self._sdk().chat.completions.create(**kwargs)
        parts: list[str] = []
        for chunk in stream:
            if not getattr(chunk, "choices", None):
                continue
            delta = chunk.choices[0].delta
            reasoning = getattr(delta, "reasoning_content", None)
            if reasoning and on_event:
                on_event("reasoning", reasoning)
            if delta.content:
                parts.append(delta.content)
                if on_event:
                    on_event("content", delta.content)
        content = "".join(parts)
        prompt_text = json.dumps([m.get("content") if isinstance(m.get("content"), str) else "[multimodal]" for m in messages])
        usage = {"prompt_tokens": estimate_tokens(prompt_text), "completion_tokens": estimate_tokens(content)}
        if not content.strip():
            raise ModelError("The model returned an empty response.")
        return content, usage

    def ping(self) -> str:
        """Tiny request used by the Settings page to verify the key, endpoint and model name."""
        content, _ = self.complete(
            [{"role": "user", "content": "Reply with the single word: ready"}], thinking=False, max_tokens=16, temperature=0
        )
        return content.strip()[:80]
