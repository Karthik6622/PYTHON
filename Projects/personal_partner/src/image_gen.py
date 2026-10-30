"""Image generation for chat, using the same image providers as AI Book Studio.

Providers are tried in this order, and only the ones that are configured are used:

1. Cloudflare Workers AI FLUX.1 schnell (CLOUDFLARE_ACCOUNT_ID + CLOUDFLARE_API_TOKEN): fast, a few seconds per image.
2. AI Horde FLUX.1 schnell (AI_HORDE_API_KEY): free shared queue, slower; the backup when Cloudflare fails.
3. NVIDIA Cosmos 3 Nano: hosted API with IMAGE_GEN_API_KEY (or NVIDIA_API_KEY), or your own server through
   IMAGE_GEN_BASE_URL (for example `sglang serve --model-path nvidia/Cosmos3-Nano`).

The hosted Cosmos route is POST https://ai.api.nvidia.com/v1/cosmos/nvidia/cosmos3-nano with model_mode=text2image,
which returns a base64 JPEG in `b64_image`.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import re
import ssl
import time

from .model_client import _configured

LOGGER = logging.getLogger(__name__)

HOSTED_URL = "https://ai.api.nvidia.com/v1/cosmos/nvidia/cosmos3-nano"
CLOUDFLARE_MODEL = "@cf/black-forest-labs/flux-1-schnell"
HORDE_URL = "https://aihorde.net/api/v2"
HORDE_MODEL = "Flux.1-Schnell fp8 (Compact)"
HORDE_POLL_SECONDS = 3.0
MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024
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


def _cloudflare_ready() -> bool:
    return bool(_configured("CLOUDFLARE_ACCOUNT_ID") and _configured("CLOUDFLARE_API_TOKEN"))


def image_generation_configured() -> bool:
    return bool(_cloudflare_ready() or _configured("AI_HORDE_API_KEY") or _configured("IMAGE_GEN_BASE_URL") or _hosted_key())


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


def _server_detail(body: str) -> str:
    """The service's own explanation (never contains our key), shortened for display."""
    try:
        data = json.loads(body)
        text = str(data.get("detail") or data.get("title") or data.get("message") or data.get("error") or "") if isinstance(data, dict) else ""
    except ValueError:
        text = body
    text = " ".join(text.split())[:200]
    return f" NVIDIA says: {text}" if text else ""


def _http_error(status: int, body: str = "") -> ImageGenerationError:
    detail = _server_detail(body)
    if status in (401, 403):
        return ImageGenerationError("NVIDIA rejected the API key for image creation. Check NVIDIA_API_KEY (or IMAGE_GEN_API_KEY)." + detail)
    if status == 404:
        return ImageGenerationError(
            "NVIDIA doesn't give this API key access to the Cosmos 3 Nano image endpoint. Open build.nvidia.com/nvidia/cosmos3-nano, "
            "generate an API key there, and set it as IMAGE_GEN_API_KEY." + detail
        )
    if status == 422:
        return ImageGenerationError("NVIDIA's safety screening refused that picture or the request was invalid. Try describing it differently." + detail)
    if status == 429:
        return ImageGenerationError("The image service is busy right now. Please try again in a moment.")
    return ImageGenerationError(f"The image service couldn't create that picture (error {status}). Please try again." + detail)


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
        with httpx.Client(timeout=httpx.Timeout(60.0, read=IMAGE_TIMEOUT_SECONDS), verify=ssl.create_default_context()) as client:
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
        raise _http_error(response.status_code, response.text)
    try:
        payload = response.json()
    except ValueError as exc:
        raise ImageGenerationError("The image service sent back something that is not a picture.") from exc
    return _picture_from_json(payload)


def _http_client(timeout: float):
    import httpx

    return httpx.Client(timeout=httpx.Timeout(60.0, read=timeout), verify=ssl.create_default_context())


