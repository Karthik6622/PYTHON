"""Central configuration for CineForge AI.

This module is the single place that defines:

* the NVIDIA Cosmos3-Nano endpoint and the **confirmed** request schema,
* every UI option list (content types, platforms, styles, ...),
* application limits and filesystem locations,
* secure API-key lookup (Streamlit secrets first, environment variable second).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

APP_NAME = "CineForge AI"
APP_TAGLINE = "Powered by NVIDIA Cosmos3-Nano"
APP_ICON = "🎬"

# --------------------------------------------------------------------------- #
# Provider selection                                                          #
# --------------------------------------------------------------------------- #
PROVIDER_SETTING_NAME = "VIDEO_PROVIDER"  # optional: "huggingface" (default), "nvidia" or "pictures"
PROVIDER_HUGGINGFACE = "huggingface"
PROVIDER_NVIDIA = "nvidia"
PROVIDER_PICTURES = "pictures"  # quota-free AI key-frames with camera motion (also the automatic fallback)

# --------------------------------------------------------------------------- #
# Free provider: LTX-Video on a Hugging Face Space (no API key required)      #
# --------------------------------------------------------------------------- #
HF_SPACE_ID = "Lightricks/ltx-video-distilled"
HF_SPACE_URL = "https://huggingface.co/spaces/Lightricks/ltx-video-distilled"
HF_API_NAME = "/text_to_video"
HF_TOKEN_SETTING_NAME = "HF_TOKEN"  # optional: a free token raises the daily GPU quota
HF_MIN_SECONDS = 0.3
HF_MAX_SECONDS = 8.5
HF_MIN_SIDE, HF_MAX_SIDE, HF_SIDE_STEP = 256, 1280, 32
HF_LONG_SIDE_BY_QUALITY: dict[str, int] = {"Draft": 512, "Standard": 704, "High quality": 960}
HF_EXPECTED_SECONDS_BY_QUALITY: dict[str, int] = {"Draft": 60, "Standard": 110, "High quality": 170}

# --------------------------------------------------------------------------- #
# Primary provider when BYTEZ_KEY is set: a Wan-AI text-to-video model on Bytez #
# --------------------------------------------------------------------------- #
BYTEZ_KEY_SETTING_NAME = "BYTEZ_KEY"
BYTEZ_MODEL_SETTING_NAME = "BYTEZ_MODEL"  # optional override of the model id
BYTEZ_DEFAULT_MODEL = "Wan-AI/Wan2.1-T2V-14B"
BYTEZ_API_BASE = "https://api.bytez.com/models/v2"
BYTEZ_EXPECTED_SECONDS = 240
BYTEZ_MAX_PROMPT_CHARS = 1500

# --------------------------------------------------------------------------- #
# Top provider when OPENROUTER_API_KEY is set: Google Veo 3.1 (video + audio)  #
# --------------------------------------------------------------------------- #
OPENROUTER_KEY_SETTING_NAME = "OPENROUTER_API_KEY"
OPENROUTER_MODEL_SETTING_NAME = "OPENROUTER_VIDEO_MODEL"  # e.g. google/veo-3.1-fast is ~3x cheaper
OPENROUTER_DEFAULT_MODEL = "google/veo-3.1"
OPENROUTER_API_BASE = "https://openrouter.ai/api/v1"
OPENROUTER_DURATIONS = (4, 6, 8)  # seconds Veo 3.1 can produce
OPENROUTER_POLL_SECONDS = 8
OPENROUTER_EXPECTED_SECONDS = 150
OPENROUTER_MAX_PROMPT_CHARS = 1800

# --------------------------------------------------------------------------- #
# AI Director: NVIDIA Nemotron models write the video prompt and voice-over    #
# --------------------------------------------------------------------------- #
LLM_API_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
LLM_TIMEOUT_SECONDS = 120
LLM_MODELS: dict[str, str] = {
    "Nemotron 3 Ultra 550B": "nvidia/nemotron-3-ultra-550b-a55b",
    "Nemotron 3.5 Super VL 120B": "nvidia/nemotron-3.5-super-vl-120b-a12b",
    "Nemotron 3.5 Lightning 30B": "nvidia/nemotron-3.5-lightning-30b-a3b",
}
DEFAULT_LLM_MODEL = "Nemotron 3 Ultra 550B"

# --------------------------------------------------------------------------- #
# Voice-over (Microsoft Edge neural voices via edge-tts) and YouTube export    #
# --------------------------------------------------------------------------- #
VOICES: dict[str, str] = {
    "Guy · US male": "en-US-GuyNeural",
    "Aria · US female": "en-US-AriaNeural",
    "Andrew · US male (warm)": "en-US-AndrewNeural",
    "Ryan · UK male": "en-GB-RyanNeural",
    "Sonia · UK female": "en-GB-SoniaNeural",
    "Prabhat · Indian English male": "en-IN-PrabhatNeural",
    "Neerja · Indian English female": "en-IN-NeerjaNeural",
}
DEFAULT_VOICE = "Guy · US male"
EXPORT_LONG_SIDE = 1920  # YouTube-ready Full HD export (long side, in pixels)

# --------------------------------------------------------------------------- #
# NVIDIA API                                                                  #
# --------------------------------------------------------------------------- #
DEFAULT_API_URL = "https://ai.api.nvidia.com/v1/cosmos/nvidia/cosmos3-nano"
API_URL_SETTING_NAME = "NVIDIA_API_URL"  # optional override (secrets or environment)
SELF_HOSTED_NIM_PATH = "/v1/infer"
API_MODEL_PAGE_URL = "https://build.nvidia.com/nvidia/cosmos3-nano"
API_KEY_SECRET_NAME = "NVIDIA_API_KEY"
API_KEY_PREFIX = "nvapi-"
REQUEST_TIMEOUT_SECONDS = 600
CONNECT_TIMEOUT_SECONDS = 15

# --------------------------------------------------------------------------- #
# SCHEMA-DEPENDENT SECTION                                                    #
# Cosmos3-Nano is a Preview API and its schema may change. Everything that    #
# depends on the request schema lives in this block. To adopt a newer schema, #
# copy the JSON body from NVIDIA's "View API Code" panel and update only the  #
# lines marked [SCHEMA].                                                      #
# --------------------------------------------------------------------------- #
MODEL_MODE_TEXT2VIDEO = "text2video"  # [SCHEMA] confirmed value of "model_mode"
RESPONSE_VIDEO_FIELD = "b64_video"  # [SCHEMA] confirmed response field

# [SCHEMA] Optional text2video fields documented on the model page (OpenAPI
# TextToVideoRequest). Anything not listed here is never sent.
SUPPORTED_OPTIONAL_PARAMS: frozenset[str] = frozenset(
    {"resolution", "num_frames", "fps", "seed", "num_inference_steps", "guidance_scale"}
)
# [SCHEMA] Limits from the schema: resolution tier -> maximum num_frames.
MIN_FRAMES = 25
MAX_FRAMES_BY_TIER: dict[str, int] = {"256": 397, "480": 297, "720": 197}
RESOLUTION_ASPECT_SUFFIX: dict[str, str] = {"16:9": "16_9", "9:16": "9_16", "1:1": "1_1"}
FPS_RANGE = (1, 60)
STEPS_RANGE = (1, 100)
GUIDANCE_RANGE = (1.0, 7.0)


def build_payload(
    prompt: str,
    negative_prompt: str = "",
    optional_params: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the JSON body for a text-to-video request.

    Only confirmed fields are sent. Optional parameters that are not listed in
    ``SUPPORTED_OPTIONAL_PARAMS`` are silently dropped.
    """
    payload: dict[str, Any] = {
        "model_mode": MODEL_MODE_TEXT2VIDEO,  # [SCHEMA]
        "prompt": prompt,  # [SCHEMA]
    }
    if negative_prompt.strip():
        payload["negative_prompt"] = negative_prompt.strip()  # [SCHEMA]
    for name, value in (optional_params or {}).items():
        if name in SUPPORTED_OPTIONAL_PARAMS and value is not None:
            payload[name] = value
    return payload


