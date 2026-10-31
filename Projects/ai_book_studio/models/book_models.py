"""Structured data models for AI Book Studio.

The models are deliberately lenient about what a language model returns (numbers as text,
lists as strings, missing keys) and strict about what the application needs.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from config import (
    DEFAULT_CONTENT_KEYS,
    DEFAULT_PAGES,
    MAX_PAGES,
    MIN_PAGES,
)


def utc_now() -> str:
    """Current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def to_int(value: Any, default: int = 0) -> int:
    """Convert numbers and numeric text such as ``"1,200 words"`` to an int."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        digits = re.sub(r"[^\d.]", "", value.replace(",", ""))
        try:
            return int(float(digits)) if digits else default
        except ValueError:
            return default
    return default


def to_text(value: Any) -> str:
    """Flatten any JSON value into readable text."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "; ".join(part for part in (to_text(item) for item in value) if part)
    if isinstance(value, dict):
        return "; ".join(f"{key}: {to_text(item)}" for key, item in value.items())
    return str(value).strip()


def to_text_list(value: Any) -> list[str]:
    """Convert a string, list or dict into a list of non-empty strings."""
    if value is None or value == "":
        return []
    if isinstance(value, str):
        return [part.strip() for part in re.split(r"[\n;]+|,\s+", value) if part.strip()]
    if isinstance(value, dict):
        value = [f"{key}: {to_text(item)}" for key, item in value.items()]
    if isinstance(value, (list, tuple)):
        return [text for text in (to_text(item) for item in value) if text]
    return [str(value)]


def to_bool(value: Any, default: bool = True) -> bool:
    """Convert common truthy and falsy values to bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "y", "1"}:
            return True
        if lowered in {"false", "no", "n", "0", ""}:
            return False
    return default


class _Model(BaseModel):
    """Base class: ignore unknown keys and strip whitespace."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


class _OpenModel(BaseModel):
    """Base class that keeps unknown keys (used for free-form bible entries)."""

    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)


# --------------------------------------------------------------------------------------
# Plan
# --------------------------------------------------------------------------------------
class CharacterProfile(_OpenModel):
    """A character in the story bible."""

    name: str = ""
    role: str = ""
    appearance: str = ""
    clothing: str = ""
    personality: str = ""
    motivation: str = ""
    relationships: str = ""

    @field_validator("*", mode="before")
    @classmethod
    def _flatten(cls, value: Any) -> Any:
        return to_text(value) if isinstance(value, (list, tuple, dict)) else value


class LocationProfile(_OpenModel):
    """A location in the story bible."""

    name: str = ""
    description: str = ""
    significance: str = ""

    @field_validator("*", mode="before")
    @classmethod
    def _flatten(cls, value: Any) -> Any:
        return to_text(value) if isinstance(value, (list, tuple, dict)) else value


class BookBible(_OpenModel):
    """Continuity bible. Fiction and nonfiction use different extra keys."""

    characters: list[CharacterProfile] = Field(default_factory=list)
    locations: list[LocationProfile] = Field(default_factory=list)

    @field_validator("characters", "locations", mode="before")
    @classmethod
    def _normalise_entries(cls, value: Any) -> Any:
        if value is None:
            return []
        if isinstance(value, dict):
            return [
                {"name": key, **item} if isinstance(item, dict) else {"name": key, "description": to_text(item)}
                for key, item in value.items()
            ]
        if isinstance(value, list):
            return [item if isinstance(item, dict) else {"name": to_text(item)} for item in value]
        return []


class ChapterPlan(_Model):
    """One planned chapter."""

    chapter_number: int = 1
    title: str = ""
    objective: str = ""
    summary: str = ""
    key_topics: list[str] = Field(default_factory=list)
    target_words: int = 0
    requires_image: bool = True
    image_concept: str = ""

    @field_validator("chapter_number", "target_words", mode="before")
    @classmethod
    def _ints(cls, value: Any) -> int:
        return to_int(value)

    @field_validator("title", "objective", "summary", "image_concept", mode="before")
    @classmethod
    def _texts(cls, value: Any) -> str:
        return to_text(value)

    @field_validator("key_topics", mode="before")
    @classmethod
    def _topics(cls, value: Any) -> list[str]:
        return to_text_list(value)

    @field_validator("requires_image", mode="before")
    @classmethod
    def _bool(cls, value: Any) -> bool:
        return to_bool(value)


class BookPlan(_Model):
    """The approved structure of the book."""

    title: str = ""
    subtitle: str = ""
    author: str = ""
    book_type: str = ""
    audience: str = ""
    language: str = ""
    writing_style: str = ""
    description: str = ""
    main_theme: str = ""
    tone: str = ""
    estimated_pages: int = 0
    estimated_words: int = 0
    visual_style: str = ""
    chapters: list[ChapterPlan] = Field(default_factory=list)

    @field_validator("estimated_pages", "estimated_words", mode="before")
    @classmethod
    def _ints(cls, value: Any) -> int:
        return to_int(value)

    @field_validator(
        "title",
        "subtitle",
        "author",
        "book_type",
        "audience",
        "language",
        "writing_style",
        "description",
        "main_theme",
        "tone",
        "visual_style",
        mode="before",
    )
    @classmethod
    def _texts(cls, value: Any) -> str:
        return to_text(value)

    @property
    def total_target_words(self) -> int:
        return sum(max(chapter.target_words, 0) for chapter in self.chapters)

    def chapter(self, number: int) -> ChapterPlan | None:
        """Return a chapter by number."""
        return next((item for item in self.chapters if item.chapter_number == number), None)