def _generate_cloudflare(prompt: str) -> bytes:
    """Cloudflare Workers AI FLUX.1 schnell (the AI Book Studio primary provider)."""
    import httpx

    url = f"https://api.cloudflare.com/client/v4/accounts/{_configured('CLOUDFLARE_ACCOUNT_ID')}/ai/run/{CLOUDFLARE_MODEL}"
    try:
        steps = max(1, min(8, int(_configured("CLOUDFLARE_STEPS", "6"))))
    except ValueError:
        steps = 6
    try:
        with _http_client(90) as client:
            response = client.post(
                url,
                headers={"Authorization": f"Bearer {_configured('CLOUDFLARE_API_TOKEN')}", "Content-Type": "application/json"},
                json={"prompt": prompt[:2048], "steps": steps},
            )
    except httpx.TimeoutException as exc:
        raise ImageGenerationError("Cloudflare took too long to draw the image.") from exc
    except httpx.HTTPError as exc:
        raise ImageGenerationError("I couldn't reach Cloudflare. Please try again later.") from exc
    if response.status_code in (401, 403):
        raise ImageGenerationError("Cloudflare rejected the credentials. Check CLOUDFLARE_API_TOKEN (needs Workers AI) and CLOUDFLARE_ACCOUNT_ID.")
    if response.status_code == 429:
        raise ImageGenerationError("Cloudflare's free image allowance is used up for now.")
    if response.status_code != 200:
        raise ImageGenerationError(f"Cloudflare couldn't create that picture (error {response.status_code}).")
    try:
        result = response.json().get("result")
        image = result.get("image") if isinstance(result, dict) else None
    except (ValueError, AttributeError):
        image = None
    if not isinstance(image, str) or not image:
        raise ImageGenerationError("Cloudflare sent back no picture.")
    try:
        return base64.b64decode(image.split(",", 1)[-1], validate=False)
    except ValueError as exc:
        raise ImageGenerationError("Cloudflare sent back a damaged picture.") from exc


def _horde_message(response) -> str:
    try:
        data = response.json()
        return " ".join(str(data.get("message", "")).split())[:200] if isinstance(data, dict) else ""
    except ValueError:
        return ""


def _generate_ai_horde(prompt: str) -> bytes:
    """AI Horde FLUX.1 schnell (the AI Book Studio backup provider): submit, poll, then download."""
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


def _cancel_horde(request_id: str, headers: dict) -> None:
    """Best effort: free the shared queue slot when we stop waiting."""
    if not request_id:
        return
    try:
        with _http_client(15) as client:
            client.delete(f"{HORDE_URL}/generate/status/{request_id}", headers=headers)
    except Exception:
        pass


def _generate_cosmos(prompt: str) -> bytes:
    """NVIDIA Cosmos 3 Nano: hosted API, or your own OpenAI-compatible server when IMAGE_GEN_BASE_URL is set."""
    base_url = _configured("IMAGE_GEN_BASE_URL")
    if not base_url:
        api_key = _hosted_key()
        if not api_key:
            raise ImageGenerationError("Image creation is not set up yet. Add CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN (or AI_HORDE_API_KEY) to this app.")
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


def _providers() -> list:
    """Configured providers in order. Cosmos only joins a chain when it is set up on purpose, or when it is the only option."""
    chain = []
    if _cloudflare_ready():
        chain.append(_generate_cloudflare)
    if _configured("AI_HORDE_API_KEY"):
        chain.append(_generate_ai_horde)
    if not chain or _configured("IMAGE_GEN_API_KEY") or _configured("IMAGE_GEN_BASE_URL"):
        chain.append(_generate_cosmos)
    return chain


def generate_image(prompt: str) -> bytes:
    """Create one image from the prompt and return PNG bytes. A failing provider hands over to the next one."""
    prompt = " ".join(prompt.split())[:MAX_PROMPT_CHARS]
    if not prompt:
        raise ImageGenerationError("Tell me what the image should show.")
    first_error: ImageGenerationError | None = None
    for provider in _providers():
        try:
            return _to_png(provider(prompt))
        except ImageGenerationError as exc:
            LOGGER.info("%s failed: %s", provider.__name__, exc)
            first_error = first_error or exc
    raise first_error or ImageGenerationError("Image creation is not set up yet.")
