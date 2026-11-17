"""Video generation API client.

Two providers are supported: a free LTX-Video Hugging Face Space (default, no
API key needed) and the NVIDIA Cosmos3-Nano hosted API (``VIDEO_PROVIDER=nvidia``).
All network logic lives here so the rest of the app never touches the network or
any token directly. Every failure is raised as a :class:`CineForgeError`
subclass carrying a short user-facing message, a hint and *redacted* technical
details that are safe to display.
"""

from __future__ import annotations

import base64
import binascii
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

import requests

import config

StageCallback = Callable[[str], None]
ProgressCallback = Callable[[float, str], None]

STAGE_PREPARING = "Preparing request"
STAGE_CONNECTING = "Connecting to the video service"
STAGE_GENERATING = "Generating video"
STAGE_DECODING = "Decoding output"
STAGE_PREVIEW = "Preparing preview"
STAGES = (STAGE_PREPARING, STAGE_CONNECTING, STAGE_GENERATING, STAGE_DECODING, STAGE_PREVIEW)

_SECRET_PATTERNS = (
    re.compile(r"nvapi-[A-Za-z0-9_\-]+"),
    re.compile(r"hf_[A-Za-z0-9]{10,}"),
    re.compile(r"sk_[A-Za-z0-9]{10,}"),
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

# Hugging Face failures that make the quota-free renderer worth trying.
_FALLBACK_ERRORS = (RateLimitError, ServerError, NetworkError, RequestTimeoutError)


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
    on_progress: ProgressCallback | None = None,
) -> VideoResult:
    """Generate a video with Cosmos3-Nano and return the decoded MP4 bytes.

    Raises:
        CineForgeError: a subclass describing exactly what failed.
    """
    notify = on_stage or (lambda _stage: None)

    notify(STAGE_PREPARING)
    if config.get_provider() == config.PROVIDER_HUGGINGFACE:
        return _generate_with_fallbacks(
            prompt, negative_prompt, optional_supported_parameters, notify, timeout, on_progress
        )
    api_url = config.get_api_url()
    api_key = (api_key or "").strip()
    if not api_key and config.api_key_required(api_url):
        raise MissingApiKeyError("No NVIDIA API key is configured.")
    if not prompt or not prompt.strip():
        raise BadRequestError("The prompt is empty.", hint="Enter a video description first.")

    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = config.build_payload(prompt.strip(), negative_prompt, optional_supported_parameters)

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


def _generate_with_fallbacks(
    prompt: str,
    negative_prompt: str,
    params: Mapping[str, Any] | None,
    notify: StageCallback,
    timeout: int,
    on_progress: ProgressCallback | None,
) -> VideoResult:
    """Try OpenRouter (Veo), Bytez, the Hugging Face Space, then the quota-free renderer, in order."""
    import picture_video  # imported here: picture_video itself imports this module

    if not prompt or not prompt.strip():
        raise BadRequestError("The prompt is empty.", hint="Enter a video description first.")
    if config.pictures_only():
        notify(STAGE_GENERATING)
        return picture_video.generate_video(prompt, params, on_progress)

    # (label, runner, may fall through on any expected error)
    attempts: list[tuple[str, Callable[[], VideoResult], bool]] = []
    if config.get_openrouter_key():
        attempts.append((
            f"OpenRouter ({config.get_openrouter_model()})",
            lambda: _generate_video_openrouter(prompt, negative_prompt, params, notify, timeout, on_progress),
            True,
        ))
    if config.get_bytez_key():
        attempts.append((
            f"Bytez ({config.get_bytez_model()})",
            lambda: _generate_video_bytez(prompt, notify, timeout, on_progress),
            True,
        ))
    attempts.append((
        "Hugging Face Space",
        lambda: _generate_video_huggingface(prompt, negative_prompt, params, notify, timeout, on_progress),
        False,
    ))

    failures: list[str] = []
    headline: CineForgeError | None = None
    used = ""
    result: VideoResult | None = None
    for position, (label, run, always_fall_through) in enumerate(attempts):
        try:
            result = run()
            used = label
            break
        except CineForgeError as error:
            if not (always_fall_through or isinstance(error, _FALLBACK_ERRORS)):
                raise
            failures.append(f"{label}: {error.message} {error.details}".strip())
            headline = error
            if on_progress:
                following = attempts[position + 1][0] if position + 1 < len(attempts) else "the quota-free renderer"
                on_progress(0.0, f"{label.split(' (')[0]} unavailable · trying {following.split(' (')[0]}")
    if result is None:
        notify(STAGE_GENERATING)
        try:
            result = picture_video.generate_video(prompt, params, on_progress)
            used = "the quota-free renderer (AI key-frames with camera motion)"
        except CineForgeError as fallback_error:
            assert headline is not None  # the Hugging Face attempt always runs
            headline.details = "\n".join([*failures, f"Quota-free renderer: {fallback_error.message}"])
            raise headline from None  # the last real provider failure stays the headline
    if failures:
        short = "; ".join(f.split(": ", 1)[0] + ": " + f.split(": ", 1)[1].split(". ")[0] for f in failures)
        result.metadata["fallback_reason"] = failures[-1]
        result.metadata["fallback_note"] = f"{short}. This video was made with {used}."
    return result


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
    api_url = config.get_api_url()
    if config.get_provider() == config.PROVIDER_HUGGINGFACE:
        if config.get_openrouter_key() and not config.pictures_only():
            return _check_connection_openrouter()
        if config.get_bytez_key() and not config.pictures_only():
            return _check_connection_bytez()
        return _check_connection_huggingface()
    if config.api_key_required(api_url):
        if not api_key:
            return ConnectionStatus(False, "No API key configured.")
        if not api_key.startswith(config.API_KEY_PREFIX):
            return ConnectionStatus(
                False, f"The key does not start with '{config.API_KEY_PREFIX}'. Check the value."
            )
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


