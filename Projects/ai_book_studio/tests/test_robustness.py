"""Unreadable model replies and non-English text must never stop a book or leave junk in it."""

from __future__ import annotations

from typing import Any

import pytest

import services.book_pipeline as book_pipeline
from conftest import FakeLLM
from models.book_models import ChapterPlan, QualityReport
from services.book_pipeline import BookPipeline
from services.chapter_reviewer import review_chapter, summarize_chapter
from services.image_generator import PlaceholderImageGenerator
from services.language_service import ensure_language
from services.nvidia_client import ChatResult
from utils.json_utils import extract_json_object, repair_truncated_json
from utils.language_utils import has_language_faults, has_leftover_english, sanitize_text
from utils.retry_utils import InvalidModelResponseError, TransientAPIError

TAMIL = "இது ஒரு நீண்ட தமிழ் வாக்கியம் ஆகும்."


# ---------------------------------------------------------------- JSON repair
def test_truncated_json_is_repaired() -> None:
    text = '{"important_events_or_points": ["ஒன்று", "இரண்டு"], "new_terms": ["abc", "de'
    data = extract_json_object(text)
    assert data["important_events_or_points"] == ["ஒன்று", "இரண்டு"]
    assert repair_truncated_json(text) is not None


def test_garbage_is_still_invalid() -> None:
    with pytest.raises(InvalidModelResponseError):
        extract_json_object("this is not json at all")


# ---------------------------------------------------------------- language cleaning
def test_sanitize_removes_junk_and_keeps_tamil() -> None:
    dirty = f"{TAMIL}\u200b \ufffd \u2063 இன்னொரு வரி\u00ad."
    cleaned = sanitize_text(dirty, "Tamil")
    assert "\ufffd" not in cleaned and "\u200b" not in cleaned and "\u00ad" not in cleaned
    assert "தமிழ்" in cleaned


def test_leftover_english_detected_only_for_native_script_languages() -> None:
    assert has_leftover_english(f"{TAMIL} This sentence is English.", "Tamil")
    assert not has_leftover_english("This sentence is English.", "English")


class _LanguageLLM(FakeLLM):
    def generate(self, prompt: str, preset: Any, max_tokens: int | None = None) -> ChatResult:
        name = preset if isinstance(preset, str) else preset.name
        if name == "language_fix":
            self.calls.append(name)
            return ChatResult(f"{TAMIL} {TAMIL}")
        return super().generate(prompt, preset, max_tokens)


def test_ensure_language_rewrites_english_paragraph() -> None:
    llm = _LanguageLLM()
    text = f"{TAMIL}\n\nThis paragraph is written in plain English and should be rewritten by the model.\n\n{TAMIL}"
    result = ensure_language(llm, text, "Tamil")
    assert "plain English" not in result
    assert "language_fix" in llm.calls


def test_ensure_language_leaves_english_books_alone() -> None:
    llm = _LanguageLLM()
    assert ensure_language(llm, "Plain English text.", "English").strip() == "Plain English text."
    assert "language_fix" not in llm.calls


def test_vietnamese_and_other_script_words_are_detected() -> None:
    assert has_language_faults(f"{TAMIL} thiết lập", "Tamil")
    assert has_language_faults(f"{TAMIL} अचानक", "Tamil")
    assert has_language_faults(f"{TAMIL} \ufee1\ufee5", "Tamil")
    assert not has_language_faults(TAMIL, "Tamil")


def test_foreign_script_paragraph_is_rewritten_not_just_cut() -> None:
    llm = _LanguageLLM()
    result = ensure_language(llm, f"{TAMIL} அचानक {TAMIL}", "Tamil")
    assert "language_fix" in llm.calls
    assert "\u0905" not in result and result.strip() == f"{TAMIL} {TAMIL}"


class _UselessFixLLM(_LanguageLLM):
    def generate(self, prompt: str, preset: Any, max_tokens: int | None = None) -> ChatResult:
        name = preset if isinstance(preset, str) else preset.name
        if name == "language_fix":
            self.calls.append(name)
            return ChatResult(f"{TAMIL} still English words here, plus thiết lập")
        return super().generate(prompt, preset, max_tokens)