# Friendly UI choice -> documented API value.
TIER_BY_QUALITY: dict[str, str] = {"Draft": "256", "Standard": "480", "High quality": "720"}
STEPS_BY_QUALITY: dict[str, int] = {"Draft": 20, "Standard": 35, "High quality": 50}
GUIDANCE_BY_ADHERENCE: dict[str, float] = {"Flexible": 4.0, "Balanced": 6.0, "Strict": 7.0}
DEFAULT_FPS = 24


@dataclass(frozen=True)
class VideoPlan:
    """API parameters derived from UI choices, plus human-readable notes."""

    params: dict[str, Any]
    actual_seconds: float
    notes: tuple[str, ...]

    @property
    def summary(self) -> str:
        if "width" in self.params:
            return f"{self.params['width']}×{self.params['height']} · ≈ {self.actual_seconds:.1f}s"
        tier = str(self.params["resolution"]).split("_")[0]
        return (
            f"{tier}p · {self.params['num_frames']} frames @ {self.params['fps']} fps "
            f"≈ {self.actual_seconds:.1f}s"
        )


def plan_video(
    ratio: str, quality: str, duration_seconds: int, adherence: str, seed: int = 0
) -> VideoPlan:
    """Map UI options to documented API parameters, clamping to schema limits."""
    if get_provider() == PROVIDER_HUGGINGFACE:
        return plan_video_huggingface(ratio, quality, duration_seconds, seed)
    tier = TIER_BY_QUALITY.get(quality, "480")
    suffix = RESOLUTION_ASPECT_SUFFIX.get(ratio, "16_9")
    notes: list[str] = []
    if ratio not in RESOLUTION_ASPECT_SUFFIX:
        notes.append(f"{ratio} is not an API resolution option; 16:9 is used and {ratio} is prompt-only.")
    wanted = round(duration_seconds * DEFAULT_FPS)
    frames = max(MIN_FRAMES, min(wanted, MAX_FRAMES_BY_TIER[tier]))
    if frames < wanted:
        notes.append(
            f"{quality} quality allows at most {frames / DEFAULT_FPS:.1f}s; "
            "choose a lower quality tier for longer clips."
        )
    if frames > wanted:
        notes.append(f"The model's minimum is {MIN_FRAMES} frames (≈{MIN_FRAMES / DEFAULT_FPS:.1f}s).")
    params: dict[str, Any] = {
        "resolution": f"{tier}_{suffix}",
        "num_frames": frames,
        "fps": DEFAULT_FPS,
        "num_inference_steps": STEPS_BY_QUALITY.get(quality, 35),
        "guidance_scale": GUIDANCE_BY_ADHERENCE.get(adherence, 6.0),
    }
    if seed and seed > 0:
        params["seed"] = int(seed)
    return VideoPlan(params, frames / DEFAULT_FPS, tuple(notes))


