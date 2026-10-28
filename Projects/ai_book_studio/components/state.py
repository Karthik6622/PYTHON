"""Session state, logging, flash messages and error handling shared by the interface components."""

from __future__ import annotations

import logging
import logging.handlers
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import streamlit as st

from config import (
    CONTENT_OPTIONS,
    DEFAULT_CONTENT_KEYS,
    DEFAULT_PAGES,
    ROOT_DIR,
    get_chapter_workers,
)
from models.book_models import BookInput, BookProject
from services.book_pipeline import BookPipeline
from services.job_runner import GenerationJob
from services.nvidia_client import NvidiaClient
from services.project_storage import ProjectStorage
from utils.retry_utils import AIBookError, redact

LOGGER = logging.getLogger("ai_book_studio")

MIRROR_DEFAULTS: dict[str, Any] = {
    "project_id": None,
    "book_input": None,
    "book_plan": None,
    "book_bible": None,
    "chapter_contents": {},
    "chapter_summaries": {},
    "chapter_reviews": {},
    "image_prompts": {},
    "generated_images": {},
    "generation_progress": 0.0,
    "generation_status": "new",
    "pdf_path": None,
    "docx_path": None,
    "current_error": None,
}
_LABEL_BY_KEY = {key: label for label, key in CONTENT_OPTIONS.items()}
_KEEP_PREFIXES = ("in_", "p_", "ct_", "co_", "cs_", "ck_", "cw_", "ci_", "cc_", "au_")


