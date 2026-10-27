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


def _openai_client(settings: ModelSettings):
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ModelConfigurationError("The OpenAI SDK is missing. Install the project requirements.") from exc
    return OpenAI(
        api_key=settings.api_key,
        base_url=settings.base_url,
        max_retries=0,
    )


def stream_completion(messages: list[dict[str, str]]) -> Iterator[str]:
    settings = get_model_settings()
    client = _openai_client(settings)
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
                max_tokens=settings.max_tokens,
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
            if emitted:
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
            if isinstance(content, str) and content.strip():
                return content.strip()
        except Exception as exc:
            errors.append(exc)
    if errors:
        raise errors[-1]
    raise RuntimeError("The configured model returned an empty routing response.")