# --------------------------------------------------------------------------------------
# Chapter artefacts
# --------------------------------------------------------------------------------------
class ChapterSummary(_Model):
    """Continuity summary of a finished chapter."""

    chapter_number: int = 0
    chapter_title: str = ""
    important_events_or_points: list[str] = Field(default_factory=list)
    character_changes: list[str] = Field(default_factory=list)
    new_locations: list[str] = Field(default_factory=list)
    new_terms: list[str] = Field(default_factory=list)
    unresolved_items: list[str] = Field(default_factory=list)
    continuity_notes_for_next_chapter: list[str] = Field(default_factory=list)

    @field_validator("chapter_number", mode="before")
    @classmethod
    def _int(cls, value: Any) -> int:
        return to_int(value)

    @field_validator("chapter_title", mode="before")
    @classmethod
    def _text(cls, value: Any) -> str:
        return to_text(value)

    @field_validator(
        "important_events_or_points",
        "character_changes",
        "new_locations",
        "new_terms",
        "unresolved_items",
        "continuity_notes_for_next_chapter",
        mode="before",
    )
    @classmethod
    def _lists(cls, value: Any) -> list[str]:
        return to_text_list(value)


class QualityReport(_Model):
    """Editor's quality check of one chapter."""

    passed: bool = False
    score: int = 0
    issues: list[str] = Field(default_factory=list)
    corrections_required: list[str] = Field(default_factory=list)
    editor_summary: str = ""
    revisions: int = 0

    @field_validator("score", mode="before")
    @classmethod
    def _score(cls, value: Any) -> int:
        return max(0, min(100, to_int(value)))

    @field_validator("passed", mode="before")
    @classmethod
    def _passed(cls, value: Any) -> bool:
        return to_bool(value, default=False)

    @field_validator("issues", "corrections_required", mode="before")
    @classmethod
    def _lists(cls, value: Any) -> list[str]:
        return to_text_list(value)

    @field_validator("editor_summary", mode="before")
    @classmethod
    def _text(cls, value: Any) -> str:
        return to_text(value)


# --------------------------------------------------------------------------------------
# Images
# --------------------------------------------------------------------------------------
class IllustrationPlan(_Model):
    """Prompt, orientation and result of one image (cover or chapter)."""

    key: str = ""  # "cover" or "chapter_01"
    label: str = ""
    chapter_number: int | None = None
    prompt: str = ""
    orientation: str = "square"  # portrait | landscape | square
    filename: str = ""
    status: str = "pending"  # pending | generated | placeholder | failed
    warning: str = ""
    updated_at: str = ""


# --------------------------------------------------------------------------------------
# Input, status and project
# --------------------------------------------------------------------------------------
class BookInput(_Model):
    """Everything the user entered on the Create tab."""

    book_idea: str = ""
    preferred_title: str = ""
    author_name: str = ""
    author_bio: str = ""
    book_type: str = "Fiction"
    custom_book_type: str = ""
    audience: str = "General Audience"
    writing_style: str = "Storytelling"
    language: str = "English"
    pages: int = DEFAULT_PAGES
    illustration_frequency: str = "One image every chapter"
    image_style: str = "Cinematic digital art"
    content_options: list[str] = Field(default_factory=lambda: list(DEFAULT_CONTENT_KEYS))

    @field_validator("pages", mode="before")
    @classmethod
    def _pages(cls, value: Any) -> int:
        return max(MIN_PAGES, min(MAX_PAGES, to_int(value, DEFAULT_PAGES)))

    @property
    def effective_book_type(self) -> str:
        """The book type, using the custom text when "Custom" is selected."""
        if self.book_type == "Custom":
            return self.custom_book_type.strip() or "Custom"
        return self.book_type

    def has(self, option: str) -> bool:
        """True when a content option (for example ``"preface"``) is selected."""
        return option in self.content_options


class GenerationStatus(_Model):
    """Where the generation pipeline currently is."""

    stage: str = "new"  # new | planned | running | failed | completed
    message: str = ""
    progress: float = 0.0
    total_chapters: int = 0
    completed_chapters: list[int] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None
    updated_at: str = Field(default_factory=utc_now)


class BookProject(_Model):
    """A complete book project, including generated content."""

    project_id: str
    owner: str = ""  # private id of the browser that created the project; empty for projects made before owners existed
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)
    book_input: BookInput = Field(default_factory=BookInput)
    plan: BookPlan | None = None
    bible: BookBible | None = None
    front_matter: dict[str, str] = Field(default_factory=dict)
    chapters: dict[int, str] = Field(default_factory=dict)
    summaries: dict[int, ChapterSummary] = Field(default_factory=dict)
    reviews: dict[int, QualityReport] = Field(default_factory=dict)
    images: dict[str, IllustrationPlan] = Field(default_factory=dict)
    status: GenerationStatus = Field(default_factory=GenerationStatus)

    @property
    def title(self) -> str:
        if self.plan and self.plan.title:
            return self.plan.title
        return self.book_input.preferred_title or "Untitled book"

    @property
    def chapter_numbers(self) -> list[int]:
        return [chapter.chapter_number for chapter in self.plan.chapters] if self.plan else []

    def chapter_done(self, number: int) -> bool:
        """A chapter is complete when its text and continuity summary were both saved."""
        return bool(self.chapters.get(number, "").strip()) and number in self.summaries