# --------------------------------------------------------------------------- #
# OpenRouter provider: Google Veo 3.1 (asynchronous job API)                  #
# --------------------------------------------------------------------------- #
def _openrouter_error(response: requests.Response, key: str, model: str) -> CineForgeError:
    status = response.status_code
    details = _safe_details(response.text, key)
    if status == 400:
        return BadRequestError(
            f"OpenRouter rejected the request for {model}.", status_code=status, details=details
        )
    if status == 401:
        return AuthenticationError("OpenRouter could not authenticate OPENROUTER_API_KEY.", status_code=status, details=details)
    if status == 402:
        return AccessDeniedError(
            "The OpenRouter account has no credits left for this video.",
            hint="Add credits or raise the key limit at openrouter.ai/settings/credits.",
            status_code=status,
            details=details,
        )
    if status == 404:
        return EndpointNotFoundError(
            f"OpenRouter does not offer the model '{model}'.",
            hint="Set OPENROUTER_VIDEO_MODEL to an id from https://openrouter.ai/api/v1/videos/models.",
            status_code=status,
            details=details,
        )
    if status == 429:
        return RateLimitError("OpenRouter rate limit reached.", status_code=status, details=details)
    if status >= 500:
        return ServerError(f"OpenRouter returned a server error ({status}).", status_code=status, details=details)
    return CineForgeError(f"Unexpected OpenRouter response ({status}).", status_code=status, details=details)


def openrouter_request_options(params: Mapping[str, Any] | None) -> dict[str, Any]:
    """Map the app's size/duration plan to values Veo accepts (4/6/8 s, 16:9 or 9:16, 720p/1080p)."""
    options = dict(params or {})
    wanted = float(options.get("duration", 6))
    durations = config.OPENROUTER_DURATIONS
    duration = next((d for d in durations if d >= wanted - 0.01), durations[-1])
    width, height = int(options.get("width", 704)), int(options.get("height", 384))
    return {
        "duration": duration,
        "aspect_ratio": "9:16" if height > width else "16:9",
        "resolution": "720p" if max(width, height) <= 512 else "1080p",
    }


