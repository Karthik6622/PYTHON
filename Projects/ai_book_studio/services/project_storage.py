"""Atomic, resumable project persistence under ``projects/{project_id}/``."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import tempfile
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from config import PROJECTS_DIR
from models.book_models import (
    BookBible,
    BookInput,
    BookPlan,
    BookProject,
    ChapterSummary,
    GenerationStatus,
    IllustrationPlan,
    QualityReport,
    utc_now,
)
from utils.image_utils import validate_image
from utils.retry_utils import ProjectLoadError

LOGGER = logging.getLogger("ai_book_studio.storage")
_PROJECT_ID = re.compile(r"^[A-Za-z0-9_\-]{6,64}$")
_CHAPTER_FILE = re.compile(r"^chapter_(\d+)\.md$")
_NOT_YOURS = "That book belongs to a different browser, so it cannot be opened here."
_WRITE_LOCK = threading.RLock()  # chapters are saved from several worker threads; replacing a file must not overlap


def atomic_write(path: Path, data: str | bytes) -> None:
    """Write a file by writing a temporary file and renaming it, so a crash cannot corrupt the target."""
    with _WRITE_LOCK:
        _atomic_write(path, data)


def _atomic_write(path: Path, data: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "wb" if isinstance(data, bytes) else "w"
    kwargs: dict[str, Any] = {} if isinstance(data, bytes) else {"encoding": "utf-8", "newline": "\n"}
    handle, temp_name = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(handle, mode, **kwargs) as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


class ProjectStorage:
    """Reads and writes projects. Every save is atomic and happens right after each pipeline stage."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root or PROJECTS_DIR)
        self.root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ paths
    @staticmethod
    def is_valid_id(project_id: str) -> bool:
        return bool(_PROJECT_ID.match(project_id or ""))

    def project_dir(self, project_id: str) -> Path:
        if not self.is_valid_id(project_id):
            raise ProjectLoadError("Saved project could not be loaded (invalid project ID).")
        return self.root / project_id

    def chapters_dir(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "chapters"

    def images_dir(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "images"

    def exports_dir(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "exports"

    def image_path(self, project: BookProject | str, key: str) -> Path:
        """Path of an image file, for example ``cover_art``, ``cover_final`` or ``chapter_03``."""
        project_id = project if isinstance(project, str) else project.project_id
        return self.images_dir(project_id) / f"{key}.png"

    def image_file(self, project: BookProject | str, key: str) -> Path | None:
        """Path of an image only if it exists and is a valid picture."""
        path = self.image_path(project, key)
        return path if validate_image(path)[0] else None

    def export_path(self, project: BookProject | str, kind: str) -> Path:
        project_id = project if isinstance(project, str) else project.project_id
        return self.exports_dir(project_id) / f"completed_book.{kind}"

    def export_file(self, project: BookProject | str, kind: str) -> Path | None:
        path = self.export_path(project, kind)
        return path if path.exists() and path.stat().st_size > 0 else None

    # ------------------------------------------------------------------ create / list / delete
    def create_project(self, book_input: BookInput, owner: str = "") -> BookProject:
        project_id = f"{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}"
        project = BookProject(project_id=project_id, owner=owner, book_input=book_input.model_dump())
        for folder in (self.chapters_dir(project_id), self.images_dir(project_id), self.exports_dir(project_id)):
            folder.mkdir(parents=True, exist_ok=True)
        self.save_project_meta(project)
        self.save_status(project)
        return project

    def list_projects(self, owner: str | None = None) -> list[dict[str, str]]:
        """Saved projects, newest first, as ``{id, title, updated_at, stage}`` dictionaries.

        With ``owner`` only that browser's projects are returned; ``None`` returns every project.
        """
        found: list[dict[str, str]] = []
        for folder in self.root.iterdir() if self.root.exists() else []:
            meta = folder / "project.json"
            if not folder.is_dir() or not meta.exists() or not self.is_valid_id(folder.name):
                continue
            try:
                data = json.loads(meta.read_text(encoding="utf-8"))
                if owner is not None and (not owner or str(data.get("owner", "")) != owner):
                    continue
                status = self._read_json(folder / "generation_status.json") or {}
                found.append(
                    {
                        "id": folder.name,
                        "title": str(data.get("title") or "Untitled book"),
                        "updated_at": str(data.get("updated_at", "")),
                        "stage": str(status.get("stage", "new")),
                    }
                )
            except (OSError, ValueError, ProjectLoadError):
                LOGGER.warning("Skipping unreadable project folder %s", folder.name)
        return sorted(found, key=lambda item: item["updated_at"], reverse=True)

    def latest_project_id(self, owner: str | None = None) -> str | None:
        projects = self.list_projects(owner)
        return projects[0]["id"] if projects else None

    def owner_of(self, project_id: str) -> str:
        """Owner id stored with a project (empty for projects created before owners existed)."""
        meta = self._read_json(self.project_dir(project_id) / "project.json") or {}
        return str(meta.get("owner", ""))

    def delete_project(self, project_id: str, owner: str | None = None) -> None:
        """Delete one saved project folder (only folders directly under the projects root).

        With ``owner`` the folder is only deleted when it belongs to that owner.
        """
        folder = self.project_dir(project_id).resolve()
        if folder.parent != self.root.resolve() or not folder.exists():
            return
        if owner is not None and (not owner or self.owner_of(project_id) != owner):
            raise ProjectLoadError(_NOT_YOURS)
        shutil.rmtree(folder)

    def adopt_unowned(self, owner: str) -> int:
        """Give projects that predate owners to ``owner``. Returns how many were adopted."""
        adopted = 0
        for folder in self.root.iterdir() if self.root.exists() else []:
            meta_path = folder / "project.json"
            if not folder.is_dir() or not meta_path.exists() or not self.is_valid_id(folder.name):
                continue
            try:
                meta = self._read_json(meta_path) or {}
                if str(meta.get("owner", "")):
                    continue
                meta["owner"] = owner
                self._write_json(meta_path, meta)
                adopted += 1
            except (OSError, ProjectLoadError):
                LOGGER.warning("Could not adopt project folder %s", folder.name)
        return adopted

    def transfer_owner(self, old_owner: str, new_owner: str) -> int:
        """Move every project of ``old_owner`` to ``new_owner`` (used when a browser's books join an account)."""
        if not old_owner or not new_owner or old_owner == new_owner:
            return 0
        moved = 0
        for folder in self.root.iterdir() if self.root.exists() else []:
            meta_path = folder / "project.json"
            if not folder.is_dir() or not meta_path.exists() or not self.is_valid_id(folder.name):
                continue
            try:
                meta = self._read_json(meta_path) or {}
                if str(meta.get("owner", "")) != old_owner:
                    continue
                meta["owner"] = new_owner
                self._write_json(meta_path, meta)
                moved += 1
            except (OSError, ProjectLoadError):
                LOGGER.warning("Could not move project folder %s", folder.name)
        return moved

    def clear_generated(self, project: BookProject) -> None:
        """Remove generated content (bible, front matter, chapters, images, exports) but keep the input and plan."""
        folder = self.project_dir(project.project_id)
        for name in ("book_bible.json", "front_matter.json", "images.json"):
            (folder / name).unlink(missing_ok=True)
        for sub in ("chapters", "images", "exports"):
            shutil.rmtree(folder / sub, ignore_errors=True)
            (folder / sub).mkdir(parents=True, exist_ok=True)
        project.bible = None
        project.front_matter.clear()
        project.chapters.clear()
        project.summaries.clear()
        project.reviews.clear()
        project.images.clear()
        project.status = GenerationStatus(stage="planned" if project.plan else "new")
        self.save_status(project)
        self.save_project_meta(project)

    # ------------------------------------------------------------------ save
    def save_project_meta(self, project: BookProject) -> None:
        project.updated_at = utc_now()
        meta = {
            "project_id": project.project_id,
            "owner": project.owner,
            "title": project.title,
            "created_at": project.created_at,
            "updated_at": project.updated_at,
            "book_input": project.book_input.model_dump(mode="json"),
        }
        self._write_json(self.project_dir(project.project_id) / "project.json", meta)

    def save_plan(self, project: BookProject) -> None:
        if project.plan is not None:
            self._write_json(self.project_dir(project.project_id) / "book_plan.json", project.plan.model_dump(mode="json"))
        self.save_project_meta(project)

    def save_bible(self, project: BookProject) -> None:
        if project.bible is not None:
            self._write_json(self.project_dir(project.project_id) / "book_bible.json", project.bible.model_dump(mode="json"))
        self.save_project_meta(project)

    def save_front_matter(self, project: BookProject) -> None:
        self._write_json(self.project_dir(project.project_id) / "front_matter.json", project.front_matter)
        self.save_project_meta(project)

    def save_status(self, project: BookProject) -> None:
        project.status.updated_at = utc_now()
        self._write_json(
            self.project_dir(project.project_id) / "generation_status.json", project.status.model_dump(mode="json")
        )

    def save_images(self, project: BookProject) -> None:
        payload = {key: image.model_dump(mode="json") for key, image in list(project.images.items())}
        self._write_json(self.project_dir(project.project_id) / "images.json", payload)
        self.save_project_meta(project)

    def save_chapter(self, project: BookProject, number: int) -> None:
        """Save a chapter's text and, when present, its summary and quality review."""
        folder = self.chapters_dir(project.project_id)
        stem = f"chapter_{number:02d}"
        if number in project.chapters:
            atomic_write(folder / f"{stem}.md", project.chapters[number])
        if number in project.summaries:
            self._write_json(folder / f"{stem}_summary.json", project.summaries[number].model_dump(mode="json"))
        else:
            (folder / f"{stem}_summary.json").unlink(missing_ok=True)
        if number in project.reviews:
            self._write_json(folder / f"{stem}_review.json", project.reviews[number].model_dump(mode="json"))
        self.save_project_meta(project)

    def save_all(self, project: BookProject) -> None:
        """Write every part of a project (used for imports and tests)."""
        self.save_project_meta(project)
        self.save_plan(project)
        self.save_bible(project)
        self.save_front_matter(project)
        self.save_images(project)
        for number in project.chapters:
            self.save_chapter(project, number)
        self.save_status(project)

    # ------------------------------------------------------------------ load
    def load_project(self, project_id: str, owner: str | None = None) -> BookProject:
        """Load a project. Raises ``ProjectLoadError`` with a clear message when it cannot be read.

        With ``owner`` the project is only loaded when it belongs to that owner.
        """
        folder = self.project_dir(project_id)
        meta = self._read_json(folder / "project.json")
        if not meta:
            raise ProjectLoadError()
        if owner is not None and (not owner or str(meta.get("owner", "")) != owner):
            raise ProjectLoadError(_NOT_YOURS)
        try:
            project = BookProject(
                project_id=project_id,
                owner=str(meta.get("owner", "")),
                created_at=str(meta.get("created_at", utc_now())),
                updated_at=str(meta.get("updated_at", utc_now())),
                book_input=BookInput.model_validate(meta.get("book_input", {})),
            )
            plan = self._read_json(folder / "book_plan.json")
            project.plan = BookPlan.model_validate(plan) if plan else None
            bible = self._read_json(folder / "book_bible.json")
            project.bible = BookBible.model_validate(bible) if bible else None
            front = self._read_json(folder / "front_matter.json")
            project.front_matter = {str(k): str(v) for k, v in (front or {}).items()}
            images = self._read_json(folder / "images.json") or {}
            project.images = {key: IllustrationPlan.model_validate(value) for key, value in images.items()}
            status = self._read_json(folder / "generation_status.json")
            project.status = GenerationStatus.model_validate(status) if status else GenerationStatus()
            chapters_dir = folder / "chapters"
            if chapters_dir.exists():
                for file in sorted(chapters_dir.iterdir()):
                    match = _CHAPTER_FILE.match(file.name)
                    if not match:
                        continue
                    number = int(match.group(1))
                    project.chapters[number] = file.read_text(encoding="utf-8")
                    summary = self._read_json(chapters_dir / f"chapter_{number:02d}_summary.json")
                    if summary:
                        project.summaries[number] = ChapterSummary.model_validate(summary)
                    review = self._read_json(chapters_dir / f"chapter_{number:02d}_review.json")
                    if review:
                        project.reviews[number] = QualityReport.model_validate(review)
            return project
        except (ValidationError, OSError, ValueError) as exc:
            LOGGER.error("Could not load project %s: %s", project_id, type(exc).__name__)
            raise ProjectLoadError() from exc

    # ------------------------------------------------------------------ json helpers
    @staticmethod
    def _write_json(path: Path, data: Any) -> None:
        atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2))

    @staticmethod
    def _read_json(path: Path) -> Any:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            LOGGER.error("Corrupt JSON file %s", path.name)
            raise ProjectLoadError() from exc
