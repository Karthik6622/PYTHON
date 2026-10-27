"""Application configuration: paths, UI option lists, model settings and secret lookup.

API keys are read from Streamlit secrets first and environment variables second.
Keys are never stored in source code and are never logged.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

APP_NAME = "AI Book Studio"
APP_ICON = "📚"
APP_TAGLINE = "Turn your idea into a professionally structured and illustrated book."

ROOT_DIR = Path(__file__).resolve().parent
PROJECTS_DIR = ROOT_DIR / "projects"
ASSETS_DIR = ROOT_DIR / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
PLACEHOLDERS_DIR = ASSETS_DIR / "placeholders"

# --------------------------------------------------------------------------------------
# NVIDIA NIM (text generation)
# --------------------------------------------------------------------------------------
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
NVIDIA_MODEL = "nvidia/nemotron-3.5-lightning-30b-a3b"
NVIDIA_TIMEOUT_SECONDS = 120.0

MIN_OUTPUT_TOKENS = 512
MAX_OUTPUT_TOKENS = 16384
DEFAULT_REASONING_BUDGET = 4096


@dataclass(frozen=True)
class SamplingPreset:
    """Sampling settings for one kind of model request."""

    name: str
    temperature: float
    top_p: float
    max_tokens: int  # 0 means "calculate from the target length"


PRESETS: dict[str, SamplingPreset] = {
    "planning": SamplingPreset("planning", 0.4, 0.9, 6000),
    "bible": SamplingPreset("bible", 0.3, 0.9, 6000),
    "chapter": SamplingPreset("chapter", 0.75, 0.95, 0),
    "revision": SamplingPreset("revision", 0.5, 0.9, 0),
    "front_matter": SamplingPreset("front_matter", 0.7, 0.95, 2500),
    "review": SamplingPreset("review", 0.2, 0.8, 2500),
    "summary": SamplingPreset("summary", 0.2, 0.8, 2500),
    "image_prompt": SamplingPreset("image_prompt", 0.5, 0.9, 1200),
}

# --------------------------------------------------------------------------------------
# Quality and retry rules
# --------------------------------------------------------------------------------------
PASS_SCORE = 80
MAX_REVISIONS = 2
MAX_API_RETRIES = 3
RETRY_DELAYS = (2.0, 5.0, 10.0)

# --------------------------------------------------------------------------------------
# UI option lists
# --------------------------------------------------------------------------------------
BOOK_TYPES = [
    "Fiction",
    "Fantasy",
    "Science Fiction",
    "Children's Book",
    "Educational",
    "Technology",
    "Business",
    "Self Help",
    "Biography",
    "History",
    "Mystery",
    "Adventure",
    "Romance",
    "Custom",
]
AUDIENCES = [
    "Children",
    "Teenagers",
    "Young Adults",
    "Adults",
    "Professionals",
    "Beginners",
    "Advanced Readers",
    "General Audience",
]
WRITING_STYLES = [
    "Storytelling",
    "Professional",
    "Educational",
    "Conversational",
    "Academic",
    "Simple and Friendly",
    "Creative",
    "Inspirational",
    "Technical",
    "Humorous",
]
LANGUAGES = ["English", "Tamil", "Hindi", "Spanish", "French", "German", "Japanese"]
ILLUSTRATION_FREQUENCIES = [
    "Cover only",
    "One image every chapter",
    "One image every two chapters",
    "Image-heavy book",
    "No images",
]
IMAGE_STYLES = [
    "Cinematic digital art",
    "Children's storybook illustration",
    "Photorealistic",
    "Watercolor painting",
    "Fantasy concept art",
    "Minimal flat illustration",
    "Comic-book style",
    "Educational infographic",
    "Professional editorial illustration",
]
CONTENT_OPTIONS: dict[str, str] = {
    "Include title page": "title_page",
    "Include copyright page": "copyright_page",
    "Include dedication": "dedication",
    "Include preface": "preface",
    "Include introduction": "introduction",
    "Include table of contents": "table_of_contents",
    "Include conclusion": "conclusion",
    "Include glossary": "glossary",
    "Include author page": "author_page",
}
DEFAULT_CONTENT_KEYS = [
    "title_page",
    "copyright_page",
    "introduction",
    "table_of_contents",
    "conclusion",
    "author_page",
]
FICTION_TYPES = {"Fiction", "Fantasy", "Science Fiction", "Mystery", "Adventure", "Romance"}

MIN_PAGES = 10
MAX_PAGES = 400
DEFAULT_PAGES = 50

# --------------------------------------------------------------------------------------
# Secrets
# --------------------------------------------------------------------------------------
_PLACEHOLDER_PREFIXES = ("your-", "your_", "$", "<", "changeme", "replace")


def _clean_secret(value: Any) -> str:
    """Return a usable secret or an empty string for blanks and example placeholders."""
    text = str(value or "").strip().strip("\"'").strip()
    if not text or text.lower().startswith(_PLACEHOLDER_PREFIXES):
        return ""
    return text


def get_secret(name: str, default: str = "") -> str:
    """Read a secret from ``st.secrets`` first, then from the environment."""
    try:
        import streamlit as st

        value = _clean_secret(st.secrets[name])
        if value:
            return value
    except Exception:  # noqa: BLE001 - missing secrets file or key is normal
        pass
    return _clean_secret(os.environ.get(name, "")) or default


def get_setting(name: str, default: str = "") -> str:
    """Read a non-secret setting from ``st.secrets`` or the environment."""
    try:
        import streamlit as st

        value = str(st.secrets[name]).strip()
        if value:
            return value
    except Exception:  # noqa: BLE001
        pass
    return os.environ.get(name, "").strip() or default


@dataclass(frozen=True)
class NvidiaSettings:
    """Connection settings for the NVIDIA NIM text-generation endpoint."""

    api_key: str
    base_url: str = NVIDIA_BASE_URL
    model: str = NVIDIA_MODEL
    timeout: float = NVIDIA_TIMEOUT_SECONDS
    enable_thinking: bool = False
    reasoning_budget: int = DEFAULT_REASONING_BUDGET

    @property
    def configured(self) -> bool:
        return bool(self.api_key)


def get_nvidia_settings() -> NvidiaSettings:
    """Build NVIDIA settings from secrets and environment variables."""
    thinking = get_setting("NVIDIA_ENABLE_THINKING", "false").lower() in {"1", "true", "yes", "on"}
    try:
        budget = int(get_setting("NVIDIA_REASONING_BUDGET", str(DEFAULT_REASONING_BUDGET)))
    except ValueError:
        budget = DEFAULT_REASONING_BUDGET
    return NvidiaSettings(
        api_key=get_secret("NVIDIA_API_KEY"),
        base_url=get_setting("NVIDIA_BASE_URL", NVIDIA_BASE_URL),
        model=get_setting("NVIDIA_MODEL", NVIDIA_MODEL),
        enable_thinking=thinking,
        reasoning_budget=max(512, min(budget, MAX_OUTPUT_TOKENS)),
    )


# --------------------------------------------------------------------------------------
# Image provider
# --------------------------------------------------------------------------------------
DEFAULT_IMAGE_API_URL = "https://api.openai.com/v1/images/generations"
DEFAULT_IMAGE_MODEL = "gpt-image-1"
DEFAULT_IMAGE_SIZES = {
    "portrait": "1024x1536",
    "landscape": "1536x1024",
    "square": "1024x1024",
}


@dataclass(frozen=True)
class ImageSettings:
    """Settings for the configurable, API-based image provider."""

    api_key: str
    api_url: str = DEFAULT_IMAGE_API_URL
    model: str = DEFAULT_IMAGE_MODEL
    provider: str = "auto"  # auto | api | placeholder
    response_format: str = ""
    timeout: float = 180.0
    sizes: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_IMAGE_SIZES))
    extra_body: dict[str, Any] = field(default_factory=dict)

    @property
    def use_api(self) -> bool:
        """True when the real image API should be called."""
        return self.provider != "placeholder" and bool(self.api_key)


def get_image_settings() -> ImageSettings:
    """Build image-provider settings from secrets and environment variables."""
    extra: dict[str, Any] = {}
    raw_extra = get_setting("IMAGE_API_EXTRA_JSON")
    if raw_extra:
        try:
            parsed = json.loads(raw_extra)
            if isinstance(parsed, dict):
                extra = parsed
        except ValueError:
            extra = {}
    sizes = dict(DEFAULT_IMAGE_SIZES)
    for orientation in sizes:
        override = get_setting(f"IMAGE_API_SIZE_{orientation.upper()}")
        if override:
            sizes[orientation] = override
    return ImageSettings(
        api_key=get_secret("IMAGE_API_KEY"),
        api_url=get_setting("IMAGE_API_URL", DEFAULT_IMAGE_API_URL),
        model=get_setting("IMAGE_API_MODEL", DEFAULT_IMAGE_MODEL),
        provider=get_setting("IMAGE_PROVIDER", "auto").lower(),
        response_format=get_setting("IMAGE_API_RESPONSE_FORMAT"),
        sizes=sizes,
        extra_body=extra,
    )