def _snap_side(value: float) -> int:
    snapped = round(value / HF_SIDE_STEP) * HF_SIDE_STEP
    return int(max(HF_MIN_SIDE, min(snapped, HF_MAX_SIDE)))


def plan_video_huggingface(
    ratio: str, quality: str, duration_seconds: int, seed: int = 0
) -> VideoPlan:
    """Map UI options to the LTX-Video Space inputs (sides divisible by 32, <= 8.5 s)."""
    notes: list[str] = []
    try:
        ratio_w, ratio_h = (float(part) for part in ratio.split(":"))
    except ValueError:
        ratio_w, ratio_h = 16.0, 9.0
    long_side = HF_LONG_SIDE_BY_QUALITY.get(quality, 704)
    if ratio_w >= ratio_h:
        width, height = _snap_side(long_side), _snap_side(long_side * ratio_h / ratio_w)
    else:
        width, height = _snap_side(long_side * ratio_w / ratio_h), _snap_side(long_side)
    seconds = float(max(HF_MIN_SECONDS, min(duration_seconds, HF_MAX_SECONDS)))
    if seconds < duration_seconds:
        notes.append(
            f"The free model allows at most {HF_MAX_SECONDS:g}s per clip; use Storyboard mode for longer videos."
        )
    params: dict[str, Any] = {
        "width": width,
        "height": height,
        "duration": seconds,
        "improve_texture": quality != "Draft",
        "expected_seconds": HF_EXPECTED_SECONDS_BY_QUALITY.get(quality, 110),
    }
    if seed and seed > 0:
        params["seed"] = int(seed)
    return VideoPlan(params, seconds, tuple(notes))


