"""NVIDIA Cosmos3-Nano API client.

All HTTP logic lives here so the rest of the app never touches the network or
the API key directly. Every failure is raised as a :class:`CineForgeError`
subclass carrying a short user-facing message, a hint and *redacted* technical
details that are safe to display.
"""

from __future__ import annotations

import base64
import binascii
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

import requests

import config

StageCallback = Callable[[str], None]

STAGE_PREPARING = "Preparing request"
STAGE_CONNECTING = "Connecting to NVIDIA"
STAGE_GENERATING = "Generating video"
STAGE_DECODING = "Decoding output"
STAGE_PREVIEW = "Preparing preview"
STAGES = (STAGE_PREPARING, STAGE_CONNECTING, STAGE_GENERATING, STAGE_DECODING, STAGE_PREVIEW)

_SECRET_PATTERNS = (
    re.compile(r"nvapi-[A-Za-z0-9_\-]+"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-\.=]+"),
)
_MAX_DETAIL_CHARS = 1500


# --------------------------------------------------------------------------- #
# Exceptions                                                                  #
# --------------------------------------------------------------------------- #
class CineForgeError(Exception):
    """Base class for all expected, user-presentable errors."""

    title = "Something went wrong"
    hint = ""

    def __init__(
        self,
        message: str,
        *,
        hint: str | None = None,
        status_code: int | None = None,
        details: str = "",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint if hint is not None else self.hint
        self.status_code = status_code
        self.details = details

    def to_safe_dict(self) -> dict[str, Any]:
        """Return a dict that is safe to store in session state and display."""
        return {
            "type": type(self).__name__,
            "title": self.title,
            "message": self.message,
            "hint": self.hint,
            "status_code": self.status_code,
            "details": self.details,
        }


class MissingApiKeyError(CineForgeError):
    title = "NVIDIA API key missing"
    hint = (
        "Add NVIDIA_API_KEY to .streamlit/secrets.toml (or the NVIDIA_API_KEY "
        "environment variable for local development), then restart the app."
    )


class BadRequestError(CineForgeError):
    title = "Malformed request (400)"
    hint = "Shorten or simplify the prompt and try again."


class AuthenticationError(CineForgeError):
    title = "Authentication failed (401)"
    hint = "The API key is invalid, expired or revoked. Generate a new key on build.nvidia.com."


class AccessDeniedError(CineForgeError):
    title = "Access denied (403)"
    hint = (
        f"Open {config.API_MODEL_PAGE_URL}, accept the API trial terms and "
        "confirm that endpoint access is enabled for your account."
    )


class EndpointNotFoundError(CineForgeError):
    title = "Endpoint not found (404)"
    hint = (
        "NVIDIA's gateway does not serve this URL. If a standalone curl/requests call to the same "
        "URL also returns 404, the hosted endpoint is not live for your account right now and "
        "nothing in this app can fix it. Check the 'View API Code' panel for a different "
        "invocation URL and set NVIDIA_API_URL in .streamlit/secrets.toml (or .env). A "
        f"self-hosted NIM uses http://<host>:8000{config.SELF_HOSTED_NIM_PATH}."
    )


class InvalidRequestFieldError(CineForgeError):
    title = "Invalid or unsupported request field (422)"
    hint = (
        "Cosmos3-Nano is a Preview endpoint and its schema may change. Compare "
        "the payload in config.py with NVIDIA's current 'View API Code' example."
    )


class RateLimitError(CineForgeError):
    title = "Rate limit reached (429)"
    hint = "Your free-trial or rate limit was reached. Wait a few minutes before retrying."


class ServerError(CineForgeError):
    title = "NVIDIA server error"
    hint = "This is a temporary NVIDIA-side problem. Try again in a few minutes."


class RequestTimeoutError(CineForgeError):
    title = "Request timed out"
    hint = "Video generation took longer than the allowed time. Try again or simplify the prompt."


class NetworkError(CineForgeError):
    title = "Network error"
    hint = "Check your internet connection, proxy or firewall settings."


class ResponseFormatError(CineForgeError):
    title = "Unexpected API response"
    hint = "The response did not contain a video. Retry; if it persists the Preview schema may have changed."


class InvalidVideoDataError(CineForgeError):
    title = "Invalid video data"
    hint = "The returned video could not be decoded. Try generating again."


class UnsupportedVideoFormatError(CineForgeError):
    title = "Unsupported video format"
    hint = "The returned file is not a playable MP4 (H.264/MP4 container expected)."


_STATUS_ERRORS: dict[int, type[CineForgeError]] = {
    400: BadRequestError,
    401: AuthenticationError,
    403: AccessDeniedError,
    404: EndpointNotFoundError,
    422: InvalidRequestFieldError,
    429: RateLimitError,
}


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #
def redact_secrets(text: str, api_key: str | None = None) -> str:
    """Remove the API key and any bearer/nvapi tokens from ``text``."""
    cleaned = text or ""
    if api_key:
        cleaned = cleaned.replace(api_key, "[REDACTED]")
    for pattern in _SECRET_PATTERNS:
        cleaned = pattern.sub("[REDACTED]", cleaned)
    return cleaned


def _safe_details(text: str, api_key: str | None) -> str:
    cleaned = redact_secrets(text, api_key)
    if len(cleaned) > _MAX_DETAIL_CHARS:
        cleaned = cleaned[:_MAX_DETAIL_CHARS] + "… [truncated]"
    return cleaned


def decode_base64_video(raw_value: str) -> bytes:
    """Strip an optional data-URI prefix and decode Base64 into bytes."""
    value = raw_value.strip()
    if value.startswith("data:") and "," in value:
        value = value.split(",", 1)[1]
    value = re.sub(r"\s+", "", value)
    value += "=" * (-len(value) % 4)
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as error:
        raise InvalidVideoDataError(
            "The video data returned by the API is not valid Base64.",
            details=type(error).__name__,
        ) from error


def validate_mp4(video_bytes: bytes) -> None:
    """Raise if ``video_bytes`` is empty or not an MP4/ISO-BMFF container."""
    if not video_bytes:
        raise InvalidVideoDataError("The API returned an empty video.")
    if len(video_bytes) < 12 or video_bytes[4:8] != b"ftyp":
        raise UnsupportedVideoFormatError(
            "The returned data is not an MP4 file.",
            details=f"First bytes: {video_bytes[:12].hex()}",
        )


def _error_from_response(response: requests.Response, api_key: str) -> CineForgeError:
    status = response.status_code
    details = _safe_details(response.text, api_key)
    if status in _STATUS_ERRORS:
        error_class = _STATUS_ERRORS[status]
        message = {
            400: "NVIDIA rejected the request as malformed.",
            401: "NVIDIA could not authenticate the API key.",
            403: "Your account does not have access to this endpoint yet.",
            404: "NVIDIA could not find the requested endpoint.",
            422: "NVIDIA rejected one of the request fields.",
            429: "The free-trial or rate limit has been reached.",
        }[status]
        return error_class(message, status_code=status, details=details)
    if status >= 500:
        return ServerError(
            f"NVIDIA returned a server error ({status}).", status_code=status, details=details
        )
    if status == 202:
        return ResponseFormatError(
            "NVIDIA accepted the job but returned no video yet (asynchronous result).",
            hint="This app only supports synchronous responses. Check 'View API Code' for polling instructions.",
            status_code=status,
            details=details,
        )
    return CineForgeError(
        f"Unexpected API response ({status}).", status_code=status, details=details
    )


# --------------------------------------------------------------------------- #
# Public API                                                                  #
# --------------------------------------------------------------------------- #
@dataclass
class VideoResult:
    """Decoded video plus metadata that is safe to store and display."""

    video_bytes: bytes
    metadata: dict[str, Any] = field(default_factory=dict)


def generate_video(
    prompt: str,
    negative_prompt: str,
    api_key: str | None,
    optional_supported_parameters: Mapping[str, Any] | None = None,
    on_stage: StageCallback | None = None,
    timeout: int = config.REQUEST_TIMEOUT_SECONDS,
) -> VideoResult:
    """Generate a video with Cosmos3-Nano and return the decoded MP4 bytes.

    Raises:
        CineForgeError: a subclass describing exactly what failed.
    """
    notify = on_stage or (lambda _stage: None)

    notify(STAGE_PREPARING)
    if not api_key or not api_key.strip():
        raise MissingApiKeyError("No NVIDIA API key is configured.")
    api_key = api_key.strip()
    if not prompt or not prompt.strip():
        raise BadRequestError("The prompt is empty.", hint="Enter a video description first.")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    payload = config.build_payload(prompt.strip(), negative_prompt, optional_supported_parameters)

    api_url = config.get_api_url()
    notify(STAGE_CONNECTING)
    started = time.monotonic()
    try:
        notify(STAGE_GENERATING)
        response = requests.post(
            api_url,
            headers=headers,
            json=payload,
            timeout=(config.CONNECT_TIMEOUT_SECONDS, timeout),
        )
    except requests.Timeout as error:
        raise RequestTimeoutError(
            "The request timed out before NVIDIA returned a video.",
            details=type(error).__name__,
        ) from error
    except requests.RequestException as error:
        raise NetworkError(
            "Could not reach NVIDIA.",
            details=_safe_details(f"{type(error).__name__}: {error}", api_key),
        ) from error
    elapsed = time.monotonic() - started

    if response.status_code != 200:
        error = _error_from_response(response, api_key)
        if isinstance(error, EndpointNotFoundError):
            error.details = f"URL: {api_url}\n{error.details}"
        raise error

    notify(STAGE_DECODING)
    try:
        body = response.json()
    except ValueError as error:
        raise ResponseFormatError(
            "The API response was not valid JSON.",
            details=_safe_details(response.text, api_key),
        ) from error
    if not isinstance(body, dict):
        raise ResponseFormatError("The API response had an unexpected structure.")

    video_value = body.get(config.RESPONSE_VIDEO_FIELD)
    if not isinstance(video_value, str) or not video_value.strip():
        safe_keys = ", ".join(sorted(str(key) for key in body)) or "none"
        raise ResponseFormatError(
            f"The response did not include '{config.RESPONSE_VIDEO_FIELD}'.",
            details=f"Response fields: {safe_keys}",
        )

    video_bytes = decode_base64_video(video_value)
    validate_mp4(video_bytes)

    metadata = {
        "status_code": response.status_code,
        "elapsed_seconds": round(elapsed, 1),
        "size_bytes": len(video_bytes),
        "request_id": response.headers.get("nvcf-reqid", ""),
        "response_fields": sorted(str(key) for key in body if key != config.RESPONSE_VIDEO_FIELD),
    }
    return VideoResult(video_bytes=video_bytes, metadata=metadata)


@dataclass(frozen=True)
class ConnectionStatus:
    """Result of the lightweight connection test."""

    ok: bool
    message: str


def check_connection(api_key: str | None) -> ConnectionStatus:
    """Check key presence and whether the endpoint route exists, without spending quota.

    An *unauthenticated* empty request is sent (the key is never transmitted):
    401/403/422 prove the route exists, 404 proves it does not.
    """
    if not api_key:
        return ConnectionStatus(False, "No API key configured.")
    if not api_key.startswith(config.API_KEY_PREFIX):
        return ConnectionStatus(
            False, f"The key does not start with '{config.API_KEY_PREFIX}'. Check the value."
        )
    api_url = config.get_api_url()
    try:
        response = requests.post(
            api_url, json={}, headers={"Accept": "application/json"},
            timeout=config.CONNECT_TIMEOUT_SECONDS,
        )
    except requests.RequestException:
        return ConnectionStatus(False, "NVIDIA could not be reached. Check your network.")
    if response.status_code == 404:
        return ConnectionStatus(
            False,
            f"Endpoint not found (404) at {api_url}. Set NVIDIA_API_URL to the invocation "
            "URL from the model page's 'View API Code' panel.",
        )
    if response.status_code >= 500:
        return ConnectionStatus(False, f"NVIDIA returned a server error ({response.status_code}).")
    return ConnectionStatus(
        True, "Endpoint found. The key itself is verified on the first generation."
    )
