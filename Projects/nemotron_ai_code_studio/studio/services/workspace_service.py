"""Sandboxed file operations. Every path is resolved through security.resolve_in_root, so nothing leaves the repository."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from ..config import settings
from ..security import PathSecurityError, is_protected, relative_posix, resolve_in_root

HEAVY_DIRS = {
    "node_modules", "dist", "build", "coverage", "__pycache__", ".venv", "venv", "env", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", ".next", ".nuxt", ".idea", ".vscode", "target", ".gradle", ".tox", ".cache", ".parcel-cache",
}
BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".pdf", ".zip", ".gz", ".tar", ".7z", ".rar", ".exe", ".dll",
    ".so", ".dylib", ".bin", ".class", ".jar", ".pyc", ".pyo", ".woff", ".woff2", ".ttf", ".otf", ".eot", ".mp3", ".mp4",
    ".mov", ".avi", ".wav", ".sqlite", ".db", ".lock-binary", ".pkl", ".npy", ".parquet", ".onnx", ".pt", ".safetensors",
}
LANGUAGES = {
    ".py": "python", ".pyi": "python", ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".json": "json", ".md": "markdown", ".mdx": "markdown", ".html": "html",
    ".htm": "html", ".css": "css", ".scss": "scss", ".less": "less", ".yml": "yaml", ".yaml": "yaml", ".toml": "ini",
    ".ini": "ini", ".cfg": "ini", ".xml": "xml", ".svg": "xml", ".sh": "shell", ".bash": "shell", ".ps1": "powershell",
    ".bat": "bat", ".cmd": "bat", ".java": "java", ".kt": "kotlin", ".go": "go", ".rs": "rust", ".c": "c", ".h": "c",
    ".cpp": "cpp", ".cc": "cpp", ".hpp": "cpp", ".cs": "csharp", ".php": "php", ".rb": "ruby", ".swift": "swift",
    ".sql": "sql", ".r": "r", ".lua": "lua", ".vue": "html", ".svelte": "html", ".dockerfile": "dockerfile",
    ".txt": "plaintext", ".env": "plaintext", ".gitignore": "plaintext",
}
SPECIAL_NAMES = {"dockerfile": "dockerfile", "makefile": "makefile", ".gitignore": "plaintext", ".env.example": "plaintext"}


class WorkspaceError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def language_for(path: str | Path) -> str:
    name = Path(path).name.lower()
    return SPECIAL_NAMES.get(name) or LANGUAGES.get(Path(name).suffix, "plaintext")


def looks_binary(sample: bytes) -> bool:
    return b"\x00" in sample[:8000]


class WorkspaceService:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    # ---------------------------------------------------------------- path helpers
    def resolve(self, relative: str, *, allow_root: bool = True) -> Path:
        try:
            return resolve_in_root(self.root, relative, allow_root=allow_root)
        except PathSecurityError as exc:
            raise WorkspaceError(str(exc), 400) from exc

    def rel(self, path: Path) -> str:
        return relative_posix(self.root, path)

    def _writable(self, relative: str) -> Path:
        path = self.resolve(relative, allow_root=False)
        if is_protected(self.root, path):
            raise WorkspaceError("The .git directory is managed by Git and cannot be edited here.", 403)
        return path

    # ---------------------------------------------------------------- reading
    def list_dir(self, relative: str = "") -> list[dict[str, Any]]:
        directory = self.resolve(relative)
        if not directory.is_dir():
            raise WorkspaceError("Not a directory.", 404)
        entries: list[dict[str, Any]] = []
        for entry in os.scandir(directory):
            if entry.name == ".git":
                continue
            is_dir = entry.is_dir(follow_symlinks=False)
            try:
                size = 0 if is_dir else entry.stat(follow_symlinks=False).st_size
            except OSError:
                size = 0
            entries.append({
                "name": entry.name,
                "path": self.rel(Path(entry.path)),
                "type": "dir" if is_dir else "file",
                "size": size,
                "ignored": is_dir and entry.name in HEAVY_DIRS,
                "language": None if is_dir else language_for(entry.name),
            })
        entries.sort(key=lambda item: (item["type"] != "dir", item["name"].lower()))
        return entries

    def read_text(self, relative: str, max_bytes: int | None = None) -> dict[str, Any]:
        path = self.resolve(relative, allow_root=False)
        if not path.is_file():
            raise WorkspaceError(f"File not found: {relative}", 404)
        limit = max_bytes or settings.max_file_bytes
        size = path.stat().st_size
        with path.open("rb") as handle:
            data = handle.read(limit + 1)
        if looks_binary(data) or path.suffix.lower() in BINARY_EXTENSIONS:
            return {"path": self.rel(path), "binary": True, "content": "", "size": size, "truncated": False, "language": "plaintext"}
        truncated = len(data) > limit
        if truncated:
            data = data[:limit]
        text = data.decode("utf-8", errors="replace")
        return {
            "path": self.rel(path), "binary": False, "content": text, "size": size, "truncated": truncated,
            "language": language_for(path), "lines": text.count("\n") + (0 if text.endswith("\n") or not text else 1),
        }

    def read_lines(self, relative: str, start: int = 1, end: int | None = None) -> dict[str, Any]:
        info = self.read_text(relative)
        if info["binary"]:
            raise WorkspaceError("Binary files cannot be read as text.", 415)
        lines = info["content"].splitlines()
        start = max(1, start)
        end = len(lines) if end is None else min(len(lines), max(start, end))
        chunk = lines[start - 1:end]
        return {**info, "content": "\n".join(chunk), "start": start, "end": start + len(chunk) - 1, "total_lines": len(lines)}

    def metadata(self, relative: str) -> dict[str, Any]:
        path = self.resolve(relative)
        if not path.exists():
            return {"path": relative, "exists": False}
        stat = path.stat()
        info: dict[str, Any] = {
            "path": self.rel(path), "exists": True, "type": "dir" if path.is_dir() else "file",
            "size": stat.st_size, "modified": stat.st_mtime,
        }
        if path.is_file():
            with path.open("rb") as handle:
                sample = handle.read(8000)
            binary = looks_binary(sample) or path.suffix.lower() in BINARY_EXTENSIONS
            info.update({"language": language_for(path), "binary": binary})
            if not binary and stat.st_size <= settings.max_file_bytes:
                info["lines"] = path.read_bytes().count(b"\n") + 1
        return info

    def tree_text(self, relative: str = "", depth: int = 3, max_entries: int = 400) -> str:
        """A bounded text tree for the model (skips .git and heavy generated directories)."""
        base = self.resolve(relative)
        if not base.is_dir():
            raise WorkspaceError("Not a directory.", 404)
        lines: list[str] = [(self.rel(base) or self.root.name) + "/"]
        count = 0

        def walk(directory: Path, level: int) -> None:
            nonlocal count
            try:
                items = sorted(os.scandir(directory), key=lambda e: (not e.is_dir(follow_symlinks=False), e.name.lower()))
            except OSError:
                return
            for item in items:
                if item.name == ".git" or item.name in HEAVY_DIRS:
                    continue
                if count >= max_entries:
                    return
                count += 1
                is_dir = item.is_dir(follow_symlinks=False)
                lines.append("  " * level + item.name + ("/" if is_dir else ""))
                if is_dir and level < depth:
                    walk(Path(item.path), level + 1)

        walk(base, 1)
        if count >= max_entries:
            lines.append(f"... (truncated at {max_entries} entries)")
        return "\n".join(lines)

    # ---------------------------------------------------------------- writing
    def write_text(self, relative: str, content: str) -> dict[str, Any]:
        path = self._writable(relative)
        if path.is_dir():
            raise WorkspaceError("A directory with that name already exists.", 409)
        if len(content.encode("utf-8")) > settings.max_file_bytes * 5:
            raise WorkspaceError("Content is too large to write.", 413)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(dir=path.parent, prefix=".nemotron-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
                handle.write(content)
            os.replace(temp_name, path)
        except Exception:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise
        return {"path": self.rel(path), "size": path.stat().st_size}

    def create(self, relative: str, kind: str = "file", content: str = "") -> dict[str, Any]:
        path = self._writable(relative)
        if path.exists():
            raise WorkspaceError("That path already exists.", 409)
        if kind == "dir":
            path.mkdir(parents=True)
            return {"path": self.rel(path), "type": "dir"}
        self.write_text(relative, content)
        return {"path": self.rel(path), "type": "file"}

    def delete(self, relative: str) -> dict[str, Any]:
        path = self._writable(relative)
        if not path.exists() and not path.is_symlink():
            raise WorkspaceError("Path not found.", 404)
        if path.is_symlink() or path.is_file():
            path.unlink()
        else:
            shutil.rmtree(path)
        return {"path": relative, "deleted": True}

    def rename(self, source: str, target: str) -> dict[str, Any]:
        src = self._writable(source)
        dst = self._writable(target)
        if not src.exists():
            raise WorkspaceError("Source not found.", 404)
        if dst.exists():
            raise WorkspaceError("The destination already exists.", 409)
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
        return {"from": self.rel(src), "to": self.rel(dst)}
