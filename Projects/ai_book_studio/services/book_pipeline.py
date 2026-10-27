"""The 17-step book pipeline: plan, bible, front matter, chapters, review, summaries, images, cover and exports.

Every stage is saved to disk as soon as it finishes, so an interrupted run resumes where it stopped.
This module never imports Streamlit; the interface passes a progress callback instead.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from config import MAX_REVISIONS
from generators import ExportAssets
from generators.cover_generator import compose_cover
from generators.docx_generator import build_docx
from generators.pdf_generator import build_pdf
from models.book_models import BookProject, GenerationStatus, IllustrationPlan, utc_now
from services.book_bible import generate_bible
from services.book_planner import generate_plan
from services.chapter_reviewer import review_chapter, summarize_chapter
from services.chapter_writer import revise_chapter, write_chapter, write_front_section, write_glossary
from services.image_generator import ImageGenerator, PlaceholderImageGenerator, generate_illustration, get_image_generator
from services.image_prompt_service import chapter_prompt, choose_orientation, cover_prompt
from services.nvidia_client import LLMClient, NvidiaClient
from services.project_storage import ProjectStorage
from utils.retry_utils import AIBookError, ExportError, redact
from utils.text_utils import chapter_label, compute_budget, label
from utils.validation_utils import collect_warnings, screen_request, validate_book_input, validate_project_for_export

LOGGER = logging.getLogger("ai_book_studio.pipeline")
ProgressCallback = Callable[[float, str], None]
ChapterEventCallback = Callable[[int, str], None]
REVIEW_UNAVAILABLE = "Review unavailable."


class GenerationStopped(AIBookError):
    """The user asked to stop; progress is saved and generation can continue later."""

    default_message = "Generation was stopped. Your progress is saved; press Continue to carry on."


@dataclass
class ExportSummary:
    """Result of assembling the PDF and DOCX."""

    pdf_path: Path
    docx_path: Path
    pages: int
    warnings: list[str] = field(default_factory=list)


class BookPipeline:
    """Runs and resumes the generation of one book project."""

    def __init__(
        self,
        project: BookProject,
        storage: ProjectStorage,
        llm: LLMClient | None = None,
        image_generator: ImageGenerator | None = None,
        progress: ProgressCallback | None = None,
        llm_factory: Callable[[], LLMClient] | None = None,
        chapter_event: ChapterEventCallback | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> None:
        self.project = project
        self.storage = storage
        self._llm = llm
        self._llm_factory = llm_factory
        self._image_generator = image_generator
        self._progress = progress
        self._chapter_event = chapter_event
        self._should_stop = should_stop
        self._total = 1
        self._done = 0

    # ------------------------------------------------------------------ lazy providers
    @property
    def llm(self) -> LLMClient:
        if self._llm is None:
            self._llm = self._llm_factory() if self._llm_factory else NvidiaClient()
        return self._llm

    @property
    def images(self) -> ImageGenerator:
        if self._image_generator is None:
            self._image_generator = get_image_generator()
        return self._image_generator

    # ------------------------------------------------------------------ progress and status
    def _begin(self, message: str) -> None:
        fraction = min(self._done / max(self._total, 1), 0.99)
        self.project.status.message = message
        self.project.status.progress = fraction
        if self._progress:
            self._progress(fraction, message)

    def _finish(self) -> None:
        self._done += 1

    def _note(self, number: int, phase: str) -> None:
        """Tell the interface which phase a chapter is in (writing, testing, revising, summarising, illustrating, done)."""
        if self._chapter_event:
            self._chapter_event(number, phase)

    def _check_stop(self) -> None:
        if self._should_stop and self._should_stop():
            raise GenerationStopped()

    def _sync_status(self) -> None:
        status = self.project.status
        status.total_chapters = len(self.project.chapter_numbers)
        status.completed_chapters = [n for n in self.project.chapter_numbers if self.project.chapter_done(n)]
        status.warnings = collect_warnings(self.project, self.storage)

    def _set_stage(self, stage: str, message: str = "", error: str | None = None) -> None:
        status = self.project.status
        status.stage = stage
        status.error = error
        if message:
            status.message = message
        self._sync_status()
        self.storage.save_status(self.project)

    def _fail(self, message: str) -> None:
        self._set_stage("failed", message, error=message)
        if self._progress:
            self._progress(self.project.status.progress, message)

    def _require_plan(self):
        if self.project.plan is None:
            raise AIBookError("Please create and approve a book plan first.")
        return self.project.plan

    # ------------------------------------------------------------------ steps 1-3: plan
    def _plan_step(self, fraction: float, message: str) -> None:
        self.project.status.message = message
        self.project.status.progress = fraction
        if self._progress:
            self._progress(fraction, message)

    def create_plan(self):
        """Validate the request, ask Nemotron for a plan and save it."""
        book_input = self.project.book_input
        problems = validate_book_input(book_input)
        if problems:
            raise AIBookError(" ".join(problems))
        self._plan_step(0.02, "Checking your request...")
        screen_request(book_input)
        self._total, self._done = 1, 0
        steps = {
            "designing": (0.15, "Nemotron is designing the chapters, themes and illustrations..."),
            "checking": (0.85, "Checking and balancing the plan (chapters, word counts, illustrations)..."),
        }
        plan = generate_plan(
            self.llm,
            book_input,
            compute_budget(book_input),
            on_step=lambda step: self._plan_step(*steps[step]),
        )
        self._plan_step(0.95, "Saving the plan...")
        self.project.plan = plan
        self.storage.save_plan(self.project)
        self.project.status = GenerationStatus(stage="planned", message="Plan ready for review.", progress=0.0)
        self._set_stage("planned", "Plan ready for review.")
        return plan

    # ------------------------------------------------------------------ steps 4-16: the whole book
    def generate_complete_book(self) -> ExportSummary:
        """Generate everything that is missing and export the book. Safe to call again after a failure."""
        plan = self._require_plan()
        options = self.project.book_input
        front_keys = [key for key in ("dedication", "preface", "introduction") if options.has(key)]
        back_keys = [key for key in ("conclusion", "glossary") if options.has(key)]
        image_chapters = [c for c in plan.chapters if c.requires_image]
        self._total = 1 + len(front_keys) + len(plan.chapters) + len(image_chapters) + len(back_keys) + 2
        self._done = 0
        self._set_stage("running", "Starting generation...")
        try:
            self._ensure_bible()
            for key in front_keys:
                self._check_stop()
                self._ensure_section(key)
            for chapter in plan.chapters:
                number = chapter.chapter_number
                self._check_stop()
                review = self.project.reviews.get(number)
                if not self.project.chapter_done(number):
                    self._begin(f"Writing {chapter_label(number, plan.language)}: {chapter.title}")
                    self.process_chapter(number)
                elif review is None or not review.passed:
                    self._begin(f"Improving {chapter_label(number, plan.language)}: {chapter.title}")
                    self.improve_chapter(number)
                else:
                    self._begin(f"{chapter_label(number, plan.language)}: {chapter.title} is already complete")
                self._finish()
                if chapter.requires_image:
                    self._check_stop()
                    self._begin(f"Creating illustration for {chapter_label(number, plan.language)}")
                    if not self.storage.image_file(self.project, f"chapter_{number:02d}"):
                        self._note(number, "illustrating")
                        self.generate_chapter_image(number)
                    self._finish()
                self._note(number, "done")
            for key in back_keys:
                self._check_stop()
                self._ensure_section(key)
            self._check_stop()
            self._begin("Creating the front cover...")
            if not (self.storage.image_file(self.project, "cover_art") and "cover" in self.project.images):
                self.generate_cover()
            self._finish()
            self._begin("Building the PDF and DOCX files...")
            summary = self.assemble_exports()
            self._finish()
        except GenerationStopped as exc:
            self._set_stage("stopped", exc.user_message)
            raise
        except AIBookError as exc:
            LOGGER.error("Generation stopped: %s", type(exc).__name__)
            self._fail(exc.user_message)
            raise
        except Exception as exc:  # noqa: BLE001
            LOGGER.error("Unexpected generation error: %s: %s", type(exc).__name__, redact(exc))
            message = f"Generation stopped unexpectedly ({type(exc).__name__}). Your progress is saved; press Resume."
            self._fail(message)
            raise AIBookError(message) from exc
        self.project.status.progress = 1.0
        self._set_stage("completed", "Your book is ready.")
        if self._progress:
            self._progress(1.0, "Your book is ready.")
        return summary

    def _ensure_bible(self) -> None:
        self._begin("Creating the book bible...")
        if self.project.bible is None:
            self.project.bible = generate_bible(self.llm, self._require_plan())
            self.storage.save_bible(self.project)
        self._finish()

    def _ensure_section(self, key: str) -> None:
        self._begin(f"Writing {label(key, 'English').lower()}...")
        if not self.project.front_matter.get(key, "").strip():
            if key == "glossary":
                text = write_glossary(self.llm, self.project)
            else:
                text = write_front_section(self.llm, self.project, key, compute_budget(self.project.book_input))
            self.project.front_matter[key] = text
            self.storage.save_front_matter(self.project)
        self._finish()

    # ------------------------------------------------------------------ chapters
    def process_chapter(self, number: int, force: bool = False) -> None:
        """Write (when missing), review, revise up to twice and summarise one chapter."""
        plan = self._require_plan()
        chapter = plan.chapter(number)
        if chapter is None:
            raise AIBookError(f"Chapter {number} does not exist in the plan.")
        project = self.project
        if force or not project.chapters.get(number, "").strip():
            self._note(number, "writing")
            project.chapters[number] = write_chapter(self.llm, project, chapter)
            project.summaries.pop(number, None)
            project.reviews.pop(number, None)
            self.storage.save_chapter(project, number)
        text = project.chapters[number]
        if number not in project.reviews:
            self._check_stop()
            self._note(number, "testing")
            report = review_chapter(self.llm, project, chapter, text)
            self._quality_loop(number, chapter, report)
        if number not in project.summaries:
            self._check_stop()
            self._note(number, "summarising")
            project.summaries[number] = summarize_chapter(self.llm, project, chapter, project.chapters[number])
            self.storage.save_chapter(project, number)
        self._sync_status()
        self.storage.save_status(project)

    def _quality_loop(self, number: int, chapter, report, prior_revisions: int = 0) -> None:
        """Fix what the editor found, then re-check, up to MAX_REVISIONS times. Length is never a reason to fail."""
        project = self.project
        history = []
        revisions = 0
        while not report.passed and revisions < MAX_REVISIONS and report.editor_summary != REVIEW_UNAVAILABLE:
            revisions += 1
            self._check_stop()
            self._note(number, f"revising {revisions}")
            revised = revise_chapter(self.llm, project, chapter, project.chapters[number], report, history)
            project.chapters[number] = revised
            project.summaries.pop(number, None)  # the text changed, so the continuity summary is rebuilt
            self.storage.save_chapter(project, number)
            history.append(report)
            self._check_stop()
            self._note(number, "testing")
            report = review_chapter(self.llm, project, chapter, revised, previous=report)
        report.revisions = prior_revisions + revisions
        project.reviews[number] = report
        self.storage.save_chapter(project, number)

    def improve_chapter(self, number: int) -> None:
        """Re-test a finished chapter that did not pass and fix only the problems found."""
        plan = self._require_plan()
        chapter = plan.chapter(number)
        if chapter is None or not self.project.chapters.get(number, "").strip():
            raise AIBookError(f"Chapter {number} has no text to improve.")
        project = self.project
        report = project.reviews.get(number)
        prior = report.revisions if report else 0
        if report is None or report.editor_summary == REVIEW_UNAVAILABLE:
            self._check_stop()
            self._note(number, "testing")
            report = review_chapter(self.llm, project, chapter, project.chapters[number])
            prior = 0
        if not report.passed:
            self._quality_loop(number, chapter, report, prior)
        if number not in project.summaries:
            self._check_stop()
            self._note(number, "summarising")
            project.summaries[number] = summarize_chapter(self.llm, project, chapter, project.chapters[number])
            self.storage.save_chapter(project, number)
        self._sync_status()
        self.storage.save_status(project)

    def regenerate_chapter(self, number: int) -> None:
        """Rewrite one chapter from scratch with a fresh review and summary."""
        self.process_chapter(number, force=True)

    def review_again(self, number: int) -> None:
        """Run the quality check and the continuity summary again on the current text (no automatic revision)."""
        plan = self._require_plan()
        chapter = plan.chapter(number)
        if chapter is None or not self.project.chapters.get(number, "").strip():
            raise AIBookError(f"Chapter {number} has no text to review.")
        text = self.project.chapters[number]
        report = review_chapter(self.llm, self.project, chapter, text)
        self.project.reviews[number] = report
        self.project.summaries[number] = summarize_chapter(self.llm, self.project, chapter, text)
        self.storage.save_chapter(self.project, number)
        self._sync_status()
        self.storage.save_status(self.project)

    # ------------------------------------------------------------------ images
    def generate_chapter_image(
        self, number: int, new_prompt: bool = False, prompt: str | None = None, orientation: str | None = None
    ) -> IllustrationPlan:
        """Create (or recreate) a chapter illustration. Failures are recorded on the image, not raised."""
        plan = self._require_plan()
        chapter = plan.chapter(number)
        if chapter is None:
            raise AIBookError(f"Chapter {number} does not exist in the plan.")
        key = f"chapter_{number:02d}"
        record = self.project.images.get(key)
        chosen_orientation = orientation or (record.orientation if record else "") or choose_orientation(chapter, plan.book_type)
        path = self.storage.image_path(self.project, key)
        entry = IllustrationPlan(
            key=key,
            label=f"{chapter_label(number, plan.language)}: {chapter.title}",
            chapter_number=number,
            prompt=prompt or (record.prompt if record else ""),
            orientation=chosen_orientation,
            filename=path.name,
            status="failed",
            updated_at=utc_now(),
        )
        try:
            if prompt is None and (new_prompt or not entry.prompt):
                entry.prompt = chapter_prompt(self.llm, plan, self.project.bible, chapter, chosen_orientation)
            result = generate_illustration(self.images, entry.prompt, path, chosen_orientation)
            entry.status = "placeholder" if result.placeholder_used else "generated"
            entry.warning = result.warning
        except AIBookError as exc:
            entry.warning = exc.user_message
            LOGGER.warning("Chapter %s image failed: %s", number, type(exc).__name__)
        self.project.images[key] = entry
        self.storage.save_images(self.project)
        self._sync_status()
        self.storage.save_status(self.project)
        return entry

    def generate_cover(self, new_prompt: bool = False, prompt: str | None = None) -> IllustrationPlan:
        """Create the cover artwork and compose the final cover with the title and author."""
        plan = self._require_plan()
        record = self.project.images.get("cover")
        art_path = self.storage.image_path(self.project, "cover_art")
        entry = IllustrationPlan(
            key="cover",
            label="Front cover",
            prompt=prompt or (record.prompt if record else ""),
            orientation="portrait",
            filename="cover_final.png",
            status="failed",
            updated_at=utc_now(),
        )
        try:
            if self.project.book_input.illustration_frequency == "No images":
                PlaceholderImageGenerator().generate_image(plan.title, art_path, "cover")
                entry.status = "generated"
            else:
                if prompt is None and (new_prompt or not entry.prompt):
                    entry.prompt = cover_prompt(self.llm, plan, self.project.bible)
                result = generate_illustration(self.images, entry.prompt, art_path, "cover")
                entry.status = "placeholder" if result.placeholder_used else "generated"
                entry.warning = result.warning
            self.project.images["cover"] = entry
            self.recompose_cover()
        except AIBookError as exc:
            entry.warning = exc.user_message
            LOGGER.warning("Cover failed: %s", type(exc).__name__)
            self.project.images["cover"] = entry
        self.storage.save_images(self.project)
        self._sync_status()
        self.storage.save_status(self.project)
        return entry

    def recompose_cover(self) -> Path:
        """Draw the title, subtitle and author onto the cover artwork (typographic cover when no artwork exists)."""
        plan = self._require_plan()
        art = self.storage.image_file(self.project, "cover_art")
        return compose_cover(
            art,
            plan.title,
            plan.subtitle,
            plan.author,
            self.storage.image_path(self.project, "cover_final"),
            plan.language,
        )

    # ------------------------------------------------------------------ step 17: export
    def assemble_exports(self) -> ExportSummary:
        """Validate the book and create the PDF and DOCX files."""
        self._require_plan()
        cover = self.recompose_cover()
        report = validate_project_for_export(self.project, self.storage)
        if not report.ok:
            raise ExportError("The book cannot be exported yet: " + " ".join(report.errors))
        chapter_images: dict[int, Path] = {}
        for number in self.project.chapter_numbers:
            found = self.storage.image_file(self.project, f"chapter_{number:02d}")
            if found:
                chapter_images[number] = found
        assets = ExportAssets(cover_path=cover, chapter_images=chapter_images)
        pdf = build_pdf(self.project, assets, self.storage.export_path(self.project, "pdf"))
        docx = build_docx(self.project, assets, self.storage.export_path(self.project, "docx"))
        warnings = list(dict.fromkeys(report.warnings + pdf.warnings + docx.warnings))
        self.project.status.warnings = warnings
        self.storage.save_status(self.project)
        return ExportSummary(pdf_path=pdf.path, docx_path=docx.path, pages=pdf.pages, warnings=warnings)
