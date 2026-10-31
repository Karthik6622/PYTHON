"""On-disk storage for generated automation bundles (files are never stored in the database)."""

from __future__ import annotations

import io
import json
import shutil
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from ats.config import get_settings
from ats.errors import NotFoundError, StudioError

MAX_FILE_BYTES = 2_000_000
EXCLUDED_DIRS = {"node_modules", ".git", "__pycache__", "reports", "target", ".pytest_cache", "test-results", "playwright-report", ".venv"}
SECRET_NAMES = {".env", "storage_state.json"}
SECRET_SUFFIXES = (".pem", ".key", ".p12")


class UnsafePathError(StudioError):
    default_message = "That file path is not allowed."


def is_secret(rel: str) -> bool:
    name = PurePosixPath(rel).name.lower()
    if name in SECRET_NAMES or name.endswith(SECRET_SUFFIXES):
        return True
    return name.startswith(".env.") and name not in {".env.example", ".env.sample"}


def clean_rel(rel: str) -> str:
    """Normalise a relative path and reject anything that could escape the bundle folder."""
    text = (rel or "").replace("\\", "/").strip()
    if not text or "\x00" in text or text.startswith("/") or (len(text) > 1 and text[1] == ":"):
        raise UnsafePathError(f"Unsafe path: {rel!r}")
    parts = PurePosixPath(text).parts
    if any(part in {"..", ""} for part in parts):
        raise UnsafePathError(f"Unsafe path: {rel!r}")
    return "/".join(parts)


class BundleStore:
    def __init__(self, base: Path | None = None) -> None:
        self.base = base or get_settings().projects_dir

    # ------------------------------------------------------------------ locations
    def root(self, project_id: str, bundle_id: int) -> Path:
        return self.base / project_id / "bundles" / str(int(bundle_id))

    def _target(self, project_id: str, bundle_id: int, rel: str) -> Path:
        root = self.root(project_id, bundle_id).resolve()
        target = (root / clean_rel(rel)).resolve()
        if root != target and root not in target.parents:
            raise UnsafePathError(f"Unsafe path: {rel!r}")
        return target

    def exists(self, project_id: str, bundle_id: int) -> bool:
        return self.root(project_id, bundle_id).is_dir()

    # ------------------------------------------------------------------ write / read
    def write(self, project_id: str, bundle_id: int, files: dict[str, str]) -> None:
        root = self.root(project_id, bundle_id)
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True, exist_ok=True)
        for rel, content in files.items():
            self.write_file(project_id, bundle_id, rel, content)

    def write_file(self, project_id: str, bundle_id: int, rel: str, content: str) -> None:
        if len(content.encode("utf-8")) > MAX_FILE_BYTES:
            raise StudioError("File is too large.")
        target = self._target(project_id, bundle_id, rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")

    def read_file(self, project_id: str, bundle_id: int, rel: str) -> str:
        target = self._target(project_id, bundle_id, rel)
        if not target.is_file():
            raise NotFoundError()
        return target.read_text(encoding="utf-8", errors="replace")

    def list_files(self, project_id: str, bundle_id: int) -> list[str]:
        root = self.root(project_id, bundle_id)
        if not root.is_dir():
            return []
        out = []
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            if any(part in EXCLUDED_DIRS for part in path.relative_to(root).parts[:-1]) or is_secret(rel):
                continue
            out.append(rel)
        return out

    def read_all(self, project_id: str, bundle_id: int) -> dict[str, str]:
        return {rel: self.read_file(project_id, bundle_id, rel) for rel in self.list_files(project_id, bundle_id)}

    def zip_bytes(self, project_id: str, bundle_id: int) -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for rel, content in self.read_all(project_id, bundle_id).items():
                archive.writestr(rel, content)
        return buffer.getvalue()

    def copy_to(self, project_id: str, bundle_id: int, destination: Path) -> Path:
        """Copy the bundle (without secrets or run output) into a run workspace."""
        if destination.exists():
            shutil.rmtree(destination)
        destination.mkdir(parents=True, exist_ok=True)
        for rel, content in self.read_all(project_id, bundle_id).items():
            out = destination / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(content, encoding="utf-8", newline="\n")
        return destination

    # ------------------------------------------------------------------ locators
    def load_locators(self, project_id: str, bundle_id: int) -> dict[str, Any]:
        try:
            return json.loads(self.read_file(project_id, bundle_id, "config/locators.json"))
        except (NotFoundError, ValueError):
            return {}

    def save_locators(self, project_id: str, bundle_id: int, data: dict[str, Any]) -> None:
        self.write_file(project_id, bundle_id, "config/locators.json", json.dumps(data, indent=2, ensure_ascii=False) + "\n")

    def delete(self, project_id: str, bundle_id: int) -> None:
        shutil.rmtree(self.root(project_id, bundle_id), ignore_errors=True)


def import_files(files: dict[str, bytes]) -> dict[str, str]:
    """Filter and decode files fetched from a repository; secrets, binaries and oversized files are dropped."""
    out: dict[str, str] = {}
    for rel, raw in files.items():
        try:
            rel = clean_rel(rel)
        except UnsafePathError:
            continue
        if is_secret(rel) or len(raw) > MAX_FILE_BYTES or any(part in EXCLUDED_DIRS for part in PurePosixPath(rel).parts[:-1]):
            continue
        try:
            out[rel] = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
    return out
