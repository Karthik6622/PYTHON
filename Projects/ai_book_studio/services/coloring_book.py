"""Coloring books: Nemotron plans the book, the image model draws every page, Pillow turns each drawing into clean black-and-white line art.

Nemotron is a text model and cannot draw, so it only writes the plan (title, cover scene, one scene per page). The pictures come
from the image provider that is already configured for the app (Cloudflare FLUX, AI Horde or an OpenAI-compatible API). Each
picture is then converted to pure black lines on white, checked, and placed on a print-ready page. Every step is saved to disk,
so an interrupted run resumes where it stopped.

The coloring pages are stored as the plan's "chapters" (number, title, scene) so that saving, status, progress and the
background job work exactly as they do for an eBook.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PIL import Image

from config import COMPLEXITY_HARD, LAYOUT_PAGE_WITH_ICON
from generators.coloring_pdf import build_coloring_docx, build_coloring_pdf, build_pages_zip
from generators.cover_generator import compose_coloring_cover
from models.book_models import BookInput, BookPlan, ChapterPlan, GenerationStatus, IllustrationPlan, utc_now
from prompts.coloring_prompts import COLORING_PLAN_PROMPT, MORE_SCENES_PROMPT, cover_art_prompt, detail_for, page_prompt
from services.book_pipeline import ExportSummary, GenerationStopped
from services.image_generator import PlaceholderImageGenerator, generate_illustration
from utils.coloring_utils import compose_page, is_usable_line_art, make_line_art_placeholder, to_line_art
from utils.coloring_front_matter import render_front_pages
from utils.image_utils import ORIENTATION_SIZES, validate_image
from utils.proofread import autocorrect_text, proofread_issues
from utils.retry_utils import (
    AIBookError,
    ContentPolicyError,
    ExportError,
    NvidiaAuthError,
    NvidiaKeyMissingError,
    redact,
)
from utils.text_utils import render_template
from utils.validation_utils import screen_request, validate_book_input

if TYPE_CHECKING:
    from services.book_pipeline import BookPipeline
    from services.nvidia_client import LLMClient

LOGGER = logging.getLogger("ai_book_studio.coloring")
DRAW_ATTEMPTS = 3  # tries per page before a drawn pattern takes its place
_LONG_SIDE = {"portrait": 1728, "square": 1536}  # pixels of the stored line art (enlarged so the lines stay crisp when printed)
_RETRY_SUFFIX = " Fewer, larger shapes, simple bold black outlines on pure white only, white space inside every shape, no shading or hatching."
_FOLLOW_UPS = 3
_MIN_SCENE_CHARS = 3


def line_key(number: int) -> str:
    """Key of the stored line art (black and white drawing) of one page."""
    return f"chapter_{number:02d}"


def page_key(number: int) -> str:
    """Key of the finished page (frame, line art and, if chosen, the colored preview)."""
    return f"page_{number:02d}"


def _save_png(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.stem + ".tmp.png")
    image.save(temp, "PNG", optimize=True)
    os.replace(temp, path)


def _load_flat(path: Path) -> Image.Image:
    """Open a generated picture; transparency is flattened onto white."""
    with Image.open(path) as image:
        image.load()
        if image.mode in ("RGBA", "LA") or "transparency" in image.info:
            rgba = image.convert("RGBA")
            flat = Image.new("RGB", rgba.size, (255, 255, 255))
            flat.paste(rgba, mask=rgba.split()[3])
            return flat
        return image.convert("RGB")


# --------------------------------------------------------------------------------------
# Plan
# --------------------------------------------------------------------------------------
def _pages_from(data: Any) -> list[ChapterPlan]:
    """Turn the model's page list into plan entries; strings and half-filled objects are accepted."""
    pages = data.get("pages") if isinstance(data, dict) else None
    if not isinstance(pages, list):
        return []
    result: list[ChapterPlan] = []
    for item in pages:
        if isinstance(item, str):
            title, scene = item, item
        elif isinstance(item, dict):
            scene = str(item.get("scene") or item.get("description") or item.get("prompt") or item.get("title") or "").strip()
            title = str(item.get("title") or item.get("name") or "").strip() or scene[:40]
        else:
            continue
        scene = scene.strip()
        if len(scene) < _MIN_SCENE_CHARS:
            continue
        result.append(ChapterPlan(title=title.strip(), objective=scene, summary=scene, image_concept=scene, requires_image=True))
    return result


