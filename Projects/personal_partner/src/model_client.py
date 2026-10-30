"""OpenAI-compatible streamed model client with configurable settings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterator

import streamlit as st


class ModelConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class ModelSettings:
    api_key: str
    base_url: str | None
    model: str
    temperature: float
    max_tokens: int


def _configured(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name)
    except Exception:
        value = None
    return str(value if value not in (None, "") else os.environ.get(name, default)).strip()


def get_model_settings() -> ModelSettings:
    # Keep Interview Studio's NVIDIA_API_KEY configuration working while
    # still allowing the generic LLM_* names for other compatible providers.
    api_key = _configured("NVIDIA_API_KEY") or _configured("LLM_API_KEY")
    if not api_key or api_key.casefold().startswith(("your-", "your_", "nvapi-your")):
        raise ModelConfigurationError(
            "Add NVIDIA_API_KEY or LLM_API_KEY to .streamlit/secrets.toml or your local .env file to enable chat."
        )
    try:
        temperature = float(_configured("LLM_TEMPERATURE", "0.6"))
        max_tokens = int(_configured("LLM_MAX_TOKENS", "1200"))
    except ValueError as exc:
        raise ModelConfigurationError("LLM temperature and token settings must be numeric.") from exc
    if not 0 <= temperature <= 1:
        raise ModelConfigurationError("LLM_TEMPERATURE must be between 0 and 1.")
    if not 64 <= max_tokens <= 4_000:
        raise ModelConfigurationError("LLM_MAX_TOKENS must be between 64 and 4000.")
    base_url = _configured("LLM_BASE_URL") or _configured(
        "NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"
    )
    model = _configured("LLM_MODEL")
    if not model or model.casefold() in {"your-model-id", "your_model_id"}:
        model = _configured("NVIDIA_MODEL", "nvidia/nemotron-3.5-bolt-e4b")
    return ModelSettings(api_key, base_url, model, temperature, max_tokens)


_THINKING_OFF_VARIANTS = (
    {"extra_body": {"chat_template_kwargs": {"enable_thinking": False}}},
    {"extra_body": {"chat_template_kwargs": {"thinking": False}}},
    {"reasoning_effort": "none"},
    {},
)


REQUEST_TIMEOUT_SECONDS = 45.0

# Errors where trying another request variant cannot help, so fail fast instead of waiting again.
_FATAL_ERRORS = {
    "APITimeoutError",
    "APIConnectionError",
    "AuthenticationError",
    "PermissionDeniedError",
    "RateLimitError",
}

_THINK_OPEN = "<think>"
_THINK_CLOSE = "</think>"


def _openai_client(settings: ModelSettings, timeout: float | None = None):
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ModelConfigurationError("The OpenAI SDK is missing. Install the project requirements.") from exc
    return OpenAI(
        api_key=settings.api_key,
        base_url=settings.base_url,
        max_retries=0,
        timeout=timeout or REQUEST_TIMEOUT_SECONDS,
    )


def _is_fatal(exc: Exception) -> bool:
    return type(exc).__name__ in _FATAL_ERRORS


def describe_model_error(exc: Exception) -> str:
    """A short, user-facing reason for a failed model call."""
    if isinstance(exc, ModelConfigurationError):
        return str(exc)
    name = type(exc).__name__
    if name == "APITimeoutError":
        return "The model took too long to answer. Please try again."
    if name == "RateLimitError":
        return "The model is busy right now. Please wait a moment and try again."
    if name in {"AuthenticationError", "PermissionDeniedError"}:
        return "The model rejected the API key. Check NVIDIA_API_KEY or LLM_API_KEY."
    if name == "APIConnectionError":
        return "Could not reach the model. Check your connection and try again."
    if "empty response" in str(exc):
        return "The model sent back an empty reply. Please try again."
    return "The assistant couldn't reply just now. Please try again."


def _partial_tag_length(text: str, tag: str) -> int:
    for size in range(min(len(tag) - 1, len(text)), 0, -1):
        if text.endswith(tag[:size]):
            return size
    return 0


def strip_think_blocks(chunks: Iterator[str]) -> Iterator[str]:
    """Drop <think>...</think> reasoning from a stream so it is never shown or spoken."""
    buffer = ""
    inside = False
    for chunk in chunks:
        buffer += chunk
        while True:
            if inside:
                end = buffer.find(_THINK_CLOSE)
                if end == -1:
                    buffer = buffer[-(len(_THINK_CLOSE) - 1):]
                    break
                buffer = buffer[end + len(_THINK_CLOSE):].lstrip()
                inside = False
                continue
            start = buffer.find(_THINK_OPEN)
            if start == -1:
                hold = _partial_tag_length(buffer, _THINK_OPEN)
                ready = buffer[: len(buffer) - hold]
                buffer = buffer[len(buffer) - hold:]
                if ready:
                    yield ready
                break
            if start:
                yield buffer[:start]
            buffer = buffer[start + len(_THINK_OPEN):]
            inside = True
    if not inside and buffer:
        yield buffer


def stream_completion(messages: list[dict[str, str]], max_tokens: int | None = None) -> Iterator[str]:
    """Stream a reply. max_tokens, when given, replaces the configured LLM_MAX_TOKENS limit (up to 4000)."""
    return strip_think_blocks(_stream_raw(messages, max_tokens))


def _stream_raw(messages: list[dict[str, str]], max_tokens: int | None = None) -> Iterator[str]:
    settings = get_model_settings()
    client = _openai_client(settings)
    token_limit = settings.max_tokens if max_tokens is None else min(4_000, max(64, max_tokens))
    errors: list[Exception] = []
    for options in _THINKING_OFF_VARIANTS:
        stream = None
        emitted = False
        try:
            stream = client.chat.completions.create(
                model=settings.model,
                messages=messages,
                temperature=settings.temperature,
                top_p=0.95,
                max_tokens=token_limit,
                stream=True,
                **options,
            )
            for chunk in stream:
                if not chunk.choices:
                    continue
                content = chunk.choices[0].delta.content
                if isinstance(content, str) and content:
                    emitted = True
                    yield content
            if emitted:
                return
        except Exception as exc:
            if emitted or _is_fatal(exc):
                raise
            errors.append(exc)
        finally:
            if stream is not None:
                try:
                    stream.close()
                except Exception:
                    pass
    if errors:
        raise errors[-1]
    raise RuntimeError("The configured model returned an empty response.")


def complete_text(messages: list[dict[str, str]], max_tokens: int = 200) -> str:
    """Return one non-streamed reply. Used by Nemotron for routing decisions."""
    settings = get_model_settings()
    client = _openai_client(settings)
    errors: list[Exception] = []
    for options in _THINKING_OFF_VARIANTS:
        try:
            response = client.chat.completions.create(
                model=settings.model,
                messages=messages,
                temperature=0.0,
                max_tokens=max_tokens,
                stream=False,
                **options,
            )
            content = response.choices[0].message.content if response.choices else None
            if isinstance(content, str):
                content = "".join(strip_think_blocks(iter([content]))).strip()
            if content:
                return content
        except Exception as exc:
            if _is_fatal(exc):
                raise
            errors.append(exc)
    if errors:
        raise errors[-1]
    raise RuntimeError("The configured model returned an empty routing response.")
