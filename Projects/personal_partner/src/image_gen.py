"""Image generation with NVIDIA Cosmos 3 Nano.

By default the app calls NVIDIA's hosted API (build.nvidia.com/nvidia/cosmos3-nano) with the same NVIDIA_API_KEY used
for chat: POST https://ai.api.nvidia.com/v1/cosmos/nvidia/cosmos3-nano with model_mode=text2image, which returns a
base64 JPEG in `b64_image`.

To use your own GPU server instead (for example `sglang serve --model-path nvidia/Cosmos3-Nano`), set
IMAGE_GEN_BASE_URL (for example http://gpu-host:30000/v1); the app then calls POST /v1/images/generations.
"""

from __future__ import annotations

import base64
import io
import re
import time

from .model_client import _configured

HOSTED_URL = "https://ai.api.nvidia.com/v1/cosmos/nvidia/cosmos3-nano"
HOSTED_STATUS_URL = "https://api.nvcf.nvidia.com/v2/nvcf/pexec/status/"
DEFAULT_IMAGE_MODEL = "nvidia/Cosmos3-Nano"
DEFAULT_IMAGE_SIZE = "1024x1024"
DEFAULT_RESOLUTION = "480_1_1"
IMAGE_TIMEOUT_SECONDS = 300.0
POLL_SECONDS = 2.0
MAX_PROMPT_CHARS = 1_000

_VERBS = r"(?:generate|create|make|draw|paint|design|render|produce|sketch|illustrate|imagine|show\s+me)"
_NOUNS = (
    r"(?:image|images|picture|pictures|photo|photos|photograph|illustration|artwork|drawing|painting|logo|"
    r"wallpaper|poster|portrait|avatar|icon|sketch|render)"
)
_IMAGE_REQUEST = re.compile(rf"\b{_VERBS}\b[^.?!\n]{{0,60}}?\b{_NOUNS}\b", re.IGNORECASE)
_DRAW_REQUEST = re.compile(r"^\s*(?:please\s+|can you\s+|could you\s+)?draw\b", re.IGNORECASE)
_QUESTION_START = re.compile(r"^\s*(?:how|what|why|where|when|which|who)\b", re.IGNORECASE)


class ImageGenerationError(RuntimeError):
    """Image generation failed; the message is safe to show to the user."""


def _hosted_key() -> str:
    return _configured("IMAGE_GEN_API_KEY") or _configured("NVIDIA_API_KEY") or _configured("LLM_API_KEY")


def image_generation_configured() -> bool:
    return bool(_configured("IMAGE_GEN_BASE_URL") or _hosted_key())


def wants_image(text: str) -> bool:
    """True when the message asks the assistant to create a picture (not a question about pictures)."""
    if not text or _QUESTION_START.match(text):
        return False
    return bool(_IMAGE_REQUEST.search(text) or _DRAW_REQUEST.match(text))


def _to_png(data: bytes) -> bytes:
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as image:
            image.load()
            out = io.BytesIO()
            image.convert("RGB").save(out, format="PNG")
        return out.getvalue()
    except Exception as exc:
        raise ImageGenerationError("The image service returned something that is not a picture.") from exc


def _http_error(status: int, body: str = "") -> ImageGenerationError:
    if status in (401, 403):
        return ImageGenerationError("NVIDIA rejected the API key for image creation. Check NVIDIA_API_KEY (or IMAGE_GEN_API_KEY).")
    if status == 404:
        return ImageGenerationError("This NVIDIA key can't use the Cosmos 3 Nano image endpoint yet. Open build.nvidia.com/nvidia/cosmos3-nano and make sure the key has access.")
    if status == 422:
        return ImageGenerationError("NVIDIA's safety screening refused that picture or the request was invalid. Try describing it differently.")
    if status == 429:
        return ImageGenerationError("The image service is busy right now. Please try again in a moment.")
    return ImageGenerationError(f"The image service couldn't create that picture (error {status}). Please try again.")


def _picture_from_json(payload: object) -> bytes:
    encoded = None
    if isinstance(payload, dict):
        encoded = payload.get("b64_image")
        if not encoded and isinstance(payload.get("data"), list) and payload["data"]:
            first = payload["data"][0]
            encoded = first.get("b64_json") or first.get("b64_image") if isinstance(first, dict) else None
    if not isinstance(encoded, str) or not encoded:
        raise ImageGenerationError("The image service sent back no picture.")
    if encoded.startswith("data:") and "," in encoded:
        encoded = encoded.split(",", 1)[1]
    try:
        return base64.b64decode(encoded, validate=False)
    except ValueError as exc:
        raise ImageGenerationError("The image service sent back a damaged picture.") from exc