def _validate_plan_reply(data: dict[str, Any]) -> BookPlan:
    if data.get("refused"):
        raise ContentPolicyError(str(data.get("reason") or "The model declined this request."))
    pages = _pages_from(data)
    if not pages:
        raise ValueError("The plan has no pages (the reply was probably cut off).")
    fields = {key: data.get(key, "") for key in ("title", "subtitle", "description", "cover_concept")}
    return BookPlan.model_validate({**fields, "chapters": [page.model_dump() for page in pages]})


def _validate_more_pages(data: dict[str, Any]) -> list[ChapterPlan]:
    pages = _pages_from(data)
    if not pages:
        raise ValueError("The reply has no pages.")
    return pages


def _fallback_title(idea: str) -> str:
    words = [word for word in idea.replace("\n", " ").split() if word][:6]
    base = " ".join(words).strip(" .,:;!?")
    return f"{base.title()} Coloring Book" if base else "My Coloring Book"


def _clean_title(text: str, fallback: str) -> str:
    """Tidy a title; a title with garbled words is replaced by the fallback so a misspelled name never reaches the cover."""
    title = autocorrect_text(" ".join(text.split()).strip(" \"'*#"))
    if not title or proofread_issues(title, "English", check_ending=False):
        return fallback
    return title


def _finish_plan(plan: BookPlan, book_input: BookInput, count: int) -> BookPlan:
    pages = plan.chapters[:count]
    seen: dict[str, int] = {}
    for index, page in enumerate(pages, start=1):
        page.chapter_number = index
        title = autocorrect_text(" ".join(page.title.split())) or f"Page {index}"
        seen[title.lower()] = seen.get(title.lower(), 0) + 1
        page.title = title if seen[title.lower()] == 1 else f"{title} ({seen[title.lower()]})"
        page.target_words = 0
    plan.chapters = pages
    plan.title = _clean_title(book_input.preferred_title or plan.title, _fallback_title(book_input.book_idea))
    plan.subtitle = _clean_title(plan.subtitle, "") if plan.subtitle.strip() else ""
    plan.description = autocorrect_text(plan.description.strip())
    plan.cover_concept = plan.cover_concept.strip() or f"{book_input.book_idea.strip()}, a joyful colorful scene"
    plan.author = book_input.author_name.strip()
    plan.book_type = "Coloring book"
    plan.audience = book_input.audience
    plan.language = "English"
    plan.writing_style = ""
    plan.estimated_pages = len(pages)
    plan.estimated_words = 0
    plan.visual_style = "Black and white line art"
    return plan


def generate_coloring_plan(llm: "LLMClient", book_input: BookInput, on_step: Callable[[str], None] | None = None) -> BookPlan:
    """Ask Nemotron for the title, the cover scene and one scene per page, then make the plan complete and tidy.

    A reply with too few scenes is topped up with follow-up requests; the page count always matches what the user chose.
    """
    count = book_input.coloring_pages
    detail = detail_for(book_input.audience, book_input.coloring_complexity)
    prompt = render_template(
        COLORING_PLAN_PROMPT,
        book_idea=book_input.book_idea.strip(),
        preferred_title=book_input.preferred_title.strip() or "None (create a title)",
        audience=book_input.audience,
        page_count=count,
        detail=detail,
    )
    if on_step:
        on_step("designing")
    plan: BookPlan = llm.generate_json(prompt, "planning", max_tokens=min(16000, 2500 + 110 * count), validator=_validate_plan_reply)
    if on_step:
        on_step("checking")
    for _ in range(_FOLLOW_UPS):
        missing = count - len(plan.chapters)
        if missing <= 0:
            break
        existing = "\n".join(f"- {page.image_concept}" for page in plan.chapters[-60:])
        more_prompt = render_template(
            MORE_SCENES_PROMPT,
            title=plan.title or "Coloring book",
            book_idea=book_input.book_idea.strip(),
            existing=existing,
            count=missing,
            detail=detail,
        )
        try:
            more = llm.generate_json(more_prompt, "planning", max_tokens=min(12000, 1500 + 110 * missing), validator=_validate_more_pages)
        except (NvidiaAuthError, NvidiaKeyMissingError, ContentPolicyError):
            raise
        except AIBookError as exc:
            LOGGER.warning("Could not get more page scenes: %s", type(exc).__name__)
            break
        known = {page.image_concept.strip().lower() for page in plan.chapters}
        plan.chapters += [page for page in more if page.image_concept.strip().lower() not in known]
    shortfall = count - len(plan.chapters)
    if shortfall > 0:
        # Last resort: reuse scenes with a new viewpoint so the book still has the number of pages that was asked for.
        base = list(plan.chapters)
        for index in range(shortfall):
            source = base[index % len(base)]
            plan.chapters.append(
                ChapterPlan(
                    title=f"{source.title} from a new angle",
                    objective=source.objective,
                    summary=source.summary,
                    image_concept=f"{source.image_concept} Shown from a different angle with a different pose and background.",
                    requires_image=True,
                )
            )
    return _finish_plan(plan, book_input, count)


