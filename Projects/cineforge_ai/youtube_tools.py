"""Local YouTube metadata generation from templates (no external API calls)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import config
import prompt_engine
from video_utils import safe_filename

_STOPWORDS = frozenset(
    "a an the and or of in on at to for with from by into over under through across "
    "is are was were be been being as it its this that these those very more most "
    "while during then than up down out about around near".split()
)
_SMALL_WORDS = frozenset("a an the and or of in on at to for with from by".split())
_MAX_TITLE_CHARS = 100
_MAX_TITLE_WORDS = 9

_HOOKS: dict[str, str] = {
    "YouTube Short": "Wait for it… {subject}",
    "Social Media Reel": "You won't believe this: {subject}",
    "Product Advertisement": "Meet the new standard: {subject}",
    "Educational Visual": "Here's something you can see in seconds: {subject}",
    "Gaming Scene": "Drop into this world: {subject}",
    "Nature/Travel Scene": "Imagine standing here: {subject}",
}
_DEFAULT_HOOK = "What if you could see this: {subject}"


@dataclass
class YouTubePackage:
    """Everything a creator needs to publish a generated clip."""

    title: str
    description: str
    alternative_titles: list[str] = field(default_factory=list)
    hashtags: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    thumbnail_prompt: str = ""
    hook: str = ""
    caption: str = ""
    filename: str = ""

    def to_dict(self) -> dict[str, object]:
        """Return a plain dict for session storage."""
        return {
            "title": self.title,
            "description": self.description,
            "alternative_titles": list(self.alternative_titles),
            "hashtags": list(self.hashtags),
            "tags": list(self.tags),
            "thumbnail_prompt": self.thumbnail_prompt,
            "hook": self.hook,
            "caption": self.caption,
            "filename": self.filename,
        }


def extract_keywords(text: str, limit: int = 10) -> list[str]:
    """Return unique, meaningful lowercase words in their original order."""
    seen: dict[str, None] = {}
    for word in re.findall(r"[A-Za-z][A-Za-z'\-]{2,}", text.lower()):
        if word not in _STOPWORDS:
            seen.setdefault(word, None)
    return list(seen)[:limit]


def _title_case(words: list[str]) -> str:
    result = []
    for index, word in enumerate(words):
        if index > 0 and word.lower() in _SMALL_WORDS:
            result.append(word.lower())
        else:
            result.append(word[:1].upper() + word[1:])
    return " ".join(result)


def suggest_title(prompt: str) -> str:
    """Build a concise title from the first words of the user's prompt."""
    cleaned = re.sub(r"[^A-Za-z0-9'\- ]+", " ", prompt_engine.sanitize_prompt(prompt))
    words = cleaned.split()[:_MAX_TITLE_WORDS]
    while words and words[-1].lower() in _SMALL_WORDS:
        words.pop()
    return _title_case(words) or "AI Generated Video"


def _clip(text: str, limit: int = _MAX_TITLE_CHARS) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def build_youtube_package(
    prompt: str, content_type: str, style: str, platform: str
) -> YouTubePackage:
    """Create title, description, hashtags, tags, hook and more from templates."""
    subject = prompt_engine.sanitize_prompt(prompt)
    title = _clip(suggest_title(subject))
    keywords = extract_keywords(subject)
    preset = config.PLATFORM_PRESETS.get(platform)
    ratio = preset.ratio if preset else "16:9"

    alternatives = [
        f"{title} | {style} AI Video",
        f"Watch: {title}",
        f"{title} (AI Generated {content_type})",
        f"AI Created: {title}",
        f"{title} – Cinematic AI Visuals",
    ]
    alternatives = [_clip(item) for item in alternatives]

    hashtags = ["#AIVideo", "#GenerativeAI", "#NVIDIACosmos"]
    if content_type == "YouTube Short" or ratio == "9:16":
        hashtags.append("#Shorts")
    hashtags += [f"#{word.replace('-', '').replace(chr(39), '')}" for word in keywords[:4]]
    hashtags.append("#" + re.sub(r"[^A-Za-z0-9]", "", style.title()))
    hashtags = list(dict.fromkeys(hashtags))[:10]

    tag_pool = ["AI video", "generative AI", "NVIDIA Cosmos", style.lower(), content_type.lower()]
    tag_pool += keywords
    tags: list[str] = []
    total = 0
    for tag in dict.fromkeys(tag_pool):
        if total + len(tag) + 1 > 450:
            break
        tags.append(tag)
        total += len(tag) + 1

    description = (
        f"{title}. A {style.lower()} {content_type.lower()} created with AI "
        "(NVIDIA Cosmos3-Nano). This video is synthetic and may contain SynthID watermarking. "
        "Subscribe for more AI-generated visuals."
    )
    thumbnail_prompt = (
        f"YouTube thumbnail, {subject.rstrip('.')}, bold focal subject, high contrast, "
        f"vibrant colors, {style.lower()} look, {ratio} composition with empty space for large "
        "headline text, dramatic lighting, no embedded text"
    )
    hook_template = _HOOKS.get(content_type, _DEFAULT_HOOK)
    lowered = subject.rstrip(".")
    hook = hook_template.format(subject=lowered[:1].lower() + lowered[1:])
    caption = _title_case(subject.split()[:6]) if subject else title

    return YouTubePackage(
        title=title,
        description=description,
        alternative_titles=alternatives,
        hashtags=hashtags,
        tags=tags,
        thumbnail_prompt=thumbnail_prompt,
        hook=hook,
        caption=caption,
        filename=safe_filename(title),
    )
