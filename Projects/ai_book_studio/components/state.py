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
)
from models.book_models import BookInput, BookProject
from services.book_pipeline import BookPipeline
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