def _generate_hosted(prompt: str, api_key: str) -> bytes:
    """NVIDIA's hosted Cosmos 3 Nano text2image call, following the 202 + status polling used by hosted NVIDIA functions."""
    try:
        import httpx
    except ImportError as exc:
        raise ImageGenerationError("The httpx package is missing. Install the project requirements.") from exc
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json", "Content-Type": "application/json"}
    body = {"model_mode": "text2image", "prompt": prompt, "resolution": _configured("IMAGE_GEN_RESOLUTION", DEFAULT_RESOLUTION)}
    deadline = time.monotonic() + IMAGE_TIMEOUT_SECONDS
    try:
        with httpx.Client(timeout=httpx.Timeout(60.0, read=IMAGE_TIMEOUT_SECONDS)) as client:
            response = client.post(_configured("IMAGE_GEN_URL", HOSTED_URL), headers=headers, json=body)
            request_id = response.headers.get("NVCF-REQID")
            while response.status_code == 202 and request_id:
                if time.monotonic() > deadline:
                    raise ImageGenerationError("Creating the image took too long. Please try again.")
                time.sleep(POLL_SECONDS)
                response = client.get(HOSTED_STATUS_URL + request_id, headers={"Authorization": headers["Authorization"], "Accept": "application/json"})
    except ImageGenerationError:
        raise
    except httpx.TimeoutException as exc:
        raise ImageGenerationError("Creating the image took too long. Please try again.") from exc
    except httpx.HTTPError as exc:
        raise ImageGenerationError("I couldn't reach the image service. Please try again later.") from exc
    if response.status_code != 200:
        raise _http_error(response.status_code)
    try:
        payload = response.json()
    except ValueError as exc:
        raise ImageGenerationError("The image service sent back something that is not a picture.") from exc
    return _picture_from_json(payload)


def generate_image(prompt: str) -> bytes:
    """Create one image from the prompt and return PNG bytes."""
    prompt = " ".join(prompt.split())[:MAX_PROMPT_CHARS]
    if not prompt:
        raise ImageGenerationError("Tell me what the image should show.")
    base_url = _configured("IMAGE_GEN_BASE_URL")
    if not base_url:
        api_key = _hosted_key()
        if not api_key:
            raise ImageGenerationError("Image creation is not set up yet. Add NVIDIA_API_KEY (or IMAGE_GEN_BASE_URL for your own server).")
        return _to_png(_generate_hosted(prompt, api_key))
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ImageGenerationError("The OpenAI SDK is missing. Install the project requirements.") from exc
    client = OpenAI(
        api_key=_configured("IMAGE_GEN_API_KEY", "EMPTY") or "EMPTY",
        base_url=base_url,
        max_retries=0,
        timeout=IMAGE_TIMEOUT_SECONDS,
    )
    try:
        response = client.images.generate(
            model=_configured("IMAGE_GEN_MODEL", DEFAULT_IMAGE_MODEL),
            prompt=prompt,
            size=_configured("IMAGE_GEN_SIZE", DEFAULT_IMAGE_SIZE),
            n=1,
            response_format="b64_json",
        )
    except Exception as exc:
        name = type(exc).__name__
        if name == "APITimeoutError":
            raise ImageGenerationError("Creating the image took too long. Please try again.") from exc
        if name in {"APIConnectionError"}:
            raise ImageGenerationError("I couldn't reach the image service. Please try again later.") from exc
        if name in {"AuthenticationError", "PermissionDeniedError"}:
            raise ImageGenerationError("The image service rejected the API key (IMAGE_GEN_API_KEY).") from exc
        raise ImageGenerationError("The image service couldn't create that picture. Try describing it differently.") from exc
    encoded = response.data[0].b64_json if response.data else None
    if not encoded:
        raise ImageGenerationError("The image service sent back no picture.")
    try:
        raw = base64.b64decode(encoded, validate=False)
    except ValueError as exc:
        raise ImageGenerationError("The image service sent back a damaged picture.") from exc
    return _to_png(raw)