# --------------------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------------------
@st.cache_resource
def setup_logging() -> bool:
    """Log to logs/app.log (rotating). Secrets are redacted before they reach any log message."""
    logger = logging.getLogger("ai_book_studio")
    logger.setLevel(logging.INFO)
    log_dir = ROOT_DIR / "logs"
    try:
        log_dir.mkdir(exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(log_dir / "app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)
    except OSError:
        logger.addHandler(logging.StreamHandler())
    return True


@st.cache_resource
def get_storage() -> ProjectStorage:
    return ProjectStorage()


NAV_LABELS: dict[str, str] = {
    "create": "✍️ Create",
    "plan": "🗺️ Plan",
    "chapters": "📖 Chapters",
    "images": "🖼️ Images",
    "preview": "👁️ Preview",
    "export": "📤 Export",
    "audio": "🎧 Audio",
}


@st.cache_resource
def _job_registry() -> dict[str, GenerationJob]:
    """Background jobs live here, outside any one session, so they survive reruns and reconnects."""
    return {}


def job_for(project: BookProject | None) -> GenerationJob | None:
    return _job_registry().get(project.project_id) if project else None


def job_running(project: BookProject | None) -> bool:
    job = job_for(project)
    return bool(job and job.running)


@st.cache_resource
def _plan_registry() -> dict[str, GenerationJob]:
    """Background plan-creation jobs, keyed by project id."""
    return {}


def plan_job_here() -> GenerationJob | None:
    """The plan job of the project this browser session is working on (if any)."""
    return _plan_registry().get(st.session_state.get("plan_project_id") or "")


def plan_job_running_for(project: BookProject) -> bool:
    job = _plan_registry().get(project.project_id)
    return bool(job and job.running)


def go_to(section: str) -> None:
    """Open a section (a key of NAV_LABELS) on the next run."""
    st.session_state["nav_target"] = section


def start_generation(project: BookProject) -> bool:
    """Start (or continue) generation in the background and open the Chapters section."""
    if job_running(project):
        return True

    def build(progress, chapter_event, should_stop) -> BookPipeline:
        return BookPipeline(
            project,
            get_storage(),
            llm_factory=NvidiaClient,
            progress=progress,
            chapter_event=chapter_event,
            should_stop=should_stop,
            chapter_workers=workers,
        )

    workers = get_chapter_workers()
    job = GenerationJob(build)
    try:
        job.start()
    except AIBookError as exc:
        st.error(exc.user_message)
        return False
    job.handled = False  # type: ignore[attr-defined]
    _job_registry()[project.project_id] = job
    project.status.stage = "running"
    project.status.error = None
    go_to("chapters")
    return True


def start_plan(project: BookProject, new_book: bool = False) -> bool:
    """Create the book plan in the background so the interface can show each step as it happens.

    ``new_book`` means the project was created for this request and is deleted again if the plan fails.
    """
    if plan_job_running_for(project):
        return True

    def build(progress, chapter_event, should_stop) -> BookPipeline:
        return BookPipeline(
            project,
            get_storage(),
            llm_factory=NvidiaClient,
            progress=progress,
            chapter_event=chapter_event,
            should_stop=should_stop,
        )

    job = GenerationJob(build, task="plan")
    try:
        job.start()
    except AIBookError as exc:
        st.error(exc.user_message)
        return False
    job.handled = False
    job.new_book = new_book
    _plan_registry()[project.project_id] = job
    st.session_state["plan_project_id"] = project.project_id
    if new_book:
        set_project(project)  # open it now so the Plan tab and the sidebar can show the live status
    go_to("plan")
    return True


def _finalize_plan_jobs() -> None:
    """Once per finished plan job: adopt the new plan (or report the error) and forget the job."""
    registry = _plan_registry()
    for project_id, job in list(registry.items()):
        if job.running or job.handled:
            continue
        job.handled = True
        registry.pop(project_id, None)
        project = job.project
        current = current_project()
        is_current = current is not None and current.project_id == project_id
        if job.plan_ready and project is not None:
            if job.new_book or is_current:
                set_project(project)
            flash("Your book plan is ready. Review and edit it below, then generate the book.", "success")
            go_to("plan")
        else:
            if job.new_book:
                try:
                    get_storage().delete_project(project_id)
                except (AIBookError, OSError) as exc:
                    LOGGER.warning("Could not remove the unfinished project: %s", redact(exc))
                if is_current:
                    set_project(None)
                go_to("create")
            flash(job.error or "The book plan could not be created.", "error")


def stop_generation(project: BookProject) -> None:
    job = job_for(project)
    if job and job.running:
        job.request_stop()


def finalize_job() -> None:
    """Once per finished job: refresh the mirrors, show the outcome and open Preview after success."""
    _finalize_plan_jobs()
    project = current_project()
    job = job_for(project)
    if job is None or job.running or getattr(job, "handled", True):
        return
    job.handled = True  # type: ignore[attr-defined]
    sync_mirrors(project)
    bump_content()
    if job.summary is not None:
        st.session_state["export_summary"] = job.summary
        extra = f" {len(job.summary.warnings)} warning(s) need your attention." if job.summary.warnings else ""
        flash(f"Your book is ready ({job.summary.pages} PDF pages). Review it here, then download it on the Export tab.{extra}", "success")
        go_to("preview")
    elif job.stopped:
        flash("Generation stopped. Your progress is saved; press Continue to carry on.", "warning")
    elif job.error:
        flash(f"{job.error} Your progress is saved; press Continue to carry on.", "error")


# --------------------------------------------------------------------------------------
# Session state
# --------------------------------------------------------------------------------------
def input_defaults() -> dict[str, Any]:
    return {
        "in_idea": "",
        "in_title": "",
        "in_author": "",
        "in_bio": "",
        "in_type": "Fiction",
        "in_custom_type": "",
        "in_audience": "General Audience",
        "in_style": "Storytelling",
        "in_language": "English",
        "in_pages": DEFAULT_PAGES,
        "in_frequency": "One image every chapter",
        "in_image_style": "Cinematic digital art",
        "in_options": [_LABEL_BY_KEY[key] for key in DEFAULT_CONTENT_KEYS],
    }


def init_state() -> None:
    """Create every session-state key once, before any widget is drawn."""
    for key, value in {**MIRROR_DEFAULTS, **input_defaults()}.items():
        st.session_state.setdefault(key, value.copy() if isinstance(value, (dict, list)) else value)
    st.session_state.setdefault("project", None)
    st.session_state.setdefault("plan_version", 0)
    st.session_state.setdefault("content_version", 0)
    st.session_state.setdefault("flash", [])
    st.session_state.setdefault("export_summary", None)
    # Only the open section is drawn, and Streamlit forgets widgets that are not drawn.
    # Re-assigning keeps the form and the unsaved plan edits when moving between sections.
    for key in list(st.session_state.keys()):
        if isinstance(key, str) and key.startswith(_KEEP_PREFIXES):
            st.session_state[key] = st.session_state[key]


def current_project() -> BookProject | None:
    return st.session_state.get("project")


def image_if_exists(project: BookProject, key: str) -> Path | None:
    """Cheap existence check used by the interface (full validation happens at export time)."""
    path = get_storage().image_path(project, key)
    return path if path.exists() and path.stat().st_size > 0 else None


def sync_mirrors(project: BookProject | None) -> None:
    """Mirror the active project into the documented session-state keys."""
    state = st.session_state
    if project is None:
        for key, value in MIRROR_DEFAULTS.items():
            state[key] = value.copy() if isinstance(value, (dict, list)) else value
        return
    storage = get_storage()
    state["project_id"] = project.project_id
    state["book_input"] = project.book_input
    state["book_plan"] = project.plan
    state["book_bible"] = project.bible
    state["chapter_contents"] = project.chapters
    state["chapter_summaries"] = project.summaries
    state["chapter_reviews"] = project.reviews
    state["image_prompts"] = {key: image.prompt for key, image in project.images.items()}
    keys = ["cover_final"] + [f"chapter_{n:02d}" for n in project.chapter_numbers]
    state["generated_images"] = {key: str(path) for key in keys if (path := image_if_exists(project, key))}
    state["generation_progress"] = project.status.progress
    state["generation_status"] = project.status.stage
    state["pdf_path"] = str(path) if (path := storage.export_file(project, "pdf")) else None
    state["docx_path"] = str(path) if (path := storage.export_file(project, "docx")) else None
    state["current_error"] = project.status.error


def populate_inputs(book_input: BookInput) -> None:
    """Copy a saved BookInput into the Create tab widgets. Call only from callbacks or before widgets are drawn."""
    st.session_state.update(
        {
            "in_idea": book_input.book_idea,
            "in_title": book_input.preferred_title,
            "in_author": book_input.author_name,
            "in_bio": book_input.author_bio,
            "in_type": book_input.book_type,
            "in_custom_type": book_input.custom_book_type,
            "in_audience": book_input.audience,
            "in_style": book_input.writing_style,
            "in_language": book_input.language,
            "in_pages": book_input.pages,
            "in_frequency": book_input.illustration_frequency,
            "in_image_style": book_input.image_style,
            "in_options": [_LABEL_BY_KEY[key] for key in book_input.content_options if key in _LABEL_BY_KEY],
        }
    )


def set_project(project: BookProject | None) -> None:
    st.session_state["project"] = project
    st.session_state["plan_version"] += 1
    st.session_state["content_version"] += 1
    st.session_state["export_summary"] = None
    sync_mirrors(project)


def bump_content() -> None:
    st.session_state["content_version"] += 1


def open_project(project_id: str) -> None:
    """Callback: load a saved project and show its input in the Create tab."""
    try:
        project = get_storage().load_project(project_id)
    except AIBookError as exc:
        flash(exc.user_message, "error")
        return
    populate_inputs(project.book_input)
    live = job_for(project)
    if live is not None and live.running and live.project is not None:
        project = live.project  # attach to the generation that is still running
    set_project(project)
    flash(f"Loaded “{project.title}”.", "success")


def new_book() -> None:
    """Callback: start from a blank form."""
    st.session_state.update(input_defaults())
    set_project(None)


def delete_project(project_id: str) -> None:
    """Callback: delete one saved project folder."""
    try:
        get_storage().delete_project(project_id)
    except (AIBookError, OSError) as exc:
        flash(f"The project could not be deleted: {redact(exc)}", "error")
        return
    st.session_state["sb_confirm_delete"] = False
    new_book()
    flash("The saved project was deleted.", "success")


# --------------------------------------------------------------------------------------
# Messages and errors
# --------------------------------------------------------------------------------------
def flash(message: str, kind: str = "info") -> None:
    """Queue a message that is shown at the top of the next run."""
    st.session_state.setdefault("flash", []).append((kind, message))


def render_flash() -> None:
    queue, st.session_state["flash"] = st.session_state.get("flash", []), []
    for kind, message in queue:
        {"success": st.success, "error": st.error, "warning": st.warning}.get(kind, st.info)(message)


@contextmanager
def guarded(action: str) -> Iterator[None]:
    """Show a friendly message instead of a traceback. Technical details go to the log (secrets redacted)."""
    try:
        yield
    except AIBookError as exc:
        LOGGER.warning("%s failed: %s: %s", action, type(exc).__name__, redact(exc))
        st.error(exc.user_message)
    except Exception as exc:  # noqa: BLE001 - last line of defence for the UI
        LOGGER.error("%s failed unexpectedly: %s: %s", action, type(exc).__name__, redact(exc), exc_info=True)
        st.error(f"{action} failed unexpectedly ({type(exc).__name__}). The details were written to logs/app.log.")


def make_pipeline(project: BookProject, progress: Callable[[float, str], None] | None = None) -> BookPipeline:
    """Pipeline bound to the project. The NVIDIA client is created lazily, so a missing key surfaces as a clear message."""
    return BookPipeline(project, get_storage(), llm_factory=NvidiaClient, progress=progress)


def refresh() -> None:
    """Re-mirror the project after a change and rerun the script."""
    sync_mirrors(current_project())
    st.rerun()