# --------------------------------------------------------------------------------------
# Runner
# --------------------------------------------------------------------------------------
class ColoringRunner:
    """The coloring-book side of ``BookPipeline``. The pipeline hands its own project, storage and providers to it."""

    def __init__(self, pipeline: "BookPipeline") -> None:
        self.p = pipeline

    # ------------------------------------------------------------------ plan
    def create_plan(self) -> BookPlan:
        p = self.p
        book_input = p.project.book_input
        problems = validate_book_input(book_input)
        if problems:
            raise AIBookError(" ".join(problems))
        p._plan_step(0.02, "Checking your request...")
        screen_request(book_input)
        p._total, p._done = 1, 0
        steps = {
            "designing": (0.15, "Nemotron is planning the cover and every coloring page..."),
            "checking": (0.85, "Checking the page list and the title spelling..."),
        }
        plan = generate_coloring_plan(p.llm, book_input, on_step=lambda step: p._plan_step(*steps[step]))
        p._plan_step(0.95, "Saving the plan...")
        p.project.plan = plan
        p.storage.save_plan(p.project)
        p.project.status = GenerationStatus(stage="planned", message="Plan ready for review.", progress=0.0)
        p._set_stage("planned", "Plan ready for review.")
        return plan

    # ------------------------------------------------------------------ pages
    def _with_icon(self) -> bool:
        return self.p.project.book_input.coloring_layout == LAYOUT_PAGE_WITH_ICON

    @staticmethod
    def _size(picture: Image.Image | None, orientation: str, long_side: int) -> tuple[int, int]:
        width, height = picture.size if picture else ORIENTATION_SIZES.get(orientation, ORIENTATION_SIZES["portrait"])
        scale = long_side / max(width, height)
        return max(64, round(width * scale)), max(64, round(height * scale))

    def _draw(self, prompt: str, orientation: str, work_path: Path) -> tuple[Image.Image, str, str]:
        """Line art for one page: (image, status, warning). The image model is tried a few times, then a drawn pattern is used."""
        p = self.p
        long_side = _LONG_SIDE.get(orientation, _LONG_SIDE["portrait"])
        generator = p.images
        complexity = p.project.book_input.coloring_complexity
        if isinstance(generator, PlaceholderImageGenerator):  # development mode: no image model is configured
            return make_line_art_placeholder(self._size(None, orientation, long_side), prompt, complexity), "generated", ""
        thicken = complexity != COMPLEXITY_HARD
        reason = ""
        raw = work_path.with_name(work_path.stem + ".raw.png")
        for attempt in range(1, DRAW_ATTEMPTS + 1):
            p._check_stop()
            text = prompt if attempt == 1 or len(prompt) + len(_RETRY_SUFFIX) > 1000 else prompt + _RETRY_SUFFIX
            try:
                generator.generate_image(text, raw, orientation)
                valid, problem = validate_image(raw)
                if not valid:
                    reason = f"The provider returned an unusable image ({problem})."
                    continue
                picture = _load_flat(raw)
                # Solid black areas become outlines, so every shape has room to color; then the page is checked for that room.
                art = to_line_art(picture, self._size(picture, orientation, long_side), thicken=thicken, hollow=True)
                usable, problem = is_usable_line_art(art, complexity)
                if usable:
                    return art, "generated", ""
                reason = problem
            except AIBookError as exc:
                reason = exc.user_message
            except Exception as exc:  # noqa: BLE001
                LOGGER.error("Unexpected drawing error: %s: %s", type(exc).__name__, redact(exc))
                reason = f"Unexpected image error ({type(exc).__name__})."
            finally:
                raw.unlink(missing_ok=True)
            LOGGER.info("Coloring page attempt %s of %s failed: %s", attempt, DRAW_ATTEMPTS, reason)
        art = make_line_art_placeholder(self._size(None, orientation, long_side), prompt, complexity)
        return art, "placeholder", f"A drawn pattern is used after {DRAW_ATTEMPTS} attempts. {reason} Regenerate the page to try the image model again."

    def generate_page(self, number: int, new_prompt: bool = False, prompt: str | None = None, orientation: str | None = None) -> IllustrationPlan:
        """Draw (or redraw) one page. Failures are recorded on the page, not raised."""
        p = self.p
        plan = p._require_plan()
        chapter = plan.chapter(number)
        if chapter is None:
            raise AIBookError(f"Page {number} does not exist in the plan.")
        chosen = orientation or ("square" if self._with_icon() else "portrait")
        key = line_key(number)
        record = p.project.images.get(key)
        text = prompt or (record.prompt if record and record.prompt and not new_prompt and record.orientation == chosen else "")
        if not text:
            text = page_prompt(chapter.image_concept or chapter.title, p.project.book_input.audience, p.project.book_input.coloring_complexity)
        entry = IllustrationPlan(
            key=key,
            label=f"Page {number}: {chapter.title}",
            chapter_number=number,
            prompt=text,
            orientation=chosen,
            filename=page_key(number) + ".png",
            status="failed",
            updated_at=utc_now(),
        )
        line_path = p.storage.image_path(p.project, key)
        try:
            art, entry.status, entry.warning = self._draw(text, chosen, line_path)
            _save_png(art, line_path)
            self._compose(number, art, text)
        except GenerationStopped:
            raise
        except AIBookError as exc:
            entry.warning = exc.user_message
            LOGGER.warning("Page %s failed: %s", number, type(exc).__name__)
        p.project.images[key] = entry
        with p._lock:
            p.storage.save_images(p.project)
        p._save_status()
        return entry

    def _compose(self, number: int, art: Image.Image, seed: str) -> Path:
        path = self.p.storage.image_path(self.p.project, page_key(number))
        _save_png(compose_page(art, with_icon=self._with_icon(), seed=seed), path)
        return path

    def _compose_from_line_art(self, number: int, title: str) -> Path | None:
        """Rebuild the finished page from the saved line art (used when only the page file is missing)."""
        p = self.p
        line = p.storage.image_file(p.project, line_key(number))
        if line is None:
            return None
        with Image.open(line) as source:
            art = source.convert("L")
        record = p.project.images.get(line_key(number))
        return self._compose(number, art, record.prompt if record and record.prompt else title)

    def _page_job(self, chapter: ChapterPlan) -> None:
        p = self.p
        number = chapter.chapter_number
        p._check_stop()
        p._begin(f"Drawing page {number} of {len(p._require_plan().chapters)}: {chapter.title}")
        if not p.storage.image_file(p.project, line_key(number)):
            p._note(number, "illustrating")
            self.generate_page(number)
        elif not p.storage.image_file(p.project, page_key(number)):
            self._compose_from_line_art(number, chapter.title)
        p._finish()
        p._note(number, "done")

    # ------------------------------------------------------------------ cover
    def generate_cover(self, new_prompt: bool = False, prompt: str | None = None) -> IllustrationPlan:
        p = self.p
        plan = p._require_plan()
        record = p.project.images.get("cover")
        art_path = p.storage.image_path(p.project, "cover_art")
        text = prompt or (record.prompt if record and record.prompt and not new_prompt else "") or cover_art_prompt(plan.cover_concept, plan.title)
        entry = IllustrationPlan(
            key="cover",
            label="Front cover",
            prompt=text,
            orientation="portrait",
            filename="cover_final.png",
            status="failed",
            updated_at=utc_now(),
        )
        try:
            result = generate_illustration(p.images, text, art_path, "cover")
            entry.status = "placeholder" if result.placeholder_used else "generated"
            entry.warning = result.warning
            p.project.images["cover"] = entry
            self.recompose_cover()
        except GenerationStopped:
            raise
        except AIBookError as exc:
            entry.warning = exc.user_message
            LOGGER.warning("Cover failed: %s", type(exc).__name__)
            p.project.images["cover"] = entry
        p.storage.save_images(p.project)
        p._sync_status()
        p.storage.save_status(p.project)
        return entry

    def _front_pages(self, title: str, author: str) -> list[Path]:
        """Write the extra front pages the user asked for (none by default) and return their files."""
        p = self.p
        chosen = p.project.book_input.coloring_extras
        owner = p.project.book_input.coloring_copyright_name or author  # one name on every extra page
        files: list[Path] = []
        for key, image in render_front_pages(chosen, title, owner):
            path = p.storage.exports_dir(p.project.project_id) / f"front_{key}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            _save_png(image, path)
            files.append(path)
        return files

    def recompose_cover(self) -> Path:
        p = self.p
        plan = p._require_plan()
        return compose_coloring_cover(
            p.storage.image_file(p.project, "cover_art"),
            plan.title,
            plan.subtitle,
            plan.author,
            p.storage.image_path(p.project, "cover_final"),
            badge=f"{len(plan.chapters)} coloring pages",
            language=plan.language or "English",
        )

    # ------------------------------------------------------------------ whole book
    def generate_complete_book(self) -> ExportSummary:
        p = self.p
        plan = p._require_plan()
        p._total = len(plan.chapters) + 2
        p._done = 0
        p._set_stage("running", "Starting generation...")
        try:
            p._run_chapters(plan.chapters, self._page_job)
            p._check_stop()
            p._begin("Creating the front cover...")
            if not (p.storage.image_file(p.project, "cover_art") and "cover" in p.project.images):
                self.generate_cover()
            p._finish()
            p._begin("Building the PDF, the DOCX and the page files...")
            summary = self.assemble_exports()
            p._finish()
        except GenerationStopped as exc:
            p._set_stage("stopped", exc.user_message)
            raise
        except AIBookError as exc:
            LOGGER.error("Generation stopped: %s", type(exc).__name__)
            p._fail(exc.user_message)
            raise
        except Exception as exc:  # noqa: BLE001
            LOGGER.error("Unexpected generation error: %s: %s", type(exc).__name__, redact(exc))
            message = f"Generation stopped unexpectedly ({type(exc).__name__}). Your progress is saved; press Resume."
            p._fail(message)
            raise AIBookError(message) from exc
        p.project.status.progress = 1.0
        p._set_stage("completed", "Your coloring book is ready.")
        if p._progress:
            p._progress(1.0, "Your coloring book is ready.")
        return summary

    # ------------------------------------------------------------------ export
    def assemble_exports(self, progress: Callable[[float, str], None] | None = None) -> ExportSummary:
        """Compose the cover, check every page, and write the PDF and DOCX (each with and without the cover) and the ZIP of page images."""
        report = progress or (lambda fraction, message: None)
        p = self.p
        plan = p._require_plan()
        report(0.05, "Composing the front cover...")
        cover = self.recompose_cover()
        report(0.15, "Checking every page...")
        pages: list[Path] = []
        for chapter in plan.chapters:
            number = chapter.chapter_number
            page = p.storage.image_file(p.project, page_key(number)) or self._compose_from_line_art(number, chapter.title)
            if page is None:
                raise ExportError(f"Page {number} ({chapter.title}) has not been drawn yet.")
            pages.append(page)
        front = self._front_pages(plan.title, plan.author)
        sheets = front + pages
        pdf_path = p.storage.export_path(p.project, "pdf")
        report(0.3, "Building the PDF...")
        count = build_coloring_pdf(plan.title, plan.author, cover, sheets, pdf_path)
        report(0.5, "Building the DOCX...")
        docx_path = build_coloring_docx(plan.title, plan.author, cover, sheets, p.storage.export_path(p.project, "docx"))
        report(0.65, "Building the DOCX without the cover...")
        docx_plain = build_coloring_docx(plan.title, plan.author, cover, sheets, p.storage.export_path(p.project, "no_cover.docx"), include_cover=False)
        report(0.8, "Packing the page images...")
        archive = build_pages_zip(pages, p.storage.export_path(p.project, "zip"), cover, front)
        p._sync_status()
        warnings = list(p.project.status.warnings)
        p.storage.save_status(p.project)
        report(1.0, "PDF, DOCX and page images are ready.")
        return ExportSummary(
            pdf_path=pdf_path, docx_path=docx_path, pages=count, warnings=warnings, docx_no_cover_path=docx_plain, zip_path=archive
        )