def _generate_video_openrouter(
    prompt: str,
    negative_prompt: str,
    params: Mapping[str, Any] | None,
    notify: StageCallback,
    timeout: int,
    on_progress: ProgressCallback | None = None,
) -> VideoResult:
    key = config.get_openrouter_key() or ""
    model = config.get_openrouter_model()
    progress = on_progress or (lambda _fraction, _message: None)
    headers = {"Authorization": f"Bearer {key}", "X-Title": config.APP_NAME}
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt.strip()[: config.OPENROUTER_MAX_PROMPT_CHARS],
        "generate_audio": True,
        **openrouter_request_options(params),
    }
    if (seed := (params or {}).get("seed")):
        payload["seed"] = int(seed)
    if negative_prompt and negative_prompt.strip() and model.startswith("google/veo"):
        payload["provider"] = {"options": {"google-vertex": {"parameters": {"negativePrompt": negative_prompt.strip()}}}}

    def request(method: str, url: str, **kwargs: Any) -> requests.Response:
        return _with_system_certificates(
            lambda: requests.request(
                method, url, headers=headers, timeout=(config.CONNECT_TIMEOUT_SECONDS, 120), **kwargs
            )
        )

    notify(STAGE_CONNECTING)
    progress(0.0, f"Submitting the job to {model} on OpenRouter")
    started = time.monotonic()
    deadline = started + max(timeout, 600)
    try:
        submit = request("POST", f"{config.OPENROUTER_API_BASE}/videos", json=payload)
        if submit.status_code not in (200, 201, 202):
            raise _openrouter_error(submit, key, model)
        job = submit.json()
        job_id, polling_url = job["id"], job.get("polling_url") or f"{config.OPENROUTER_API_BASE}/videos/{job['id']}"
        notify(STAGE_GENERATING)
        status: dict[str, Any] = job
        while status.get("status") != "completed":
            if status.get("status") == "failed":
                raise ServerError(
                    "OpenRouter could not generate the video.",
                    hint="The prompt may have been refused by the model's safety filters; try rewording it.",
                    details=_safe_details(str(status.get("error", "")), key),
                )
            if time.monotonic() > deadline:
                raise RequestTimeoutError("OpenRouter did not finish the video in time.", details=f"job {job_id}")
            time.sleep(config.OPENROUTER_POLL_SECONDS)
            elapsed = time.monotonic() - started
            message = "Queued on OpenRouter" if status.get("status") == "pending" else "Veo is rendering your video"
            progress(min(0.97, 1.0 - math.exp(-elapsed / config.OPENROUTER_EXPECTED_SECONDS)), message)
            poll = request("GET", polling_url)
            if poll.status_code != 200:
                raise _openrouter_error(poll, key, model)
            status = poll.json()
        urls = status.get("unsigned_urls") or status.get("urls") or []
        if not urls:
            raise ResponseFormatError("OpenRouter finished the job but returned no video link.")
        progress(0.98, "Downloading the rendered video")
        download = request("GET", urls[0])
        if download.status_code != 200:
            raise _openrouter_error(download, key, model)
    except requests.Timeout as error:
        raise RequestTimeoutError("OpenRouter did not respond in time.", details=type(error).__name__) from error
    except requests.RequestException as error:
        raise NetworkError(
            "Could not reach OpenRouter.", details=_safe_details(f"{type(error).__name__}: {error}", key)
        ) from error
    except (ValueError, KeyError, TypeError) as error:
        raise ResponseFormatError("The OpenRouter response had an unexpected structure.", details=type(error).__name__) from error
    notify(STAGE_DECODING)
    validate_mp4(download.content)
    progress(1.0, "Video rendered")
    usage = status.get("usage") or {}
    metadata = {
        "status_code": 200,
        "elapsed_seconds": round(time.monotonic() - started, 1),
        "size_bytes": len(download.content),
        "request_id": str(job_id),
        "response_fields": ["unsigned_urls"],
        "provider": "openrouter",
        "model": model,
        "native_audio": True,
        "cost_usd": usage.get("cost"),
    }
    return VideoResult(video_bytes=download.content, metadata=metadata)


def _check_connection_openrouter() -> ConnectionStatus:
    """Verify OPENROUTER_API_KEY via the free ``/key`` call and report the remaining budget."""
    key = config.get_openrouter_key() or ""
    try:
        response = _with_system_certificates(
            lambda: requests.get(
                f"{config.OPENROUTER_API_BASE}/key",
                headers={"Authorization": f"Bearer {key}"},
                timeout=config.CONNECT_TIMEOUT_SECONDS,
            )
        )
    except requests.RequestException:
        return ConnectionStatus(False, "OpenRouter could not be reached. Check your network.")
    if response.status_code in (401, 403):
        return ConnectionStatus(False, "OpenRouter rejected OPENROUTER_API_KEY. Check the value.")
    if response.status_code != 200:
        return ConnectionStatus(False, f"OpenRouter returned HTTP {response.status_code}.")
    remaining = (response.json().get("data") or {}).get("limit_remaining")
    budget = f" ${remaining:.2f} key limit left." if isinstance(remaining, (int, float)) else ""
    try:  # the key's limit is only a cap; the account balance decides whether Veo can run
        credits = _with_system_certificates(
            lambda: requests.get(
                f"{config.OPENROUTER_API_BASE}/credits",
                headers={"Authorization": f"Bearer {key}"},
                timeout=config.CONNECT_TIMEOUT_SECONDS,
            )
        ).json().get("data") or {}
        balance = float(credits["total_credits"]) - float(credits["total_usage"])
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return ConnectionStatus(True, f"OpenRouter key accepted. Model: {config.get_openrouter_model()}.{budget}")
    if balance <= 0:
        return ConnectionStatus(
            False,
            "OpenRouter key accepted, but the account has no credits, so Veo cannot run. "
            "Add credits at openrouter.ai/settings/credits (the app falls back to free providers meanwhile).",
        )
    return ConnectionStatus(
        True, f"OpenRouter key accepted. Model: {config.get_openrouter_model()}. ${balance:.2f} credit left."
    )


