"""Image-generation providers behind one interface.

The rest of the application depends only on ``ImageGenerator``. Nemotron never generates images:
it writes prompts, and one of these providers turns the prompt into a PNG.
"""

from __future__ import annotations

import base64
import logging
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import requests

from config import ImageSettings, get_image_settings
from utils.image_utils import (
    COVER_SIZE,
    ORIENTATION_SIZES,
    make_placeholder_image,
    normalize_png,
    validate_image,
)
from utils.retry_utils import (
    AIBookError,
    ImageGenerationError,
    call_with_retries,
    redact,
)

LOGGER = logging.getLogger("ai_book_studio.images")
_MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024


@dataclass(frozen=True)
class ImageResult:
    """Outcome of one image request."""

    path: Path
    placeholder_used: bool = False
    warning: str = ""


class ImageGenerator(ABC):
    """Abstract image provider."""

    name = "image provider"

    @abstractmethod
    def generate_image(self, prompt: str, output_path: str | Path, orientation: str) -> Path:
        """Create a PNG at ``output_path`` from ``prompt`` and return the path. Raise ``ImageGenerationError`` on failure."""


class PlaceholderImageGenerator(ImageGenerator):
    """Development provider that draws abstract gradient art locally. It never contacts the network."""

    name = "placeholder (development)"

    def generate_image(self, prompt: str, output_path: str | Path, orientation: str) -> Path:
        size = COVER_SIZE if orientation == "cover" else ORIENTATION_SIZES.get(orientation, ORIENTATION_SIZES["square"])
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        make_placeholder_image(size, seed=prompt).save(path, "PNG")
        return path


class ApiImageGenerator(ImageGenerator):
    """Configurable HTTP provider that speaks the common ``/images/generations`` JSON format.

    Works with OpenAI-compatible image endpoints. The endpoint, model, sizes and extra body fields are all
    configurable through ``IMAGE_API_URL``, ``IMAGE_API_MODEL``, ``IMAGE_API_SIZE_*`` and ``IMAGE_API_EXTRA_JSON``.
    The API key is sent only in the Authorization header.
    """

    name = "image API"

    def __init__(self, settings: ImageSettings | None = None, session: requests.Session | None = None) -> None:
        self.settings = settings or get_image_settings()
        self._session = session or requests.Session()

    def generate_image(self, prompt: str, output_path: str | Path, orientation: str) -> Path:
        if not self.settings.api_key:
            raise ImageGenerationError("The image API key is missing (IMAGE_API_KEY).")
        size_key = "portrait" if orientation == "cover" else orientation
        body = {
            "model": self.settings.model,
            "prompt": prompt,
            "n": 1,
            "size": self.settings.sizes.get(size_key, self.settings.sizes["square"]),
            **self.settings.extra_body,
        }
        if self.settings.response_format:
            body["response_format"] = self.settings.response_format
        payload = call_with_retries(lambda: self._post(body), retryable=(ImageGenerationError,))
        data = self._extract_bytes(payload)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    # ------------------------------------------------------------------ HTTP
    def _post(self, body: dict) -> dict:
        try:
            response = self._session.post(
                self.settings.api_url,
                json=body,
                headers={"Authorization": f"Bearer {self.settings.api_key}", "Content-Type": "application/json"},
                timeout=self.settings.timeout,
            )
        except requests.Timeout as exc:
            raise ImageGenerationError("The image API timed out.") from exc
        except requests.RequestException as exc:
            LOGGER.warning("Image API network error: %s", redact(exc))
            raise ImageGenerationError("Could not reach the image API.") from exc
        if response.status_code in (401, 403):
            raise _NonRetryable("Image API authentication failed. Check IMAGE_API_KEY.")
        if response.status_code in (429, 500, 502, 503, 504):
            raise ImageGenerationError(f"The image API is busy or unavailable (HTTP {response.status_code}).")
        if not response.ok:
            LOGGER.warning("Image API error %s: %s", response.status_code, redact(response.text[:300]))
            raise _NonRetryable(f"The image API rejected the request (HTTP {response.status_code}).")
        try:
            data = response.json()
        except ValueError as exc:
            raise ImageGenerationError("The image API returned a response that is not JSON.") from exc
        if not isinstance(data, dict):
            raise ImageGenerationError("The image API returned an unexpected response.")
        return data

    def _extract_bytes(self, payload: dict) -> bytes:
        """Find image bytes in the common response layouts (b64_json, url, image, artifacts)."""
        candidates: list[dict] = []
        if isinstance(payload.get("data"), list):
            candidates.extend(item for item in payload["data"] if isinstance(item, dict))
        for key in ("images", "artifacts"):
            if isinstance(payload.get(key), list):
                candidates.extend(item if isinstance(item, dict) else {"b64_json": item} for item in payload[key])
        candidates.append(payload)
        for item in candidates:
            for key in ("b64_json", "base64", "image", "b64"):
                value = item.get(key)
                if isinstance(value, str) and value:
                    try:
                        return base64.b64decode(value.split(",", 1)[-1], validate=False)
                    except ValueError:
                        continue
            url = item.get("url")
            if isinstance(url, str) and url:
                return self._download(url)
        raise ImageGenerationError("The image API response did not contain an image.")

    def _download(self, url: str) -> bytes:
        if urlparse(url).scheme != "https":
            raise _NonRetryable("The image API returned a non-HTTPS image URL, which was refused.")
        try:
            with self._session.get(url, timeout=self.settings.timeout, stream=True) as response:
                response.raise_for_status()
                chunks, total = [], 0
                for chunk in response.iter_content(65536):
                    total += len(chunk)
                    if total > _MAX_DOWNLOAD_BYTES:
                        raise _NonRetryable("The generated image is too large.")
                    chunks.append(chunk)
        except requests.RequestException as exc:
            raise ImageGenerationError("The generated image could not be downloaded.") from exc
        return b"".join(chunks)


