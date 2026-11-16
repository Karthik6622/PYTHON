"""Local prompt sanitization and enhancement (no external AI service needed)."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

import config

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WHITESPACE = re.compile(r"\s+")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

_STORY_BEATS = (
    "the opening establishing view of the setting",
    "the main subject is introduced",
    "the action develops",
    "tension and excitement build",
    "the key moment arrives",
    "a calm, resolving final shot",
)


@dataclass
class GenerationSettings:
    """User-selected options that shape the prompt (and are stored in history)."""

    content_type: str = "YouTube Video"
    platform: str = "YouTube Landscape: 16:9"
    duration_seconds: int = 8
    style: str = "Cinematic realism"
    camera: str = "Slow cinematic push-in"
    lighting: str = "Dramatic cinematic lighting"
    quality: str = "Standard"
    motion: str = "Balanced"
    creativity: str = "Balanced"
    adherence: str = "Balanced"
    keep_original: bool = True
    seed: int = 0
    def to_dict(self) -> dict[str, object]:
        """Return a plain dict suitable for session storage."""
        return asdict(self)


def sanitize_prompt(text: str, max_chars: int = config.MAX_PROMPT_CHARS) -> str:
    """Strip control characters, collapse whitespace and enforce a length cap."""
    cleaned = _CONTROL_CHARS.sub("", text or "")
    cleaned = _WHITESPACE.sub(" ", cleaned).strip()
    return cleaned[:max_chars].rstrip()


def validate_prompt(text: str) -> list[str]:
    """Return human-readable validation problems (empty list when valid)."""
    cleaned = sanitize_prompt(text, max_chars=config.MAX_PROMPT_CHARS * 4)
    problems: list[str] = []
    if len(cleaned) < config.MIN_PROMPT_CHARS or len(cleaned.split()) < config.MIN_PROMPT_WORDS:
        problems.append(
            f"Describe your video in at least {config.MIN_PROMPT_WORDS} words "
            f"({config.MIN_PROMPT_CHARS}+ characters)."
        )
    if len(cleaned) > config.MAX_PROMPT_CHARS:
        problems.append(f"The prompt is longer than {config.MAX_PROMPT_CHARS} characters.")
    return problems


def _as_sentence(text: str) -> str:
    text = text.strip()
    if text and text[-1] not in ".!?":
        text += "."
    return text


def _trim_to_limit(text: str, limit: int = config.MAX_FINAL_PROMPT_CHARS) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit]
    boundary = max(cut.rfind(". "), cut.rfind("."))
    return cut[: boundary + 1] if boundary > limit // 2 else cut.rstrip()


def _focus_sentence(settings: GenerationSettings) -> str:
    if "shallow depth" in settings.camera.lower() or "close-up" in settings.camera.lower():
        return "Razor-thin focus on the subject with softly blurred background."
    return "Clear subject separation with natural depth of field and crisp focus."


def _motion_sentence(settings: GenerationSettings) -> str:
    motion = config.MOTION_LEVELS.get(settings.motion, config.MOTION_LEVELS["Balanced"])
    return (
        f"{motion.capitalize()}, consistent object geometry, "
        "stable temporal coherence and smooth frame-to-frame continuity."
    )


def _camera_sentence(settings: GenerationSettings) -> str:
    phrase = config.CAMERA_MOVEMENTS.get(settings.camera, settings.camera)
    return f"Camera: {phrase}."


def enhance_prompt(user_prompt: str, settings: GenerationSettings) -> str:
    """Turn a short idea into a detailed, model-friendly video prompt."""
    subject = sanitize_prompt(user_prompt)
    if not subject:
        return ""
    if not settings.keep_original:
        subject = subject[0].upper() + subject[1:]
    preset = config.PLATFORM_PRESETS.get(
        settings.platform, next(iter(config.PLATFORM_PRESETS.values()))
    )

    sentences = [
        _as_sentence(subject),
        _as_sentence(
            "Created as "
            + config.CONTENT_TYPES.get(settings.content_type, settings.content_type)
        ),
        _camera_sentence(settings),
        _as_sentence(
            "Lighting: "
            + config.LIGHTING_OPTIONS.get(settings.lighting, settings.lighting)
        ),
        _as_sentence(
            "Visual style: " + config.VISUAL_STYLES.get(settings.style, settings.style)
        ),
        _focus_sentence(settings),
        _motion_sentence(settings),
    ]
    creativity = config.CREATIVITY_LEVELS.get(settings.creativity, "")
    adherence = config.ADHERENCE_LEVELS.get(settings.adherence, "")
    for extra in (creativity, adherence):
        if extra:
            sentences.append(_as_sentence(extra.capitalize()))
    sentences.append(
        _as_sentence(
            config.QUALITY_OPTIONS.get(settings.quality, "").capitalize()
            or "Well-balanced composition"
        )
    )
    sentences.append(
        _as_sentence(
            f"Composed for {preset.ratio} {preset.orientation} delivery with {preset.composition}, "
            f"clear subject framing, pacing suited to a roughly {settings.duration_seconds}-second "
            "clip, and a polished look suitable for publishing online"
        )
    )
    return _trim_to_limit(" ".join(sentences))


def build_style_prefix(settings: GenerationSettings) -> str:
    """Return the shared style prefix that keeps storyboard scenes visually aligned."""
    preset = config.PLATFORM_PRESETS.get(
        settings.platform, next(iter(config.PLATFORM_PRESETS.values()))
    )
    return (
        f"Consistent visual style across all scenes: "
        f"{config.VISUAL_STYLES.get(settings.style, settings.style)}; "
        f"{config.LIGHTING_OPTIONS.get(settings.lighting, settings.lighting)}; "
        f"{config.QUALITY_OPTIONS.get(settings.quality, '')}; "
        f"{preset.ratio} {preset.orientation} framing."
    )


def build_scene_prompt(prefix: str, scene_text: str, settings: GenerationSettings) -> str:
    """Combine the shared prefix with one scene's description and camera/motion cues."""
    scene = sanitize_prompt(scene_text)
    if not scene:
        return ""
    parts = [
        prefix.strip(),
        _as_sentence(scene),
        _camera_sentence(settings),
        _focus_sentence(settings),
        _motion_sentence(settings),
    ]
    return _trim_to_limit(" ".join(part for part in parts if part))


def build_scene_texts(story: str, scene_count: int) -> list[str]:
    """Split a story/concept into ``scene_count`` editable scene descriptions."""
    story = sanitize_prompt(story)
    if not story:
        return []
    sentences = [s for s in _SENTENCE_SPLIT.split(story) if s.strip()]

    if len(sentences) >= scene_count:
        base, remainder = divmod(len(sentences), scene_count)
        scenes: list[str] = []
        cursor = 0
        for index in range(scene_count):
            size = base + (1 if index < remainder else 0)
            scenes.append(" ".join(sentences[cursor : cursor + size]))
            cursor += size
        return scenes

    last = len(_STORY_BEATS) - 1
    scenes = []
    for index in range(scene_count):
        beat_index = round(index * last / (scene_count - 1)) if scene_count > 1 else 0
        scenes.append(f"{_as_sentence(story)} Focus on {_STORY_BEATS[beat_index]}.")
    return scenes
