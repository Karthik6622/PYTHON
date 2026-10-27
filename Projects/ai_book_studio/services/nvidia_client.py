"""Client for NVIDIA NIM (OpenAI-compatible) running Nemotron 3.5 Lightning 30B A3B."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

import httpx
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
)
from pydantic import ValidationError

from config import MAX_OUTPUT_TOKENS, MIN_OUTPUT_TOKENS, PRESETS, NvidiaSettings, SamplingPreset, get_nvidia_settings
from prompts import SYSTEM_PROMPT
from utils.json_utils import extract_json_object
from utils.retry_utils import (
    AIBookError,
    EmptyResponseError,
    InvalidModelResponseError,
    ModelRequestError,
    ModelUnavailableError,
    NvidiaAuthError,
    NvidiaKeyMissingError,
    NvidiaRateLimitError,
    TransientAPIError,
    call_with_retries,
    redact,
)
from utils.text_utils import strip_reasoning

LOGGER = logging.getLogger("ai_book_studio.nvidia")
T = TypeVar("T")


@dataclass(frozen=True)
class ChatResult:
    """Text returned by the model and why it stopped (``length`` means it was cut off)."""

    text: str
    finish_reason: str | None = None

    @property
    def truncated(self) -> bool:
        return self.finish_reason == "length"


class LLMClient(Protocol):
    """What the rest of the application needs from a text model (also implemented by test fakes)."""

    def generate(self, prompt: str, preset: str | SamplingPreset, max_tokens: int | None = None) -> ChatResult: ...

    def generate_text(self, prompt: str, preset: str | SamplingPreset, max_tokens: int | None = None) -> str: ...

    def generate_json(
        self,
        prompt: str,
        preset: str | SamplingPreset,
        max_tokens: int | None = None,
        validator: Callable[[dict[str, Any]], T] | None = None,
    ) -> Any: ...


class NvidiaClient:
    """Streaming chat client with retries, JSON validation and clear error messages."""

    def __init__(self, settings: NvidiaSettings | None = None, client: OpenAI | None = None) -> None:
        self.settings = settings or get_nvidia_settings()
        if client is None:
            if not self.settings.configured:
                raise NvidiaKeyMissingError()
            client = OpenAI(
                base_url=self.settings.base_url,
                api_key=self.settings.api_key,
                timeout=self.settings.timeout,
            )
        self._client = client
        self._use_extra_body = True

    # ------------------------------------------------------------------ public API
    def generate(self, prompt: str, preset: str | SamplingPreset, max_tokens: int | None = None) -> ChatResult:
        """Send one prompt and return the text (retrying temporary failures and empty replies)."""
        sampling = PRESETS[preset] if isinstance(preset, str) else preset
        limit = self._token_limit(max_tokens or sampling.max_tokens)
        return call_with_retries(
            lambda: self._request(prompt, sampling, limit),
            retryable=(TransientAPIError,),
        )

    def generate_text(self, prompt: str, preset: str | SamplingPreset, max_tokens: int | None = None) -> str:
        """Like ``generate`` but returns only the text."""
        return self.generate(prompt, preset, max_tokens).text

    def generate_json(
        self,
        prompt: str,
        preset: str | SamplingPreset,
        max_tokens: int | None = None,
        validator: Callable[[dict[str, Any]], T] | None = None,
    ) -> Any:
        """Request JSON, parse it and optionally validate it; invalid JSON is retried with backoff."""
        sampling = PRESETS[preset] if isinstance(preset, str) else preset
        limit = self._token_limit(max_tokens or sampling.max_tokens)

        def attempt() -> Any:
            result = self._request(prompt, sampling, limit)
            data = extract_json_object(result.text)
            if not validator:
                return data
            try:
                return validator(data)
            except (ValidationError, ValueError, TypeError) as exc:
                LOGGER.warning("Model JSON failed validation: %s", redact(exc))
                raise InvalidModelResponseError(
                    "The model returned JSON that does not match the expected structure."
                ) from exc

        return call_with_retries(attempt, retryable=(TransientAPIError, InvalidModelResponseError))

    # ------------------------------------------------------------------ internals
    @staticmethod
    def _token_limit(value: int) -> int:
        return max(MIN_OUTPUT_TOKENS, min(int(value), MAX_OUTPUT_TOKENS))

    def _extra_body(self) -> dict[str, Any]:
        body: dict[str, Any] = {"chat_template_kwargs": {"enable_thinking": self.settings.enable_thinking}}
        if self.settings.enable_thinking:
            body["reasoning_budget"] = self.settings.reasoning_budget
        return body

    def _request(self, prompt: str, sampling: SamplingPreset, max_tokens: int) -> ChatResult:
        """One streaming request. Reasoning tokens (if enabled) are discarded; only the answer is returned."""
        total_tokens = max_tokens
        if self.settings.enable_thinking:
            total_tokens = min(max_tokens + self.settings.reasoning_budget, MAX_OUTPUT_TOKENS)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        use_extra = self._use_extra_body
        while True:
            kwargs: dict[str, Any] = {
                "model": self.settings.model,
                "messages": messages,
                "temperature": sampling.temperature,
                "top_p": sampling.top_p,
                "max_tokens": total_tokens,
                "stream": True,
            }
            if use_extra:
                kwargs["extra_body"] = self._extra_body()
            try:
                parts: list[str] = []
                finish: str | None = None
                for chunk in self._client.chat.completions.create(**kwargs):
                    if not chunk.choices:
                        continue
                    choice = chunk.choices[0]
                    if choice.delta and choice.delta.content:
                        parts.append(choice.delta.content)
                    if choice.finish_reason:
                        finish = choice.finish_reason
                break
            except BadRequestError as exc:
                if use_extra:  # the endpoint may not accept the extra chat-template options
                    LOGGER.warning("Retrying without extra_body after a 400 response: %s", redact(exc))
                    use_extra = False
                    self._use_extra_body = False
                    continue
                raise ModelRequestError(f"The model rejected the request: {redact(exc)}") from exc
            except AIBookError:
                raise
            except Exception as exc:  # noqa: BLE001 - translated into friendly errors
                raise self._translate(exc) from exc
        text = strip_reasoning("".join(parts))
        if not text:
            raise EmptyResponseError()
        return ChatResult(text=text, finish_reason=finish)

    @staticmethod
    def _translate(exc: Exception) -> AIBookError:
        """Map SDK and network exceptions to application errors. Technical details go to the log only."""
        LOGGER.error("NVIDIA request failed: %s: %s", type(exc).__name__, redact(exc))
        if isinstance(exc, (AuthenticationError, PermissionDeniedError)):
            return NvidiaAuthError()
        if isinstance(exc, RateLimitError):
            return NvidiaRateLimitError()
        if isinstance(exc, NotFoundError):
            return ModelRequestError("The model or endpoint was not found. Check NVIDIA_MODEL and NVIDIA_BASE_URL.")
        if isinstance(exc, APITimeoutError):
            return TransientAPIError("The request to the NVIDIA API timed out.")
        if isinstance(exc, APIConnectionError):
            return TransientAPIError("Could not connect to the NVIDIA API. Check your network connection.")
        if isinstance(exc, APIStatusError):
            if exc.status_code == 429:
                return NvidiaRateLimitError()
            if exc.status_code in (401, 403):
                return NvidiaAuthError()
            if exc.status_code >= 500:
                return ModelUnavailableError()
            return ModelRequestError(f"The NVIDIA API returned an error (HTTP {exc.status_code}).")
        if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
            return TransientAPIError("The connection to the NVIDIA API was interrupted.")
        return ModelRequestError(f"Unexpected error while contacting the model ({type(exc).__name__}).")
