"""Steps 8-9: continuity summaries and the strict editor quality check."""

from __future__ import annotations

import logging
from typing import Any

from config import PASS_SCORE
from models.book_models import BookProject, ChapterPlan, ChapterSummary, QualityReport
from prompts.chapter_prompts import SUMMARY_PROMPT
from prompts.review_prompts import RECHECK_BLOCK, REVIEW_PROMPT
from services.nvidia_client import LLMClient
from utils.retry_utils import AIBookError, InvalidModelResponseError
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
        report: QualityReport = llm.generate_json(prompt, "review", validator=_validate_report)
    except AIBookError as exc:
        # A broken review must never lose the chapter, but it must never be hidden either.
        LOGGER.warning("Chapter %s review could not be completed: %s", chapter.chapter_number, type(exc).__name__)
        return QualityReport(
            passed=False,
            score=0,
            issues=[f"The automatic review could not be completed ({exc.user_message})"],
            corrections_required=["Use 'Review Chapter Again' or read the chapter manually."],
            editor_summary="Review unavailable.",
        )
    report.passed = bool(report.passed and report.score >= PASS_SCORE)
    return report


def summarize_chapter(llm: LLMClient, project: BookProject, chapter: ChapterPlan, content: str) -> ChapterSummary:
    """Create the structured continuity summary used by the following chapters."""
    plan = project.plan
    assert plan is not None
    prompt = render_template(
        SUMMARY_PROMPT,
        book_bible_json=compact_json(project.bible, 6000) if project.bible else "{}",
        chapter_number=chapter.chapter_number,
        chapter_title=chapter.title,
        chapter_content=content,
        language=plan.language,
    )
    summary: ChapterSummary = llm.generate_json(prompt, "summary", validator=ChapterSummary.model_validate)
    summary.chapter_number = chapter.chapter_number
    summary.chapter_title = chapter.title
    return summary
