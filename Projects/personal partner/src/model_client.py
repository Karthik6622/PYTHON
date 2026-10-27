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
    api_key = _configured("LLM_API_KEY")
    if not api_key or api_key == "YOUR_LLM_API_KEY":
        raise ModelConfigurationError(
            "Add LLM_API_KEY to .streamlit/secrets.toml or your local .env file to enable chat."
        )
    try:
        temperature = float(_configured("LLM_TEMPERATURE", "0.6"))
        max_tokens = int(_configured("LLM_MAX_TOKENS", "700"))
    except ValueError as exc:
        raise ModelConfigurationError("LLM temperature and token settings must be numeric.") from exc
    if not 0 <= temperature <= 1:
        raise ModelConfigurationError("LLM_TEMPERATURE must be between 0 and 1.")
    if not 64 <= max_tokens <= 4_000:
        raise ModelConfigurationError("LLM_MAX_TOKENS must be between 64 and 4000.")
    base_url = _configured("LLM_BASE_URL") or None
    model = _configured("LLM_MODEL", "gpt-4o-mini")
    return ModelSettings(api_key, base_url, model, temperature, max_tokens)


def stream_completion(messages: list[dict[str, str]]) -> Iterator[str]:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ModelConfigurationError("The OpenAI SDK is missing. Install the project requirements.") from exc

    settings = get_model_settings()
    client = OpenAI(
        api_key=settings.api_key,
        base_url=settings.base_url,
        max_retries=0,
    )
    stream = client.chat.completions.create(
        model=settings.model,
        messages=messages,
        temperature=settings.temperature,
        max_tokens=settings.max_tokens,
        stream=True,
    )
    for chunk in stream:
        if not chunk.choices:
            continue
        content = chunk.choices[0].delta.content
        if isinstance(content, str) and content:
            yield content
