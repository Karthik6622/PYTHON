"""Test fixtures: a fake language model and an isolated project storage."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.book_models import BookInput  # noqa: E402
from services.nvidia_client import ChatResult  # noqa: E402
from services.project_storage import ProjectStorage  # noqa: E402

PLAN = {
    "title": "The Lantern Keeper",
    "subtitle": "A Tale of Light",
    "description": "A keeper of a coastal lantern protects a village.",
    "main_theme": "Courage",
    "tone": "Warm",
    "visual_style": "Watercolor",
    "chapters": [
        {
            "chapter_number": i,
            "title": f"Chapter title {i}",
            "objective": f"Objective {i}",
            "summary": f"Summary {i}",
            "key_topics": ["light", "sea"],
            "target_words": 200,
            "requires_image": True,
            "image_concept": "A lighthouse on a wide ocean horizon" if i == 1 else "A close-up portrait of the keeper",
        }
        for i in range(1, 4)
    ],
}

PARAGRAPH = "The wind rose over the **harbour** and the *lantern* swayed, and Mara counted the boats home. "


class FakeLLM:
    """Returns canned output per preset and records every call."""

    def __init__(self, fail_first_review: bool = True, fail_on_chapter: int | None = None) -> None:
        self.calls: list[str] = []
        self.fail_first_review = fail_first_review
        self.fail_on_chapter = fail_on_chapter
        self.chapter_requests = 0

    def generate(self, prompt: str, preset: Any, max_tokens: int | None = None) -> ChatResult:
        name = preset if isinstance(preset, str) else preset.name
        self.calls.append(name)
        if name == "chapter":
            self.chapter_requests += 1
            if self.fail_on_chapter and self.chapter_requests == self.fail_on_chapter:
                from utils.retry_utils import ModelRequestError

                raise ModelRequestError("simulated failure")
            body = "\n\n".join([PARAGRAPH * 6] * 3)
            return ChatResult(f"## A Heading\n\n{body}\n\n- first point\n- second point\n\n1. step one\n\n> A quote\n\n***\n\n{body}")
        if name == "revision":
            return ChatResult(f"## A Heading\n\n{PARAGRAPH * 20}")
        if name == "front_matter":
            return ChatResult(PARAGRAPH * 5)
        if name == "image_prompt":
            return ChatResult("A detailed watercolor scene of a lighthouse at dusk")
        raise AssertionError(f"unexpected text preset {name}")

    def generate_text(self, prompt: str, preset: Any, max_tokens: int | None = None) -> str:
        return self.generate(prompt, preset, max_tokens).text

    def generate_json(self, prompt: str, preset: Any, max_tokens: int | None = None, validator: Any = None) -> Any:
        name = preset if isinstance(preset, str) else preset.name
        self.calls.append(name)
        if name == "planning":
            data: dict[str, Any] = PLAN
        elif name == "bible":
            data = {"characters": [{"name": "Mara", "role": "Keeper"}], "locations": [{"name": "Harbour"}], "style_guide": "Warm"}
        elif name == "review":
            first = self.fail_first_review and self.calls.count("review") == 1
            data = {"passed": not first, "score": 60 if first else 92, "issues": ["too slow"] if first else [], "editor_summary": "ok"}
        elif name == "summary":
            data = {"important_events_or_points": ["Mara lights the lantern"], "new_terms": ["lantern"], "new_locations": []}
        else:
            raise AssertionError(f"unexpected json preset {name}")
        data = json.loads(json.dumps(data))
        return validator(data) if validator else data


@pytest.fixture()
def storage(tmp_path: Path) -> ProjectStorage:
    return ProjectStorage(tmp_path / "projects")


@pytest.fixture()
def book_input() -> BookInput:
    return BookInput(
        book_idea="A lighthouse keeper protects a small fishing village from a storm.",
        author_name="Test Author",
        pages=30,
        content_options=["title_page", "copyright_page", "dedication", "preface", "introduction", "table_of_contents", "conclusion", "glossary", "author_page"],
    )