def test_leftover_words_are_removed_when_the_model_cannot_fix_them() -> None:
    result = ensure_language(_UselessFixLLM(), f"{TAMIL} Chennai-\u0b87\u0bb2 subtle {TAMIL}", "Tamil")
    assert not has_language_faults(result, "Tamil")
    assert "\u0b87\u0bb2" in result  # the Tamil suffix is kept


def test_urls_and_inline_code_survive_the_last_resort() -> None:
    result = ensure_language(_UselessFixLLM(), f"{TAMIL} see https://example.com and `print(1)` also extra", "Tamil")
    assert "https://example.com" in result and "`print(1)`" in result and "extra" not in result


# ---------------------------------------------------------------- reviewer fallbacks
class _BrokenJSON(FakeLLM):
    def __init__(self, broken: set[str]) -> None:
        super().__init__(fail_first_review=False)
        self.broken = broken

    def generate_json(self, prompt: str, preset: Any, max_tokens: int | None = None, validator: Any = None) -> Any:
        name = preset if isinstance(preset, str) else preset.name
        if name in self.broken:
            raise InvalidModelResponseError("the model returned invalid JSON")
        return super().generate_json(prompt, preset, max_tokens, validator)


def _pipeline(storage: Any, book_input: Any, llm: FakeLLM) -> BookPipeline:
    project = storage.create_project(book_input)
    pipeline = BookPipeline(project, storage, llm=llm, image_generator=PlaceholderImageGenerator())
    pipeline.create_plan()
    return pipeline


def _project_with_chapter(storage: Any, book_input: Any) -> tuple[Any, ChapterPlan]:
    project = _pipeline(storage, book_input, FakeLLM()).project
    assert project.plan is not None
    return project, project.plan.chapters[0]


def test_unreadable_review_is_skipped_not_flagged(storage: Any, book_input: Any) -> None:
    project, chapter = _project_with_chapter(storage, book_input)
    report = review_chapter(_BrokenJSON({"review"}), project, chapter, "Some chapter text. " * 40)
    assert report.passed and report.skipped


def test_unreadable_summary_uses_text_fallback(storage: Any, book_input: Any) -> None:
    project, chapter = _project_with_chapter(storage, book_input)
    summary = summarize_chapter(_BrokenJSON({"summary"}), project, chapter, "First paragraph here.\n\nSecond one.\n\nThird.\n\nLast.")
    assert summary.chapter_number == chapter.chapter_number
    assert summary.important_events_or_points


# ---------------------------------------------------------------- pipeline behaviour
class _AlwaysFailingReview(FakeLLM):
    def generate_json(self, prompt: str, preset: Any, max_tokens: int | None = None, validator: Any = None) -> Any:
        name = preset if isinstance(preset, str) else preset.name
        if name == "review":
            self.calls.append(name)
            return validator({"passed": False, "score": 55, "issues": ["weak"], "editor_summary": "weak"})
        return super().generate_json(prompt, preset, max_tokens, validator)


def test_chapter_is_auto_accepted_after_revisions(storage: Any, book_input: Any) -> None:
    pipeline = _pipeline(storage, book_input, _AlwaysFailingReview())
    pipeline.process_chapter(1)
    report: QualityReport = pipeline.project.reviews[1]
    assert report.passed and report.auto_accepted
    assert report.score == 55 and report.revisions == book_pipeline.MAX_REVISIONS
    assert pipeline.project.chapter_done(1)


class _FlakyChapter(FakeLLM):
    def __init__(self) -> None:
        super().__init__(fail_first_review=False)
        self.failures = 0

    def generate(self, prompt: str, preset: Any, max_tokens: int | None = None) -> ChatResult:
        name = preset if isinstance(preset, str) else preset.name
        if name == "chapter" and self.failures < 2:
            self.failures += 1
            raise TransientAPIError("temporary")
        return super().generate(prompt, preset, max_tokens)


def test_temporary_failures_recover_without_user_action(storage: Any, book_input: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(book_pipeline, "AUTO_RECOVERY_PAUSE", 0)
    llm = _FlakyChapter()
    pipeline = _pipeline(storage, book_input, llm)
    pipeline._with_recovery(1, lambda: pipeline.process_chapter(1))
    assert llm.failures == 2
    assert pipeline.project.chapter_done(1)