# --------------------------------------------------------------------------- #
# Limits and paths                                                            #
# --------------------------------------------------------------------------- #
GENERATED_DIR = BASE_DIR / "temporary" / "generated_videos"
MAX_HISTORY_ITEMS = 20
MIN_PROMPT_CHARS = 15
MIN_PROMPT_WORDS = 3
MAX_PROMPT_CHARS = 1000
MAX_FINAL_PROMPT_CHARS = 2500
MAX_NEGATIVE_PROMPT_CHARS = 600
REQUEST_COOLDOWN_SECONDS = 3.0
MIN_SCENES = 2
MAX_SCENES = 6
DEFAULT_SCENES = 3

ALLOWED_AUDIO_EXTENSIONS = (".mp3", ".wav", ".m4a", ".aac")
MAX_AUDIO_BYTES = 20 * 1024 * 1024
MAX_VIDEO_BYTES = 200 * 1024 * 1024
CROSSFADE_SECONDS = 0.5

# --------------------------------------------------------------------------- #
# UI option lists                                                             #
# --------------------------------------------------------------------------- #
CONTENT_TYPES: dict[str, str] = {
    "YouTube Video": "a polished long-form YouTube video segment with clear storytelling",
    "YouTube Short": "a punchy vertical YouTube Short with an instantly engaging first second",
    "Cinematic Clip": "a cinematic film-style clip with deliberate, expressive framing",
    "Product Advertisement": "a premium product advertisement that showcases the subject attractively",
    "Educational Visual": "a clear educational visual that explains the subject without clutter",
    "Social Media Reel": "a high-energy social media reel with scroll-stopping visuals",
    "Gaming Scene": "an immersive game-style scene with dynamic atmosphere",
    "Nature/Travel Scene": "an immersive nature and travel scene with breathtaking scenery",
}


@dataclass(frozen=True)
class PlatformPreset:
    """Aspect-ratio preset used to shape prompt composition."""

    ratio: str
    orientation: str
    composition: str


PLATFORM_PRESETS: dict[str, PlatformPreset] = {
    "YouTube Landscape: 16:9": PlatformPreset(
        "16:9", "landscape", "wide landscape composition with the subject framed using the rule of thirds"
    ),
    "YouTube Shorts: 9:16": PlatformPreset(
        "9:16", "vertical", "vertical composition with the subject centered and kept inside the safe area"
    ),
    "Instagram Reels: 9:16": PlatformPreset(
        "9:16", "vertical", "vertical composition with the subject centered and room for captions"
    ),
    "TikTok: 9:16": PlatformPreset(
        "9:16", "vertical", "vertical composition with a bold central subject and tight framing"
    ),
    "Square Social Post: 1:1": PlatformPreset(
        "1:1", "square", "balanced square composition with a strongly centered subject"
    ),
    "Cinematic Widescreen: 21:9": PlatformPreset(
        "21:9", "ultra-wide", "ultra-wide anamorphic composition with generous horizontal negative space"
    ),
}

DURATION_OPTIONS: dict[str, int | None] = {
    "5 seconds": 5,
    "8 seconds": 8,
    "10 seconds": 10,
    "15 seconds": 15,
    "Custom": None,
}
CUSTOM_DURATION_MIN = 2
CUSTOM_DURATION_MAX = 16
DURATION_NOTICE = (
    "Duration is converted to a frame count at 24 fps. The model allows up to about 8 s at High "
    "quality, 12 s at Standard and 16 s at Draft; use Storyboard mode for longer videos."
)

VISUAL_STYLES: dict[str, str] = {
    "Cinematic realism": "cinematic realism with film-grade color grading",
    "Photorealistic": "photorealistic detail with natural textures",
    "Documentary": "authentic documentary look with natural color",
    "3D animation": "polished 3D animation with stylized yet coherent shapes",
    "Anime-inspired": "anime-inspired visuals with clean linework and expressive color",
    "Product commercial": "high-end commercial look with crisp highlights",
    "Futuristic sci-fi": "futuristic sci-fi aesthetic with sleek design language",
    "Fantasy": "rich fantasy atmosphere with painterly, magical detail",
    "Nature documentary": "nature documentary realism with vivid natural color",
    "Minimal corporate": "clean minimal corporate style with restrained palette",
}

