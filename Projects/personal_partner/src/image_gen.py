"""Image generation for chat, using AI Horde only (the same FLUX.1 schnell setup as AI Book Studio).

Set AI_HORDE_API_KEY. Optional: AI_HORDE_MODEL (comma separated, default FLUX.1 schnell) and AI_HORDE_TIMEOUT (seconds to
wait in the shared queue, default 300). The flow is: submit, poll the queue, then download the finished picture.
"""

from __future__ import annotations

import base64
import io
import re
import ssl
import time

from .model_client import _configured

HORDE_URL = "https://aihorde.net/api/v2"
HORDE_MODEL = "Flux.1-Schnell fp8 (Compact)"
HORDE_POLL_SECONDS = 3.0
MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024
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
    return bool(_configured("AI_HORDE_API_KEY"))


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
        raise ImageGenerationError("AI Horde returned something that is not a picture.") from exc


def _http_client(timeout: float):
    import httpx

    return httpx.Client(timeout=httpx.Timeout(60.0, read=timeout), verify=ssl.create_default_context())


def _horde_message(response) -> str:
    try:
        data = response.json()
        return " ".join(str(data.get("message", "")).split())[:200] if isinstance(data, dict) else ""
    except ValueError:
        return ""


def _cancel_horde(request_id: str, headers: dict) -> None:
    """Best effort: free the shared queue slot when we stop waiting."""
    if not request_id:
        return
    try:
        with _http_client(15) as client:
            client.delete(f"{HORDE_URL}/generate/status/{request_id}", headers=headers)
    except Exception:
        pass


def _generate_ai_horde(prompt: str) -> bytes:
    """AI Horde FLUX.1 schnell: submit, poll, then download."""
    import httpx

    headers = {"apikey": _configured("AI_HORDE_API_KEY"), "Client-Agent": "WithYou:1.0", "Content-Type": "application/json"}
    models = [name.strip() for name in _configured("AI_HORDE_MODEL", HORDE_MODEL).split(",") if name.strip()] or [HORDE_MODEL]
    flux = all("flux" in name.lower() for name in models)
    params: dict = {"width": 640, "height": 640, "steps": 4 if flux else 16, "n": 1}
    if flux:
        params.update({"cfg_scale": 1, "sampler_name": "k_euler"})
    payload = {"prompt": prompt[:1000], "params": params, "models": models, "nsfw": False, "censor_nsfw": True, "slow_workers": True}
    try:
        timeout = float(_configured("AI_HORDE_TIMEOUT", "300"))
    except ValueError:
        timeout = 300.0

    def call(client, method: str, path: str, **kwargs):
        response = client.request(method, HORDE_URL + path, headers=headers, **kwargs)
        detail = _horde_message(response)
        if response.status_code in (401, 403):
            if "kudos" in detail.lower():
                raise ImageGenerationError("AI Horde wants kudos for this picture. Please try again later.")
            raise ImageGenerationError("AI Horde rejected the key. Check AI_HORDE_API_KEY.")
        if response.status_code in (429, 500, 502, 503, 504):
            raise ImageGenerationError("AI Horde is busy right now. Please try again in a moment.")
        if not response.is_success:
            raise ImageGenerationError(f"AI Horde couldn't create that picture (error {response.status_code}). {detail}".strip())
        try:
            data = response.json()
        except ValueError as exc:
            raise ImageGenerationError("AI Horde sent back something unexpected.") from exc
        return data if isinstance(data, dict) else {}

    request_id = ""
    try:
        with _http_client(60) as client:
            request_id = str(call(client, "POST", "/generate/async", json=payload).get("id") or "")
            if not request_id:
                raise ImageGenerationError("AI Horde did not accept the request.")
            deadline = time.monotonic() + timeout
            while True:
                status = call(client, "GET", f"/generate/check/{request_id}")
                if status.get("faulted"):
                    raise ImageGenerationError("AI Horde could not draw this picture.")
                if status.get("done"):
                    break
                if status.get("is_possible") is False:
                    raise ImageGenerationError("No AI Horde worker is available for this right now.")
                if time.monotonic() >= deadline:
                    raise ImageGenerationError("AI Horde's shared queue is busy, so the picture took too long.")
                time.sleep(HORDE_POLL_SECONDS)
            generations = call(client, "GET", f"/generate/status/{request_id}").get("generations")
            first = generations[0] if isinstance(generations, list) and generations and isinstance(generations[0], dict) else {}
            if first.get("censored"):
                raise ImageGenerationError("AI Horde's safety filter blocked that picture. Try describing it differently.")
            image = first.get("img")
            if not isinstance(image, str) or not image:
                raise ImageGenerationError("AI Horde sent back no picture.")
            if image.startswith("https://"):
                download = client.get(image)
                if not download.is_success or len(download.content) > MAX_DOWNLOAD_BYTES:
                    raise ImageGenerationError("The picture from AI Horde could not be downloaded.")
                return download.content
            try:
                return base64.b64decode(image.split(",", 1)[-1], validate=False)
            except ValueError as exc:
                raise ImageGenerationError("AI Horde sent back a damaged picture.") from exc
    except ImageGenerationError:
        _cancel_horde(request_id, headers)
        raise
    except httpx.TimeoutException as exc:
        _cancel_horde(request_id, headers)
        raise ImageGenerationError("AI Horde took too long. Please try again.") from exc
    except httpx.HTTPError as exc:
        raise ImageGenerationError("I couldn't reach AI Horde. Please try again later.") from exc


def generate_image(prompt: str) -> bytes:
    """Create one image from the prompt with AI Horde and return PNG bytes."""
    prompt = " ".join(prompt.split())[:MAX_PROMPT_CHARS]
    if not prompt:
        raise ImageGenerationError("Tell me what the image should show.")
    if not image_generation_configured():
        raise ImageGenerationError("Image creation is not set up yet. Add AI_HORDE_API_KEY to this app.")
    return _to_png(_generate_ai_horde(prompt))