class _NonRetryable(AIBookError):
    """Image error that must not be retried (bad key, rejected request)."""

    default_message = "Image generation failed."


class _RateLimited(AIBookError):
    """HTTP 429: too many requests (or the daily free allowance is used up)."""

    default_message = "The image service rate limit was reached."

    def __init__(self, message: str | None = None, retry_after: float = 0.0) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class CloudflareImageGenerator(ImageGenerator):
    """Cloudflare Workers AI provider (``@cf/black-forest-labs/flux-1-schnell``).

    Calls ``POST /accounts/{id}/ai/run/{model}`` with a bearer token. The reply is JSON with a base64 JPEG in
    ``result.image``; it is converted to PNG by the caller. The token is sent only in the Authorization header.
    """

    name = "Cloudflare FLUX.1 schnell"
    _BASE = "https://api.cloudflare.com/client/v4/accounts"
    _MAX_PROMPT = 2048
    _STEPS = 8  # FLUX.1 schnell accepts 1-8 steps
    _RATE_DELAYS = (15.0, 30.0, 60.0)  # waits after HTTP 429 before giving up
    _COOLDOWN_SECONDS = 300.0  # after repeated 429s, skip Cloudflare for a while instead of waiting on every image
    _slots = threading.BoundedSemaphore(2)  # at most two images are requested at the same time
    _state_lock = threading.Lock()
    _cooldown_until = 0.0
    _sleep = staticmethod(time.sleep)

    def __init__(self, settings: ImageSettings | None = None, session: requests.Session | None = None) -> None:
        self.settings = settings or get_image_settings()
        self._session = session or requests.Session()

    def generate_image(self, prompt: str, output_path: str | Path, orientation: str) -> Path:
        if not (self.settings.cloudflare_account_id and self.settings.cloudflare_token):
            raise ImageGenerationError("Cloudflare is not configured (CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN).")
        with self._state_lock:
            remaining = type(self)._cooldown_until - time.time()
        if remaining > 0:
            raise _NonRetryable(
                f"Cloudflare's image limit was reached (HTTP 429), so images are paused for about {int(remaining // 60) + 1} min. "
                "The free plan has a daily allowance."
            )
        body = {
            "prompt": prompt[: self._MAX_PROMPT],
            "steps": self._STEPS,
        }
        with self._slots:
            payload = self._post_with_backoff(body)
        data = self._extract_bytes(payload)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def _post_with_backoff(self, body: dict) -> dict:
        """Send the request; on HTTP 429 wait (honouring Retry-After) and try again, then pause Cloudflare for a while."""
        for attempt in range(len(self._RATE_DELAYS) + 1):
            try:
                return call_with_retries(lambda: self._post(body), retryable=(ImageGenerationError,))
            except _RateLimited as exc:
                if attempt >= len(self._RATE_DELAYS):
                    break
                self._sleep(min(max(exc.retry_after, self._RATE_DELAYS[attempt]), 120.0))
        with self._state_lock:
            type(self)._cooldown_until = time.time() + self._COOLDOWN_SECONDS
        raise _NonRetryable(
            "Cloudflare says there were too many image requests (HTTP 429). The free plan has a daily allowance that resets "
            "every day; the remaining images use placeholders. Run the book again later to replace them."
        )

    def _post(self, body: dict) -> dict:
        url = f"{self._BASE}/{self.settings.cloudflare_account_id}/ai/run/{self.settings.cloudflare_model}"
        try:
            response = self._session.post(
                url,
                json=body,
                headers={"Authorization": f"Bearer {self.settings.cloudflare_token}", "Content-Type": "application/json"},
                timeout=self.settings.timeout,
            )
        except requests.Timeout as exc:
            raise ImageGenerationError("Cloudflare timed out while drawing the image.") from exc
        except requests.RequestException as exc:
            LOGGER.warning("Cloudflare network error: %s", redact(exc))
            raise ImageGenerationError("Could not reach Cloudflare.") from exc
        if response.status_code in (401, 403):
            raise _NonRetryable("Cloudflare authentication failed. Check CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID.")
        if response.status_code == 429:
            try:
                retry_after = float(response.headers.get("Retry-After", 0))
            except (TypeError, ValueError, AttributeError):
                retry_after = 0.0
            raise _RateLimited("Cloudflare is rate limiting image requests (HTTP 429).", retry_after)
        if response.status_code in (500, 502, 503, 504):
            raise ImageGenerationError(f"Cloudflare is busy or unavailable (HTTP {response.status_code}).")
        if not response.ok:
            detail = self._error_detail(response)
            LOGGER.warning("Cloudflare error %s: %s", response.status_code, redact(detail or response.text[:300]))
            raise _NonRetryable(
                f"Cloudflare rejected the image request (HTTP {response.status_code})" + (f": {redact(detail)}" if detail else ".")
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise ImageGenerationError("Cloudflare returned a response that is not JSON.") from exc
        if not isinstance(data, dict):
            raise ImageGenerationError("Cloudflare returned an unexpected response.")
        return data

    @staticmethod
    def _error_detail(response) -> str:
        """Cloudflare's own explanation, e.g. {"errors": [{"code": 5006, "message": "..."}]}."""
        try:
            errors = response.json().get("errors") or []
            messages = [f"{e.get('message', '')} (code {e.get('code', '?')})" for e in errors if isinstance(e, dict)]
            return "; ".join(messages)[:300]
        except (ValueError, AttributeError):
            return ""

    @staticmethod
    def _extract_bytes(payload: dict) -> bytes:
        result = payload.get("result")
        encoded = result.get("image") if isinstance(result, dict) else None
        if not isinstance(encoded, str) or not encoded:
            raise ImageGenerationError("The Cloudflare response did not contain an image.")
        try:
            return base64.b64decode(encoded.split(",", 1)[-1], validate=False)
        except ValueError as exc:
            raise ImageGenerationError("The Cloudflare image could not be decoded.") from exc


def generate_illustration(
    generator: ImageGenerator, prompt: str, output_path: str | Path, orientation: str
) -> ImageResult:
    """Generate, validate and normalise an image. Falls back to a placeholder and says so when it fails."""
    path = Path(output_path)
    size = COVER_SIZE if orientation == "cover" else ORIENTATION_SIZES.get(orientation, ORIENTATION_SIZES["square"])
    reason = ""
    try:
        generated = generator.generate_image(prompt, path, orientation)
        ok, problem = validate_image(generated)
        if ok:
            normalize_png(generated, size)
            return ImageResult(path=Path(generated))
        reason = f"The provider returned an unusable image ({problem})."
    except AIBookError as exc:
        reason = exc.user_message
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("Unexpected image error: %s: %s", type(exc).__name__, redact(exc))
        reason = f"Unexpected image error ({type(exc).__name__})."
    LOGGER.warning("Using placeholder image: %s", reason)
    PlaceholderImageGenerator().generate_image(prompt, path, orientation)
    return ImageResult(path=path, placeholder_used=True, warning=f"Placeholder used. {reason}")


def get_image_generator(settings: ImageSettings | None = None) -> ImageGenerator:
    """Cloudflare FLUX when configured, else the OpenAI-compatible API, else the development placeholder."""
    settings = settings or get_image_settings()
    if settings.use_cloudflare:
        return CloudflareImageGenerator(settings)
    return ApiImageGenerator(settings) if settings.use_api else PlaceholderImageGenerator()