# --------------------------------------------------------------------------- #
# Bytez provider: Wan-AI text-to-video                                        #
# --------------------------------------------------------------------------- #
def _with_system_certificates(call: Callable[[], requests.Response]) -> requests.Response:
    """Run ``call``; on a TLS verification failure retry once using the OS certificate store."""
    try:
        return call()
    except requests.exceptions.SSLError:
        try:  # corporate TLS proxies re-sign traffic with a certificate only the OS trusts
            import truststore
        except ImportError:
            raise
        truststore.inject_into_ssl()
        return call()


def _bytez_error(response: requests.Response, key: str, model: str) -> CineForgeError:
    status = response.status_code
    details = _safe_details(response.text, key)
    if status == 401:
        return AuthenticationError("Bytez could not authenticate BYTEZ_KEY.", status_code=status, details=details)
    if status in (402, 403):
        return AccessDeniedError(
            f"Your Bytez plan cannot run {model}.",
            hint="Bytez's free plan only runs open models up to 7B parameters; larger ones need purchased credits.",
            status_code=status,
            details=details,
        )
    if status == 404:
        return EndpointNotFoundError(
            f"Bytez does not offer the model '{model}'.",
            hint="Set BYTEZ_MODEL to a text-to-video model id from the Bytez catalog.",
            status_code=status,
            details=details,
        )
    if status == 429:
        return RateLimitError("Bytez rate limit reached.", status_code=status, details=details)
    if status >= 500:
        return ServerError(f"Bytez returned a server error ({status}).", status_code=status, details=details)
    return CineForgeError(f"Unexpected Bytez response ({status}).", status_code=status, details=details)


def _generate_video_bytez(
    prompt: str, notify: StageCallback, timeout: int, on_progress: ProgressCallback | None = None
) -> VideoResult:
    if not prompt or not prompt.strip():
        raise BadRequestError("The prompt is empty.", hint="Enter a video description first.")
    key = config.get_bytez_key() or ""
    model = config.get_bytez_model()
    progress = on_progress or (lambda _fraction, _message: None)
    headers = {"Authorization": key, "Content-Type": "application/json"}
    body = {"text": prompt.strip()[: config.BYTEZ_MAX_PROMPT_CHARS]}

    def run() -> requests.Response:
        return _with_system_certificates(
            lambda: requests.post(
                f"{config.BYTEZ_API_BASE}/{model}",
                headers=headers,
                json=body,
                timeout=(config.CONNECT_TIMEOUT_SECONDS, timeout),
            )
        )

    notify(STAGE_CONNECTING)
    progress(0.0, f"Sending the prompt to {model.split('/')[-1]} on Bytez")
    started = time.monotonic()
    notify(STAGE_GENERATING)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(run)
            while True:
                try:
                    response = future.result(timeout=1.0)
                    break
                except FutureTimeout:
                    elapsed = time.monotonic() - started
                    progress(
                        min(0.97, 1.0 - math.exp(-elapsed / config.BYTEZ_EXPECTED_SECONDS)),
                        "Rendering frames on Bytez GPUs",
                    )
    except requests.Timeout as error:
        raise RequestTimeoutError("Bytez did not return a video in time.", details=type(error).__name__) from error
    except requests.RequestException as error:
        raise NetworkError(
            "Could not reach Bytez.", details=_safe_details(f"{type(error).__name__}: {error}", key)
        ) from error
    if response.status_code != 200:
        raise _bytez_error(response, key, model)

    notify(STAGE_DECODING)
    try:
        payload = response.json()
    except ValueError as error:
        raise ResponseFormatError("The Bytez response was not valid JSON.", details=_safe_details(response.text, key)) from error
    if not isinstance(payload, dict):
        raise ResponseFormatError("The Bytez response had an unexpected structure.")
    if payload.get("error"):
        raise ServerError("Bytez could not generate the video.", details=_safe_details(str(payload["error"]), key))
    output = payload.get("output")
    video_url = output.get("url") if isinstance(output, Mapping) else output
    if not isinstance(video_url, str) or not video_url.startswith("http"):
        raise ResponseFormatError(
            "The Bytez response did not include a video link.", details=f"Output type: {type(output).__name__}"
        )
    progress(0.98, "Downloading the rendered video")
    try:
        download = _with_system_certificates(
            lambda: requests.get(video_url, timeout=(config.CONNECT_TIMEOUT_SECONDS, 180))
        )
    except requests.RequestException as error:
        raise NetworkError("Could not download the Bytez video.", details=type(error).__name__) from error
    if download.status_code != 200:
        raise _bytez_error(download, key, model)
    validate_mp4(download.content)
    progress(1.0, "Video rendered")
    metadata = {
        "status_code": 200,
        "elapsed_seconds": round(time.monotonic() - started, 1),
        "size_bytes": len(download.content),
        "request_id": "",
        "response_fields": ["output"],
        "provider": "bytez",
        "model": model,
    }
    return VideoResult(video_bytes=download.content, metadata=metadata)


