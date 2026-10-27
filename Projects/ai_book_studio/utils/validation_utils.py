"""Input validation, content screening, plan validation and export readiness checks."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from config import MAX_PAGES, MIN_PAGES
from models.book_models import BookInput, BookPlan, BookProject
from utils.retry_utils import ContentPolicyError

if TYPE_CHECKING:
    from services.project_storage import ProjectStorage


@dataclass
class ValidationReport:
    """Errors block an action; warnings are shown but do not block."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


# --------------------------------------------------------------------------------------
# Book input
# --------------------------------------------------------------------------------------
def validate_book_input(book_input: BookInput) -> list[str]:
    """Return user-facing problems with the Create tab form."""
    problems: list[str] = []
    idea = book_input.book_idea.strip()
    if not idea:
        problems.append("Please enter a book idea.")
    elif len(idea) < 20:
        problems.append("Please describe your book idea in a little more detail (at least 20 characters).")
    elif len(idea) > 6000:
        problems.append("The book idea is too long. Please keep it under 6,000 characters.")
    if not book_input.author_name.strip():
        problems.append("Please enter the author name.")
    if book_input.book_type == "Custom" and not book_input.custom_book_type.strip():
        problems.append("Please enter your custom book type.")
    if not MIN_PAGES <= book_input.pages <= MAX_PAGES:
        problems.append(f"Number of pages must be between {MIN_PAGES} and {MAX_PAGES}.")
    return problems


_BLOCKED: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"(?i)\b(erotic|porn\w*|nsfw|sex scenes?|sexually explicit|explicit sex)\b"),
        "Sexual content is not supported.",
    ),
    (
        re.compile(r"(?i)\b(child|minor|kid|underage|teen)\w*\b.{0,60}\b(sexual|erotic|nude|naked)\b"),
        "Content that sexualises minors is never supported.",
    ),
    (
        re.compile(r"(?i)\b(hate (speech|manifesto|propaganda)|racial purity|ethnic cleansing)\b"),
        "Hate material is not supported.",
    ),
    (
        re.compile(
            r"(?i)\b(how to|instructions? (for|to)|step[- ]by[- ]step|guide to)\b.{0,40}"
            r"\b(make|build|synthesi[sz]e|cook|create)\b.{0,30}\b(bomb|explosives?|nerve agent|bioweapon|meth(amphetamine)?|ransomware|malware)\b"
        ),
        "Instructions that enable serious wrongdoing are not supported.",
    ),
]
_COPY_REQUEST = re.compile(
    r"(?i)\b(exact copy|word[- ]for[- ]word|reproduce|recreate|copy of|clone of|extended version of|"
    r"continuation of|sequel to|next book in|new chapters? (of|for)|rewrite)\b.{0,80}\b(book|novel|series|story|trilogy|saga)\b"
)
_STYLE_IMITATION = re.compile(r"(?i)\b(in the style of|written like|imitate|mimic|sound like)\s+[A-Z][\w.'-]+(\s+[A-Z][\w.'-]+)?")
_REAL_PERSON_BIOGRAPHY = re.compile(r"(?i)\b(secret|scandal|affair|crime|criminal|abuse)\w*\b.{0,40}\b(real|actual|living)\b")


def screen_request(book_input: BookInput) -> None:
    """Raise ``ContentPolicyError`` for requests that clearly violate the content policy.

    This is a first, cheap screen. The planning prompt also tells the model to refuse unsafe requests.
    """
    text = " ".join([book_input.book_idea, book_input.preferred_title, book_input.custom_book_type])
    for pattern, reason in _BLOCKED:
        if pattern.search(text):
            raise ContentPolicyError(reason)
    if _COPY_REQUEST.search(text):
        raise ContentPolicyError(
            "AI Book Studio cannot reproduce or extend an existing copyrighted book. Describe your own premise and "
            "the app will create a new, original book inspired by broad themes."
        )
    if _STYLE_IMITATION.search(book_input.book_idea):
        raise ContentPolicyError(
            "AI Book Studio does not imitate the distinctive style of a specific author. "
            "Describe the tone you want instead, for example 'warm, fast-paced and funny'."
        )
    if book_input.book_type == "Biography" and _REAL_PERSON_BIOGRAPHY.search(book_input.book_idea):
        raise ContentPolicyError(
            "Biographies cannot present unverified or damaging claims about real people as facts. "
            "Choose a fictional character or provide verified source material."
        )