CAMERA_MOVEMENTS: dict[str, str] = {
    "Static tripod": "locked-off static tripod shot",
    "Slow cinematic push-in": "slow cinematic push-in toward the subject",
    "Pull-out": "smooth pull-out revealing the surroundings",
    "Pan left": "steady pan to the left",
    "Pan right": "steady pan to the right",
    "Tracking shot": "smooth tracking shot that follows the subject from a low three-quarter angle",
    "Orbit shot": "slow orbit shot circling the subject",
    "Drone shot": "sweeping aerial drone shot",
    "Handheld documentary": "subtle handheld documentary camera with gentle natural movement",
    "Close-up with shallow depth of field": "intimate close-up with shallow depth of field",
}

LIGHTING_OPTIONS: dict[str, str] = {
    "Natural daylight": "natural daylight with soft realistic shadows",
    "Golden hour": "warm golden-hour light with long soft shadows",
    "Blue hour": "cool blue-hour twilight with a gentle glow",
    "Studio lighting": "controlled studio lighting with clean highlights",
    "Dramatic cinematic lighting": "dramatic cinematic lighting with strong contrast",
    "Neon lighting": "vivid neon lighting with colorful reflections",
    "Soft diffused lighting": "soft diffused lighting with even gentle shadows",
    "Low-key lighting": "moody low-key lighting with deep shadows",
}

QUALITY_OPTIONS: dict[str, str] = {
    "Draft": "clean, readable composition",
    "Standard": "detailed environment, sharp focus, well-balanced composition",
    "High quality": (
        "highly detailed environment, sharp focus, rich textures, "
        "polished high-quality composition"
    ),
}
QUALITY_NOTICE = (
    "Draft = 256p, Standard = 480p, High quality = 720p. Higher tiers add more "
    "inference steps and take longer."
)

MOTION_LEVELS: dict[str, str] = {
    "Subtle": "very gentle, subtle motion",
    "Balanced": "controlled natural motion",
    "Dynamic": "energetic but controlled motion",
}
CREATIVITY_LEVELS: dict[str, str] = {
    "Faithful": "stay faithful to the described scene without adding extra elements",
    "Balanced": "add tasteful supporting details that fit the scene",
    "Imaginative": "add imaginative, visually rich supporting details",
}
ADHERENCE_LEVELS: dict[str, str] = {
    "Flexible": "",
    "Balanced": "keep the main subject and action clearly recognizable",
    "Strict": "follow the described subject, action and setting precisely",
}

DEFAULT_NEGATIVE_PROMPT = (
    "blurry, flickering, jittery motion, distorted objects, duplicate objects, "
    "bad anatomy, warped faces, unreadable text, unwanted subtitles, logos, "
    "compression artifacts, low detail, abrupt camera movement, inconsistent lighting"
)

EXAMPLE_PROMPTS: tuple[str, ...] = (
    "A sports car driving through a city at night",
    "A lone astronaut walking across a red desert planet at sunrise",
    "A barista pouring latte art in a cozy coffee shop",
)

PRIVACY_NOTICE = (
    "Prompts and generated outputs are sent to NVIDIA and may be logged under "
    "NVIDIA's API trial terms. Do not submit confidential or personal data."
)
SYNTHID_NOTICE = (
    "Images and videos generated by Cosmos3 may contain SynthID watermarking."
)
HF_PRIVACY_NOTICE = (
    "Prompts are sent to a public Hugging Face Space (LTX-Video) and may be logged there. "
    "Do not submit confidential or personal data."
)
HF_QUALITY_NOTICE = (
    "Draft = 512 px, Standard = 704 px, High quality = 960 px on the long side. "
    "Draft skips the extra texture pass and is fastest."
)
HF_DURATION_NOTICE = (
    "The free LTX-Video model creates clips of up to 8.5 s at 24 fps; use Storyboard mode for longer videos."
)