def _check_connection_bytez() -> ConnectionStatus:
    """Verify BYTEZ_KEY with the free ``list/tasks`` call (no credits used)."""
    key = config.get_bytez_key() or ""
    try:
        response = _with_system_certificates(
            lambda: requests.get(
                f"{config.BYTEZ_API_BASE}/list/tasks",
                headers={"Authorization": key},
                timeout=config.CONNECT_TIMEOUT_SECONDS,
            )
        )
    except requests.RequestException:
        return ConnectionStatus(False, "Bytez could not be reached. Check your network.")
    if response.status_code == 401:
        return ConnectionStatus(False, "Bytez rejected BYTEZ_KEY. Check the value.")
    if response.status_code != 200:
        return ConnectionStatus(False, f"Bytez returned HTTP {response.status_code}.")
    return ConnectionStatus(
        True, f"Bytez key accepted. Model: {config.get_bytez_model()} (falls back to free providers if unavailable)."
    )


# --------------------------------------------------------------------------- #
# Free provider: LTX-Video Hugging Face Space                                 #
# --------------------------------------------------------------------------- #
def _huggingface_error(error: BaseException, token: str | None) -> CineForgeError:
    text = f"{type(error).__name__}: {error}"
    details = _safe_details(text, token)
    lowered = text.lower()
    if any(word in lowered for word in ("quota", "zerogpu", "too many requests", "429")):
        return RateLimitError(
            "The free GPU quota of the Hugging Face Space has been used up.",
            hint=(
                "Wait a while and retry, or add a free Hugging Face token as HF_TOKEN in "
                ".streamlit/secrets.toml (or .env) to get a larger daily quota."
            ),
            details=details,
        )
    if isinstance(error, (OSError, ConnectionError)) or "connect" in lowered:
        return NetworkError("Could not reach the Hugging Face Space.", details=details)
    return ServerError(
        "The Hugging Face Space could not generate the video.",
        hint="The free Space may be busy or restarting. Try again in a minute or two.",
        details=details,
    )


def _queue_message(status: Any, elapsed: float) -> str:
    """Human-readable GPU queue/render message from a gradio ``StatusUpdate``."""
    code = str(getattr(getattr(status, "code", None), "name", "") or "").upper()
    rank = getattr(status, "rank", None)
    size = getattr(status, "queue_size", None)
    if code == "PENDING" and rank is not None and size:
        return f"Waiting for a free GPU · queue position {int(rank) + 1} of {int(size)}"
    if code in ("PROCESSING", "ITERATING", "PROGRESS"):
        return "Rendering frames on the GPU"
    return "Starting the GPU" if elapsed < 10 else "Rendering frames on the GPU"