# --------------------------------------------------------------------------------------
# Plan
# --------------------------------------------------------------------------------------
def normalize_plan(plan: BookPlan, target_words: int) -> BookPlan:
    """Repair a model-generated plan: sequential numbers, unique titles, positive and balanced word targets."""
    ordered = sorted(enumerate(plan.chapters), key=lambda pair: (pair[1].chapter_number or 10_000, pair[0]))
    plan.chapters = [chapter for _, chapter in ordered]
    seen: dict[str, int] = {}
    for index, chapter in enumerate(plan.chapters, start=1):
        chapter.chapter_number = index
        if not chapter.title.strip():
            chapter.title = f"Chapter {index}"
        key = chapter.title.strip().lower()
        seen[key] = seen.get(key, 0) + 1
        if seen[key] > 1:
            chapter.title = f"{chapter.title.strip()} (Part {seen[key]})"
    if plan.chapters:
        positives = [c.target_words for c in plan.chapters if c.target_words > 0]
        average = round(sum(positives) / len(positives)) if positives else max(100, target_words // len(plan.chapters))
        for chapter in plan.chapters:
            if chapter.target_words <= 0:
                chapter.target_words = average
        total = plan.total_target_words
        if target_words > 0 and abs(total - target_words) > 0.2 * target_words:
            factor = target_words / total
            for chapter in plan.chapters:
                chapter.target_words = max(50, round(chapter.target_words * factor))
    plan.estimated_words = plan.total_target_words
    return plan


def validate_plan(plan: BookPlan | None, target_words: int = 0) -> ValidationReport:
    """Validate a (possibly user-edited) plan."""
    report = ValidationReport()
    if plan is None:
        report.errors.append("There is no book plan yet.")
        return report
    if not plan.title.strip():
        report.errors.append("The book title is empty.")
    if not plan.chapters:
        report.errors.append("The plan must contain at least one chapter.")
        return report
    titles: dict[str, int] = {}
    for index, chapter in enumerate(plan.chapters, start=1):
        if chapter.chapter_number != index:
            report.errors.append(f"Chapter numbers must be sequential: expected {index}, found {chapter.chapter_number}.")
        if not chapter.title.strip():
            report.errors.append(f"Chapter {index} has no title.")
        if chapter.target_words <= 0:
            report.errors.append(f"Chapter {index} needs a positive word target.")
        titles.setdefault(chapter.title.strip().lower(), 0)
        titles[chapter.title.strip().lower()] += 1
        if not chapter.summary.strip():
            report.warnings.append(f"Chapter {index} has no summary.")
    for title, count in titles.items():
        if title and count > 1:
            report.errors.append(f"Duplicate chapter title: '{title}'. Each chapter needs a unique title.")
    if target_words > 0:
        total = plan.total_target_words
        if abs(total - target_words) > 0.25 * target_words:
            report.warnings.append(
                f"Chapter word targets add up to {total:,} words; the page budget suggests about {target_words:,}."
            )
    return report


# --------------------------------------------------------------------------------------
# Project warnings and export readiness
# --------------------------------------------------------------------------------------
def collect_warnings(project: BookProject, storage: "ProjectStorage | None" = None) -> list[str]:
    """Warnings the user should see: failed quality reviews and placeholder or missing images."""
    warnings: list[str] = []
    for number in sorted(project.reviews):
        review = project.reviews[number]
        if not review.passed:
            warnings.append(
                f"Chapter {number} did not pass the automatic quality check (score {review.score}). "
                "Edit or regenerate it manually."
            )
    for key, image in sorted(project.images.items()):
        if image.status == "placeholder":
            warnings.append(f"{image.label or key}: a placeholder image is used. {image.warning}".strip())
        elif image.status == "failed":
            warnings.append(f"{image.label or key}: image generation failed. {image.warning}".strip())
    if storage and project.plan:
        for chapter in project.plan.chapters:
            if chapter.requires_image and not storage.image_file(project, f"chapter_{chapter.chapter_number:02d}"):
                warnings.append(f"Chapter {chapter.chapter_number} is missing its planned illustration.")
    return warnings


def validate_project_for_export(project: BookProject, storage: "ProjectStorage") -> ValidationReport:
    """Check that the book is complete enough to export."""
    report = ValidationReport()
    if project.plan is None:
        report.errors.append("Book plan does not exist.")
        return report
    if not any(text.strip() for text in project.chapters.values()):
        report.errors.append("No chapters have been written yet.")
    for number in project.chapter_numbers:
        if not project.chapters.get(number, "").strip():
            title = project.plan.chapter(number).title if project.plan.chapter(number) else ""
            report.errors.append(f"Chapter {number} ({title}) has no content.")
    cover = storage.image_file(project, "cover_final") or storage.image_file(project, "cover_art")
    if not cover:
        report.warnings.append("No cover has been generated yet. A placeholder cover will be created during export.")
    report.warnings.extend(collect_warnings(project, storage))
    return report
