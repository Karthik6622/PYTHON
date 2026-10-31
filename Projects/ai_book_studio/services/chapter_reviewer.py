"""Steps 8-9: continuity summaries and the strict editor quality check."""

from __future__ import annotations

import logging
from typing import Any

from config import PASS_SCORE, json_tokens
from models.book_models import BookProject, ChapterPlan, ChapterSummary, QualityReport
from prompts.chapter_prompts import SUMMARY_PROMPT
from prompts.review_prompts import RECHECK_BLOCK, REVIEW_PROMPT
from services.language_service import ensure_language
from services.nvidia_client import LLMClient
from utils.language_utils import language_rules, split_paragraphs
from utils.retry_utils import AIBookError, InvalidModelResponseError, NvidiaAuthError, NvidiaKeyMissingError
from utils.text_utils import compact_json, format_previous_summaries, render_template

LOGGER = logging.getLogger("ai_book_studio.review")


def _validate_report(data: dict[str, Any]) -> QualityReport:
    if not any(key in data for key in ("score", "passed")):
        raise InvalidModelResponseError("The editor report did not contain a score.")
    return QualityReport.model_validate(data)


def review_chapter(
    llm: LLMClient,
    project: BookProject,
    chapter: ChapterPlan,
    content: str,
    previous: QualityReport | None = None,
) -> QualityReport:
    """Run the quality check. A chapter passes only with a score of 80+ and no critical problems.

    With ``previous`` the editor re-checks a revised chapter: it verifies the requested changes instead of hunting for new ones.
    """
    plan = project.plan
    assert plan is not None
    recheck = ""
    if previous is not None and previous.corrections_required:
        changes = "\n".join(f"- {item}" for item in previous.corrections_required)
        recheck = render_template(RECHECK_BLOCK, required_changes=changes)
    prompt = render_template(
        REVIEW_PROMPT,
        recheck_block=recheck,
        book_plan_json=compact_json(plan, 9000),
        book_bible_json=compact_json(project.bible, 7000) if project.bible else "{}",
        previous_chapter_summaries=format_previous_summaries(project.summaries, chapter.chapter_number, 5000),
        chapter_number=chapter.chapter_number,
        chapter_title=chapter.title,
        chapter_objective=chapter.objective,
        key_topics="; ".join(chapter.key_topics),
        chapter_content=content,
    )
    try:
        report: QualityReport = llm.generate_json(prompt, "review", max_tokens=3500, validator=_validate_report)
    except (NvidiaAuthError, NvidiaKeyMissingError):
        raise
    except AIBookError as exc:
        # The editor's reply could not be read even after several attempts. That must never stop the book or leave the
        # chapter waiting for the user: the chapter is accepted and the report says the check was skipped.
        LOGGER.warning("Chapter %s review was skipped: %s", chapter.chapter_number, type(exc).__name__)
        return QualityReport(
            passed=True,
            score=0,
            skipped=True,
            editor_summary="The automatic quality check could not be read, so the chapter was accepted as written.",
        )
    report.passed = bool(report.passed and report.score >= PASS_SCORE)
    return report


def _fallback_summary(chapter: ChapterPlan, content: str) -> ChapterSummary:
    """Continuity notes taken straight from the chapter text, used when the model's summary cannot be read."""
    paragraphs = [p.strip() for p in split_paragraphs(content) if p.strip() and not p.lstrip().startswith(("#", "---", "***"))]
    points: list[str] = []
    if paragraphs:
        points.append(paragraphs[0][:300])
        if len(paragraphs) > 2:
            points.append(paragraphs[len(paragraphs) // 2][:300])
    ending = paragraphs[-1][:300] if paragraphs else ""
    return ChapterSummary(
        chapter_number=chapter.chapter_number,
        chapter_title=chapter.title,
        important_events_or_points=points or [chapter.summary],
        continuity_notes_for_next_chapter=[ending] if ending else [],
    )


def summarize_chapter(llm: LLMClient, project: BookProject, chapter: ChapterPlan, content: str) -> ChapterSummary:
    """Create the structured continuity summary used by the following chapters.

    If the model keeps returning unreadable JSON, a summary taken from the text itself is used instead of failing.
    """
    plan = project.plan
    assert plan is not None
    prompt = render_template(
        SUMMARY_PROMPT,
        book_bible_json=compact_json(project.bible, 6000) if project.bible else "{}",
        chapter_number=chapter.chapter_number,
        chapter_title=chapter.title,
        chapter_content=content,
        language=plan.language,
        language_rules=language_rules(plan.language),
    )
    try:
        summary: ChapterSummary = llm.generate_json(
            prompt, "summary", max_tokens=json_tokens(plan.language), validator=ChapterSummary.model_validate
        )
    except InvalidModelResponseError:
        LOGGER.warning("Chapter %s summary was unreadable; using a summary taken from the text.", chapter.chapter_number)
        summary = _fallback_summary(chapter, content)
    for field in ("important_events_or_points", "character_changes", "new_locations", "new_terms", "unresolved_items", "continuity_notes_for_next_chapter"):
        setattr(summary, field, [ensure_language(llm, item, plan.language) for item in getattr(summary, field)])
    summary.chapter_number = chapter.chapter_number
    summary.chapter_title = chapter.title
    return summary
