"""Image-generation providers behind one interface.

The rest of the application depends only on ``ImageGenerator``. Nemotron never generates images:
it writes prompts, and one of these providers turns the prompt into a PNG.
"""

from __future__ import annotations

import base64
import logging
import re
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import requests

from config import AI_HORDE_URL, ImageSettings, get_image_settings
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
        return _download_image(self._session, url, self.settings.timeout)


class _NonRetryable(AIBookError):
    """Image error that must not be retried (bad key, rejected request)."""

    default_message = "Image generation failed."


class _NoWorker(_NonRetryable):
    """No AI Horde worker can serve the request as submitted."""


class _KudosLimit(_NonRetryable):
    """AI Horde wants kudos for a request this large. ``pixels`` is the no-kudos size limit when the message names it."""

    pixels: int | None = None


_KUDOS_SIZE = re.compile(r"over\s+(\d+)\s*x\s*(\d+)", re.IGNORECASE)

def _download_image(session: requests.Session, url: str, timeout: float) -> bytes:
    """Download an image over HTTPS with a size limit."""
    if urlparse(url).scheme != "https":
        raise _NonRetryable("The image service returned a non-HTTPS image URL, which was refused.")
    try:
        with session.get(url, timeout=timeout, stream=True) as response:
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


class AIHordeImageGenerator(ImageGenerator):
    """AI Horde (https://aihorde.net) crowd-sourced Stable Diffusion provider.

    Submits ``POST /generate/async``, polls ``/generate/check/{id}`` until done, reads ``/generate/status/{id}`` and
    downloads the image. The API key is sent only in the ``apikey`` header. Requests wait in a shared queue, so one image
    can take from seconds to several minutes.
    """

    name = "AI Horde"
    _MAX_PROMPT = 1000
    _POLL_SECONDS = 3.0
    # AI Horde asks for kudos above a size limit that changes with demand (836x836, 774x774, ...), and accounts
    # without kudos cannot pay. These sizes are small enough for today's limit; the real limit is learned from the
    # error message and applied to later images (see ``_fit``).
    _DIMENSIONS = {"cover": (640, 896), "portrait": (640, 896), "landscape": (896, 640), "square": (768, 768)}
    _sleep = staticmethod(time.sleep)

    def __init__(self, settings: ImageSettings | None = None, session: requests.Session | None = None) -> None:
        self.settings = settings or get_image_settings()
        self._session = session or requests.Session()
        self._slots = threading.BoundedSemaphore(max(1, self.settings.ai_horde_concurrency))
        self._base = AI_HORDE_URL
        self._pixel_limit: int | None = None  # largest width*height AI Horde accepted without kudos, once known
        self._steps_cap: int | None = None

    def _fit(self, width: int, height: int) -> tuple[int, int]:
        """Shrink a size (keeping its shape, in steps of 64) to fit the learned no-kudos pixel limit."""
        limit = self._pixel_limit
        if not limit or width * height <= limit * 0.95:
            return width, height
        scale = (limit * 0.95 / (width * height)) ** 0.5
        return max(384, int(width * scale) // 64 * 64), max(384, int(height * scale) // 64 * 64)

    def _learn_limit(self, error: _KudosLimit, width: int, height: int, steps: int) -> None:
        self._pixel_limit = error.pixels or int(width * height * 0.8)
        self._steps_cap = max(12, steps - 4)

    def generate_image(self, prompt: str, output_path: str | Path, orientation: str) -> Path:
        if not self.settings.ai_horde_key:
            raise ImageGenerationError("The AI Horde API key is missing (AI_HORDE_API_KEY).")
        base_width, base_height = self._DIMENSIONS.get(orientation, self._DIMENSIONS["square"])
        with self._slots:  # a few images at a time keeps within AI Horde's per-user limits
            for attempt in range(3):
                width, height = self._fit(base_width, base_height)
                steps = min(self.settings.ai_horde_steps, self._steps_cap or 999)
                try:
                    generation = self._draw_with_fallback(prompt, width, height, steps)
                    break
                except _KudosLimit as exc:
                    if attempt == 2:
                        raise
                    self._learn_limit(exc, width, height, steps)
                    LOGGER.info("AI Horde wants kudos for %sx%s; retrying smaller (%s pixels allowed).", width, height, self._pixel_limit)
        data = self._image_bytes(generation)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def _draw_with_fallback(self, prompt: str, width: int, height: int, steps: int) -> dict:
        try:
            return self._draw(prompt, width, height, steps, fast_only=self.settings.ai_horde_fast_only)
        except (_NoWorker, _KudosLimit):
            if not self.settings.ai_horde_fast_only:
                raise
            LOGGER.info("Fast-only AI Horde request not possible (no fast worker or kudos needed); allowing slow workers.")
            return self._draw(prompt, width, height, steps, fast_only=False)

    def _payload(self, prompt: str, width: int, height: int, steps: int, fast_only: bool) -> dict:
        models = self.settings.ai_horde_models
        params: dict = {"width": width, "height": height, "steps": steps, "n": 1}
        if all("flux" in name.lower() for name in models):
            params.update({"steps": min(steps, 8), "cfg_scale": 1, "sampler_name": "k_euler"})
        return {
            "prompt": prompt[: self._MAX_PROMPT],
            "params": params,
            "models": models,
            "nsfw": False,
            "censor_nsfw": True,
            "slow_workers": not fast_only,
        }

    def _draw(self, prompt: str, width: int, height: int, steps: int, fast_only: bool) -> dict:
        payload = self._payload(prompt, width, height, steps, fast_only)
        request_id = call_with_retries(lambda: self._submit(payload), retryable=(ImageGenerationError,))
        try:
            return self._wait(request_id)
        except BaseException:
            self._cancel(request_id)
            raise

    # ------------------------------------------------------------------ HTTP
    def _headers(self) -> dict[str, str]:
        return {"apikey": self.settings.ai_horde_key, "Client-Agent": "AI-Book-Studio:1.0", "Content-Type": "application/json"}

    @staticmethod
    def _message(response) -> str:
        try:
            data = response.json()
            return str(data.get("message", ""))[:300] if isinstance(data, dict) else ""
        except ValueError:
            return ""

    def _request(self, method: str, path: str, **kwargs) -> dict:
        try:
            response = self._session.request(method, f"{self._base}{path}", headers=self._headers(), timeout=30, **kwargs)
        except requests.Timeout as exc:
            raise ImageGenerationError("AI Horde timed out.") from exc
        except requests.RequestException as exc:
            LOGGER.warning("AI Horde network error: %s", redact(exc))
            raise ImageGenerationError("Could not reach AI Horde.") from exc
        detail = self._message(response)
        if response.status_code in (401, 403):
            if "kudos" in detail.lower():
                error = _KudosLimit(
                    "AI Horde needs kudos for this image size even after shrinking it. Lower AI_HORDE_STEPS, "
                    "or earn kudos by registering and running a worker. " + f"({redact(detail)})"
                )
                match = _KUDOS_SIZE.search(detail)
                if match:
                    error.pixels = int(match.group(1)) * int(match.group(2))
                raise error
            raise _NonRetryable("AI Horde rejected the API key. Check AI_HORDE_API_KEY." + (f" ({redact(detail)})" if detail else ""))
        if response.status_code in (429, 500, 502, 503, 504):
            raise ImageGenerationError(f"AI Horde is busy or unavailable (HTTP {response.status_code}).")
        if not response.ok:
            LOGGER.warning("AI Horde error %s: %s", response.status_code, redact(detail or response.text[:300]))
            raise _NonRetryable(f"AI Horde rejected the image request (HTTP {response.status_code})" + (f": {redact(detail)}" if detail else "."))
        try:
            data = response.json()
        except ValueError as exc:
            raise ImageGenerationError("AI Horde returned a response that is not JSON.") from exc
        if not isinstance(data, dict):
            raise ImageGenerationError("AI Horde returned an unexpected response.")
        return data

    def _submit(self, payload: dict) -> str:
        data = self._request("POST", "/generate/async", json=payload)
        request_id = data.get("id")
        if not isinstance(request_id, str) or not request_id:
            raise ImageGenerationError("AI Horde did not accept the request.")
        return request_id

    def _wait(self, request_id: str) -> dict:
        """Poll the queue until the image is ready, then return the first generation."""
        deadline = time.monotonic() + self.settings.ai_horde_timeout
        while True:
            status = call_with_retries(lambda: self._request("GET", f"/generate/check/{request_id}"), retryable=(ImageGenerationError,))
            if status.get("faulted"):
                raise ImageGenerationError("AI Horde could not draw this image.")
            if status.get("done"):
                break
            if status.get("is_possible") is False:
                raise _NoWorker(f"No AI Horde worker is available for the model(s) '{', '.join(self.settings.ai_horde_models)}'.")
            if time.monotonic() >= deadline:
                raise ImageGenerationError("AI Horde took too long (the shared queue is busy).")
            self._sleep(self._POLL_SECONDS)
        result = call_with_retries(lambda: self._request("GET", f"/generate/status/{request_id}"), retryable=(ImageGenerationError,))
        generations = result.get("generations")
        if not isinstance(generations, list) or not generations or not isinstance(generations[0], dict):
            raise ImageGenerationError("AI Horde returned no image.")
        return generations[0]

    def _cancel(self, request_id: str) -> None:
        """Best effort: free the queue slot when we stop waiting."""
        try:
            self._session.delete(f"{self._base}/generate/status/{request_id}", headers=self._headers(), timeout=15)
        except requests.RequestException:
            pass

    def _image_bytes(self, generation: dict) -> bytes:
        if generation.get("censored"):
            raise _NonRetryable("AI Horde's safety filter blocked this image.")
        image = generation.get("img")
        if not isinstance(image, str) or not image:
            raise ImageGenerationError("AI Horde returned no image.")
        if image.startswith("http"):
            return _download_image(self._session, image, 60)
        try:
            return base64.b64decode(image.split(",", 1)[-1], validate=False)
        except ValueError as exc:
            raise ImageGenerationError("The AI Horde image could not be decoded.") from exc


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
    """AI Horde when configured, else the OpenAI-compatible API, else the development placeholder."""
    settings = settings or get_image_settings()
    if settings.use_ai_horde:
        return AIHordeImageGenerator(settings)
    return ApiImageGenerator(settings) if settings.use_api else PlaceholderImageGenerator()