def _generate_video_huggingface(
    prompt: str,
    negative_prompt: str,
    params: Mapping[str, Any] | None,
    notify: StageCallback,
    timeout: int,
    on_progress: ProgressCallback | None = None,
) -> VideoResult:
    if not prompt or not prompt.strip():
        raise BadRequestError("The prompt is empty.", hint="Enter a video description first.")
    try:
        from gradio_client import Client
    except ImportError as error:
        raise CineForgeError(
            "The 'gradio_client' package is not installed.",
            hint="Run: pip install -r requirements.txt",
        ) from error

    options = dict(params or {})
    seed = options.get("seed")
    token = config.get_hf_token()
    expected = float(options.get("expected_seconds", 110))
    progress = on_progress or (lambda _fraction, _message: None)

    notify(STAGE_CONNECTING)
    progress(0.0, "Connecting to the video service")
    started = time.monotonic()
    job = None
    try:
        client = Client(config.HF_SPACE_ID, token=token, verbose=False)
        notify(STAGE_GENERATING)
        job = client.submit(
            prompt=prompt.strip(),
            negative_prompt=negative_prompt.strip(),
            input_image_filepath=None,
            input_video_filepath=None,
            height_ui=options.get("height", 512),
            width_ui=options.get("width", 704),
            mode="text-to-video",
            duration_ui=options.get("duration", 2),
            ui_frames_to_use=9,
            seed_ui=seed if seed is not None else 42,
            randomize_seed=seed is None,
            ui_guidance_scale=1,
            improve_texture_flag=bool(options.get("improve_texture", True)),
            api_name=config.HF_API_NAME,
        )
        generation_started = time.monotonic()
        while not job.done():
            elapsed = time.monotonic() - generation_started
            if time.monotonic() - started > timeout:
                raise TimeoutError
            try:
                message = _queue_message(job.status(), elapsed)
            except Exception:  # status is informational only
                message = "Rendering frames on the GPU"
            # Smooth curve that approaches (but never reaches) 97% while the GPU works.
            progress(min(0.97, 1.0 - math.exp(-elapsed / expected)), message)
            time.sleep(1.0)
        output = job.result(timeout=5)
    except TimeoutError as error:
        if job is not None:
            job.cancel()
        raise RequestTimeoutError(
            "The Hugging Face Space did not return a video in time.",
            hint="The free Space may be busy. Try again or use a shorter, lower-quality clip.",
            details=type(error).__name__,
        ) from error
    except CineForgeError:
        raise
    except Exception as error:
        raise _huggingface_error(error, token) from error
    elapsed = time.monotonic() - started
    progress(1.0, "Video rendered")

    notify(STAGE_DECODING)
    video_ref = output[0] if isinstance(output, (tuple, list)) and output else output
    if isinstance(video_ref, Mapping):
        video_ref = video_ref.get("video")
    if not isinstance(video_ref, str) or not Path(video_ref).is_file():
        raise ResponseFormatError(
            "The Space response did not include a video file.",
            details=f"Response type: {type(output).__name__}",
        )
    video_path = Path(video_ref)
    video_bytes = video_path.read_bytes()
    video_path.unlink(missing_ok=True)
    validate_mp4(video_bytes)

    used_seed = output[1] if isinstance(output, (tuple, list)) and len(output) > 1 else None
    metadata = {
        "status_code": 200,
        "elapsed_seconds": round(elapsed, 1),
        "size_bytes": len(video_bytes),
        "request_id": "",
        "response_fields": ["seed"],
        "provider": config.PROVIDER_HUGGINGFACE,
        "seed": used_seed,
    }
    return VideoResult(video_bytes=video_bytes, metadata=metadata)


def _check_connection_huggingface() -> ConnectionStatus:
    """Check that the Space exists and is running, without spending GPU quota."""
    try:
        response = requests.get(
            f"https://huggingface.co/api/spaces/{config.HF_SPACE_ID}",
            timeout=config.CONNECT_TIMEOUT_SECONDS,
        )
    except requests.RequestException:
        return ConnectionStatus(False, "Hugging Face could not be reached. Check your network.")
    if response.status_code != 200:
        return ConnectionStatus(
            False, f"The Space '{config.HF_SPACE_ID}' was not found ({response.status_code})."
        )
    stage = str((response.json().get("runtime") or {}).get("stage", "UNKNOWN"))
    if stage != "RUNNING":
        return ConnectionStatus(False, f"The Space is not running right now (status: {stage}).")
    return ConnectionStatus(True, "Free LTX-Video Space is running. No API key is needed.")
