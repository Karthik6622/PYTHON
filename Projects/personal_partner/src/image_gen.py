"""Image generation with NVIDIA Cosmos 3 Nano, served through an OpenAI-compatible images endpoint.

Cosmos3-Nano is a 16B model that needs an NVIDIA GPU (Ampere, Hopper or Blackwell) on Linux, so it cannot run inside
this app on an ordinary machine. Serve it once, for example with SGLang Diffusion:

    sglang serve --model-path nvidia/Cosmos3-Nano

then set IMAGE_GEN_BASE_URL (for example http://gpu-host:30000/v1). The app calls POST /v1/images/generations.
"""

from __future__ import annotations

import base64
import io
import re

from .model_client import _configured

DEFAULT_IMAGE_MODEL = "nvidia/Cosmos3-Nano"
DEFAULT_IMAGE_SIZE = "1024x1024"
IMAGE_TIMEOUT_SECONDS = 300.0
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


def image_generation_configured() -> bool:
    return bool(_configured("IMAGE_GEN_BASE_URL"))


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


def generate_image(prompt: str) -> bytes:
    """Create one image from the prompt and return PNG bytes."""
    base_url = _configured("IMAGE_GEN_BASE_URL")
    if not base_url:
        raise ImageGenerationError("Image creation is not set up yet. Set IMAGE_GEN_BASE_URL to a Cosmos 3 Nano server.")
    prompt = " ".join(prompt.split())[:MAX_PROMPT_CHARS]
    if not prompt:
        raise ImageGenerationError("Tell me what the image should show.")
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
