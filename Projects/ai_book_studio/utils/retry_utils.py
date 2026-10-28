"""Application errors, secret redaction and retry with exponential backoff."""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from typing import TypeVar

from config import MAX_API_RETRIES, RETRY_DELAYS

LOGGER = logging.getLogger("ai_book_studio")
T = TypeVar("T")


class AIBookError(Exception):
    """Base class. ``user_message`` is safe to show in the interface."""

    default_message = "Something went wrong."

    def __init__(self, message: str | None = None) -> None:
        self.user_message = message or self.default_message
        super().__init__(self.user_message)


class ConfigurationError(AIBookError):
    default_message = "The application is not configured correctly."


class NvidiaKeyMissingError(ConfigurationError):
    default_message = (
        "NVIDIA API key is missing. Add NVIDIA_API_KEY to .streamlit/secrets.toml or to your environment."
    )


class NvidiaAuthError(AIBookError):
    default_message = "NVIDIA API authentication failed. Check that NVIDIA_API_KEY is valid and has access."


class ModelRequestError(AIBookError):
    default_message = "The model rejected the request."


class TransientAPIError(AIBookError):
    """Temporary problem that is worth retrying."""

    default_message = "A temporary network or service error occurred."


class NvidiaRateLimitError(TransientAPIError):
    default_message = "NVIDIA API rate limit reached. Please wait a moment and try again."


class ModelUnavailableError(TransientAPIError):
    default_message = "Model is temporarily unavailable. Please try again shortly."


class EmptyResponseError(TransientAPIError):
    default_message = "The model returned an empty response."


class InvalidModelResponseError(AIBookError):
    default_message = "The model returned invalid JSON."


class ContentPolicyError(AIBookError):
    default_message = "This request cannot be processed because of the content policy."


class PlanValidationError(AIBookError):
    default_message = "The book plan is not valid."


class ImageGenerationError(AIBookError):
    default_message = "Image generation failed."


class ExportError(AIBookError):
    default_message = "Export failed."


class ProjectLoadError(AIBookError):
    default_message = "Saved project could not be loaded."


RETRYABLE_ERRORS: tuple[type[Exception], ...] = (
    TransientAPIError,
    InvalidModelResponseError,
    ImageGenerationError,
)

_SECRET_PATTERNS = (
    re.compile(r"nvapi-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{8,}"),
    re.compile(r"(?i)(api[_-]?key|token|secret)(\"?\s*[:=]\s*\"?)[A-Za-z0-9._\-]{8,}"),
    re.compile(r"sk-[A-Za-z0-9_\-]{12,}"),
    re.compile(r"fal_sk_[A-Za-z0-9]+(?::[A-Za-z0-9]+)?"),
    re.compile(r"\b[sp]k_[A-Za-z0-9]{12,}"),
)


def redact(text: object) -> str:
    """Remove anything that looks like an API key from text destined for logs or the UI."""
    value = str(text)
    for pattern in _SECRET_PATTERNS:
        value = pattern.sub(lambda m: (m.group(1) + m.group(2) + "***") if m.lastindex and m.lastindex >= 2 else "***", value)
    return value


def call_with_retries(
    func: Callable[[], T],
    *,
    retryable: tuple[type[Exception], ...] = RETRYABLE_ERRORS,
    delays: tuple[float, ...] = RETRY_DELAYS,
    max_retries: int = MAX_API_RETRIES,
    sleep: Callable[[float], None] = time.sleep,
    on_retry: Callable[[int, float, Exception], None] | None = None,
) -> T:
    """Call ``func``; on a retryable error wait 2s, 5s, then 10s (exponential-style) and retry.

    Authentication, permission and request errors are not in ``retryable`` and are raised at once.
    """
    attempt = 0
    while True:
        try:
            return func()
        except retryable as exc:
            if attempt >= min(max_retries, len(delays)):
                raise
            delay = delays[attempt]
            attempt += 1
            LOGGER.warning("Retry %d/%d in %.0fs after %s: %s", attempt, max_retries, delay, type(exc).__name__, redact(exc))
            if on_retry:
                on_retry(attempt, delay, exc)
            sleep(delay)