# --------------------------------------------------------------------------- #
# Settings lookup (Streamlit secrets first, environment second)               #
# --------------------------------------------------------------------------- #
def _read_setting(name: str) -> str | None:
    try:
        import streamlit as st

        secret = st.secrets.get(name)
        if secret:
            return str(secret).strip() or None
    except Exception:  # secrets.toml missing or unreadable
        pass
    return os.getenv(name, "").strip() or None


def get_api_key() -> str | None:
    """Return the NVIDIA API key from Streamlit secrets or the environment.

    The key is read on demand and is never stored in session state or logged.
    """
    return _read_setting(API_KEY_SECRET_NAME)


def get_api_url() -> str:
    """Return the invocation URL (``NVIDIA_API_URL`` override or the default)."""
    return _read_setting(API_URL_SETTING_NAME) or DEFAULT_API_URL


def get_provider() -> str:
    """Return the active provider; the free Hugging Face Space unless NVIDIA is chosen."""
    value = (_read_setting(PROVIDER_SETTING_NAME) or "").lower()
    return PROVIDER_NVIDIA if value == PROVIDER_NVIDIA else PROVIDER_HUGGINGFACE


def get_openrouter_key() -> str | None:
    """Optional OpenRouter key; when set, Veo 3.1 is tried first. Never logged."""
    return _read_setting(OPENROUTER_KEY_SETTING_NAME)


def get_openrouter_model() -> str:
    return _read_setting(OPENROUTER_MODEL_SETTING_NAME) or OPENROUTER_DEFAULT_MODEL


def get_bytez_key() -> str | None:
    """Optional Bytez key; when set, Bytez is tried first. Never logged."""
    return _read_setting(BYTEZ_KEY_SETTING_NAME)


def get_bytez_model() -> str:
    return _read_setting(BYTEZ_MODEL_SETTING_NAME) or BYTEZ_DEFAULT_MODEL


def get_pollinations_key() -> str | None:
    """Optional free Pollinations key (removes the 1-image-per-45 s limit); never logged."""
    return _read_setting("POLLINATIONS_API_KEY")


def pictures_only() -> bool:
    """True when ``VIDEO_PROVIDER=pictures``: always use the quota-free image-based renderer."""
    return (_read_setting(PROVIDER_SETTING_NAME) or "").lower() == PROVIDER_PICTURES


def get_hf_token() -> str | None:
    """Optional Hugging Face token (raises the free GPU quota); never logged."""
    return _read_setting(HF_TOKEN_SETTING_NAME)


def app_tagline() -> str:
    if get_provider() == PROVIDER_HUGGINGFACE:
        if get_openrouter_key() and not pictures_only():
            return f"Powered by {get_openrouter_model().split('/')[-1].replace('-', ' ').title()} · OpenRouter"
        if get_bytez_key() and not pictures_only():
            return f"Powered by {get_bytez_model().split('/')[-1]} · Bytez"
        return "Powered by LTX-Video · free Hugging Face Space"
    return APP_TAGLINE


def privacy_notice() -> str:
    if get_provider() == PROVIDER_HUGGINGFACE and (get_openrouter_key() or get_bytez_key()) and not pictures_only():
        return (
            "Prompts are sent to OpenRouter/Google (and, if it is unavailable, to Bytez, a public Hugging Face "
            "Space or Pollinations) and may be logged there. Do not submit confidential or personal data."
        )
    return HF_PRIVACY_NOTICE if get_provider() == PROVIDER_HUGGINGFACE else PRIVACY_NOTICE


def synthid_notice() -> str:
    return "" if get_provider() == PROVIDER_HUGGINGFACE else SYNTHID_NOTICE


def quality_notice() -> str:
    return HF_QUALITY_NOTICE if get_provider() == PROVIDER_HUGGINGFACE else QUALITY_NOTICE


def duration_notice() -> str:
    return HF_DURATION_NOTICE if get_provider() == PROVIDER_HUGGINGFACE else DURATION_NOTICE


def api_key_required(url: str | None = None) -> bool:
    """NVIDIA-hosted endpoints need a key; a self-hosted NIM/server usually does not."""
    if url is None and get_provider() == PROVIDER_HUGGINGFACE:
        return False
    host = (urlparse(url or get_api_url()).hostname or "").lower()
    return host == "nvidia.com" or host.endswith(".nvidia.com")
