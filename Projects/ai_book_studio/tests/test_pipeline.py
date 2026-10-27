"""End-to-end smoke tests with a fake model and the placeholder image provider (no network)."""

from __future__ import annotations

import pytest
from docx import Document

from generators import ExportAssets
from models.book_models import BookProject
from services.book_pipeline import BookPipeline
from services.image_generator import PlaceholderImageGenerator
from utils.json_utils import extract_json_object
from utils.retry_utils import AIBookError, InvalidModelResponseError, call_with_retries, redact
from utils.text_utils import compute_budget, parse_blocks, split_inline

from conftest import FakeLLM


def _pipeline(storage, book_input, llm=None):
    project = storage.create_project(book_input)
    return BookPipeline(project, storage, llm=llm or FakeLLM(), image_generator=PlaceholderImageGenerator())


def test_plan_is_valid_and_saved(storage, book_input):
    pipeline = _pipeline(storage, book_input)
    plan = pipeline.create_plan()
    assert [c.chapter_number for c in plan.chapters] == [1, 2, 3]
    assert plan.author == "Test Author"
    reloaded = storage.load_project(pipeline.project.project_id)
    assert reloaded.plan and reloaded.plan.title == "The Lantern Keeper"
    assert reloaded.status.stage == "planned"


def test_full_book_exports_pdf_and_docx(storage, book_input):
    llm = FakeLLM()
    pipeline = _pipeline(storage, book_input, llm)
    pipeline.create_plan()
    seen: list[float] = []
    pipeline._progress = lambda fraction, message: seen.append(fraction)
    summary = pipeline.generate_complete_book()

    project = pipeline.project
    assert project.status.stage == "completed"
    assert all(project.chapter_done(n) for n in (1, 2, 3))
    assert project.reviews[1].revisions >= 1  # the first review failed and triggered a revision
    assert summary.pdf_path.read_bytes()[:5] == b"%PDF-"
    assert summary.pages > 5
    assert summary.docx_path.exists()
    headings = [p for p in Document(str(summary.docx_path)).paragraphs if p.style.name == "Heading 1"]
    assert len(headings) >= 3
    assert storage.image_file(project, "cover_final")
    assert all(storage.image_file(project, f"chapter_{n:02d}") for n in (1, 2, 3))
    assert seen == sorted(seen)

    reloaded = storage.load_project(project.project_id)
    assert set(reloaded.chapters) == {1, 2, 3}
    assert "dedication" in reloaded.front_matter


def test_failure_then_resume_does_not_repeat_finished_work(storage, book_input):
    llm = FakeLLM(fail_first_review=False, fail_on_chapter=2)
    pipeline = _pipeline(storage, book_input, llm)
    pipeline.create_plan()
    with pytest.raises(AIBookError):
        pipeline.generate_complete_book()
    assert pipeline.project.status.stage == "failed"
    assert pipeline.project.chapter_done(1) and not pipeline.project.chapters.get(2)

    resumed = BookPipeline(
        storage.load_project(pipeline.project.project_id), storage, llm=FakeLLM(fail_first_review=False), image_generator=PlaceholderImageGenerator()
    )
    resumed.generate_complete_book()
    assert resumed.project.status.stage == "completed"
    assert resumed.llm.chapter_requests == 2  # chapter 1 was not written again


def test_failed_chapter_is_fixed_on_continue_without_rewriting(storage, book_input):
    pipeline = _pipeline(storage, book_input, FakeLLM(fail_first_review=False))
    pipeline.create_plan()
    pipeline.generate_complete_book()
    project = pipeline.project
    original = project.chapters[2]
    project.reviews[2].passed = False
    project.reviews[2].score = 50
    project.reviews[2].issues = ["The ending is abrupt"]
    project.reviews[2].corrections_required = ["Add a closing scene"]

    llm = FakeLLM(fail_first_review=False)
    again = BookPipeline(project, storage, llm=llm, image_generator=PlaceholderImageGenerator())
    again.generate_complete_book()
    assert llm.chapter_requests == 0  # nothing was rewritten from scratch
    assert project.reviews[2].passed
    assert project.reviews[1].revisions == 0  # chapters that already passed were left alone
    assert llm.calls.count("revision") == 1  # only the failing chapter was revised
    assert project.chapters[2] != original


def test_missing_chapter_blocks_export(storage, book_input):
    pipeline = _pipeline(storage, book_input)
    pipeline.create_plan()
    with pytest.raises(AIBookError):
        pipeline.assemble_exports()


def test_no_images_still_makes_a_typographic_cover(storage, book_input):
    book_input.illustration_frequency = "No images"
    pipeline = _pipeline(storage, book_input)
    pipeline.create_plan()
    pipeline.generate_complete_book()
    assert storage.image_file(pipeline.project, "cover_final")
    assert not any(storage.image_file(pipeline.project, f"chapter_{n:02d}") for n in (1, 2, 3))


def test_helpers():
    assert extract_json_object('Here: ```json\n{"a": [1, {"b": 2}]}\n``` done') == {"a": [1, {"b": 2}]}
    with pytest.raises(AIBookError):
        extract_json_object("no json here")
    assert split_inline("a **b** *c*") == [("a ", False, False), ("b", True, False), (" ", False, False), ("c", False, True)]
    kinds = [b.kind for b in parse_blocks("# H\n\ntext\n\n- x\n\n1. y\n\n***")]
    assert kinds == ["h1", "p", "bullet", "number", "break"]
    assert "nvapi-" not in redact("key nvapi-abcdefghijklmnop123 and Bearer abcdefghijkl")
    assert compute_budget(__import__("models.book_models", fromlist=["BookInput"]).BookInput(pages=50)).target_words > 0


def test_retry_gives_up_after_three_retries():
    calls = []

    def always_bad():
        calls.append(1)
        raise InvalidModelResponseError("bad")

    with pytest.raises(InvalidModelResponseError):
        call_with_retries(always_bad, sleep=lambda _: None)
    assert len(calls) == 4
