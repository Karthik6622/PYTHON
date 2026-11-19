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
    """Thin wrapper around the OpenAI SDK. Configuration comes from ``ModelSettings`` only.

    ``complete`` walks the role's model chain (see ``ModelSettings.chain``): transient errors are retried on the same
    model, and a model that is retired, missing or keeps failing is skipped in favour of the next one."""

    def __init__(self, settings: ModelSettings | None = None) -> None:
        self.settings = settings or get_settings().model
        self._client: Any = None
        self.last_model = ""

    @property
    def model_name(self) -> str:
        return self.last_model or self.settings.name

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
        role: str = "main",
    ) -> tuple[str, dict[str, int]]:
        """Stream a completion. Returns ``(content, usage)``. ``on_event('reasoning'|'content', text)`` is optional."""
        import openai

        settings = self.settings
        failures: list[str] = []
        for position, model in enumerate(settings.chain(role)):
            # Only the vision model receives screenshots; fallbacks get the same request as text.
            sendable = messages if position == 0 and role == "vision" else _without_images(messages)
            for attempt in range(1, settings.max_retries + 1):
                try:
                    text, usage = self._stream_once(model, sendable, thinking, temperature, max_tokens, on_event)
                    self.last_model = model
                    return text, usage
                except (openai.APIConnectionError, openai.APITimeoutError, openai.RateLimitError, openai.InternalServerError) as exc:
                    delay = min(2 ** attempt, 20)
                    LOGGER.warning("%s failed (attempt %s/%s): %s", model, attempt, settings.max_retries, type(exc).__name__)
                    if attempt < settings.max_retries:
                        time.sleep(delay)
                    else:
                        failures.append(f"{model}: {type(exc).__name__}")
                except openai.AuthenticationError as exc:
                    raise ModelError("The model API key was rejected. Check MODEL_API_KEY / NVIDIA_API_KEY.") from exc
                except ModelError as exc:  # empty reply
                    LOGGER.warning("%s: %s", model, exc)
                    failures.append(f"{model}: empty reply")
                    break
                except openai.APIStatusError as exc:  # retired (410), unknown (404) or rejected (400) for this model
                    LOGGER.warning("%s returned HTTP %s; trying the next model", model, exc.status_code)
                    failures.append(f"{model}: HTTP {exc.status_code}")
                    break
        raise ModelError("No configured model could answer (" + "; ".join(failures)[:300] + "). Try again in a moment.")

    def _stream_once(
        self,
        model: str,
        messages: list[dict[str, Any]],
        thinking: bool | None,
        temperature: float | None,
        max_tokens: int | None,
        on_event: Callable[[str, str], None] | None,
    ) -> tuple[str, dict[str, int]]:
        settings = self.settings
        enable = settings.enable_thinking if thinking is None else thinking
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": settings.temperature if temperature is None else temperature,
            "top_p": settings.top_p,
            "max_tokens": max_tokens or settings.max_tokens,
            "stream": True,
        }
        if settings.seed is not None:
            kwargs["seed"] = settings.seed
        if settings.provider.lower() in {"nvidia", "nemotron"} and "nemotron" in model:
            kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": bool(enable)}}
        stream = self._sdk().chat.completions.create(**kwargs)
        parts: list[str] = []
        finish = ""
        for chunk in stream:
            if not getattr(chunk, "choices", None):
                continue
            choice = chunk.choices[0]
            finish = getattr(choice, "finish_reason", None) or finish
            delta = choice.delta
            reasoning = getattr(delta, "reasoning_content", None) or getattr(delta, "reasoning", None)
            if reasoning and on_event:
                on_event("reasoning", reasoning)
            if delta.content:
                parts.append(delta.content)
                if on_event:
                    on_event("content", delta.content)
        content = "".join(parts)
        prompt_text = json.dumps([m.get("content") if isinstance(m.get("content"), str) else "[multimodal]" for m in messages])
        usage = {"prompt_tokens": estimate_tokens(prompt_text), "completion_tokens": estimate_tokens(content), "truncated": int(finish == "length")}
        if not content.strip():
            raise ModelError("The model returned an empty response.")
        return content, usage

    def ping(self) -> str:
        """Tiny request used by the Status page to verify the key, endpoint and model name."""
        content, _ = self.complete(
            [{"role": "user", "content": "Reply with the single word: ready"}], thinking=False, max_tokens=16, temperature=0
        )
        return content.strip()[:80]


def _without_images(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Copy of ``messages`` with image parts removed (text-only models reject them)."""
    cleaned: list[dict[str, Any]] = []
    for message in messages:
        content = message.get("content")
        if isinstance(content, list):
            text = "\n".join(part.get("text", "") for part in content if part.get("type") == "text")
            cleaned.append({**message, "content": text})
        else:
            cleaned.append(message)
    return cleaned
