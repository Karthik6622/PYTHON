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
        tier = str(self.params["resolution"]).split("_")[0]
        return (
            f"{tier}p · {self.params['num_frames']} frames @ {self.params['fps']} fps "
            f"≈ {self.actual_seconds:.1f}s"
        )


def plan_video(
    ratio: str, quality: str, duration_seconds: int, adherence: str, seed: int = 0
) -> VideoPlan:
    """Map UI options to documented API parameters, clamping to schema limits."""
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


def api_key_required(url: str | None = None) -> bool:
    """NVIDIA-hosted endpoints need a key; a self-hosted NIM/server usually does not."""
    host = (urlparse(url or get_api_url()).hostname or "").lower()
    return host == "nvidia.com" or host.endswith(".nvidia.com")
