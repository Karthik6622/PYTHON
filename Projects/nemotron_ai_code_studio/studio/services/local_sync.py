"""Server half of "work in a folder on my own computer" for hosted deployments.

A hosted app cannot open the visitor's Explorer or touch their disk, but the visitor's browser can (File System Access API).
The browser reads a folder and sends the text files here (`import_files`); afterwards this module works out which workspace
changes still have to be written back to that folder (`LocalLink.plan`), and the browser writes them. Everything that arrives
from the browser is validated here: relative paths only, nothing outside the workspace, no secrets, no tool folders.
"""

from __future__ import annotations

import base64
import json
import os
import re
import secrets
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from ..config import settings
from ..security import PathSecurityError, is_sensitive_path, resolve_in_root
from .workspace_service import BINARY_EXTENSIONS, HEAVY_DIRS

SKIP_DIRS = frozenset(HEAVY_DIRS | {".git"})
MAX_FILES = 3000
MAX_TOTAL_BYTES = 25_000_000
BATCH_FILES = 200
BATCH_BYTES = 6_000_000
EXPORT_FILE_LIMIT = 8_000_000  # largest single file written back to the user's folder
LISTED_LIMIT = 5000  # files the browser found but did not copy; they are still shown in the explorer


class SyncError(Exception):
    pass


def accept(path: object, text_only: bool = True) -> str | None:
    """A clean workspace-relative path, or None when the file must not be transferred (unsafe, secret, tool folder, binary)."""
    if not isinstance(path, str) or not path or "\x00" in path:
        return None
    cleaned = path.replace("\\", "/")
    if cleaned.startswith("/"):
        return None
    cleaned = cleaned.strip("/")
    parts = cleaned.split("/")
    if any(part in {"", ".", ".."} for part in parts) or re.match(r"^[A-Za-z]:", parts[0]):
        return None
    if any(part in SKIP_DIRS for part in parts[:-1]) or is_sensitive_path(cleaned):
        return None
    if text_only and PurePosixPath(cleaned).suffix.lower() in BINARY_EXTENSIONS:
        return None
    return cleaned


def clean_name(name: object) -> str:
    """A safe single folder name made from the name of the folder the user picked."""
    text = re.sub(r"[^A-Za-z0-9._ -]+", "_", str(name or "")).strip(" .")
    return text[:60] or "my-folder"


def scan(root: Path, text_only: bool = True, limit: int | None = None) -> dict[str, tuple[int, int]]:
    """relative path -> (modified time, size) of every transferable file in the workspace."""
    found: dict[str, tuple[int, int]] = {}
    max_bytes = limit or settings.max_file_bytes
    for current, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        base = Path(current)
        for name in names:
            full = base / name
            rel = accept(full.relative_to(root).as_posix(), text_only)
            if rel is None or full.is_symlink():
                continue
            try:
                info = full.stat()
            except OSError:
                continue
            if info.st_size > max_bytes:
                continue
            found[rel] = (info.st_mtime_ns, info.st_size)
            if len(found) >= MAX_FILES:
                return found
    return found


def snapshot(root: Path) -> dict[str, tuple[int, int]]:
    """Everything that is written back to the user's folder (text and binary files, secrets and tool folders excluded)."""
    return scan(root, text_only=False, limit=EXPORT_FILE_LIMIT)


@dataclass(frozen=True)
class ImportResult:
    count: int  # files written to the workspace copy
    left_out: int  # files that did not fit into the copy budget (MAX_TOTAL_BYTES) or the file limit


def import_files(root: Path, files: object) -> ImportResult:
    """Replace the workspace copy with the files the browser read from the user's folder.

    The copy has a size budget. Files that do not fit are left out and counted, instead of refusing the whole folder.
    Smaller files are kept first so that the most files fit into the budget."""
    if not isinstance(files, list):
        raise SyncError("The folder contents were not understood.")
    root.mkdir(parents=True, exist_ok=True)
    candidates: list[tuple[str, bytes]] = []
    left_out = max(0, len(files) - MAX_FILES)
    for item in files[:MAX_FILES]:
        if not isinstance(item, dict):
            continue
        rel = accept(item.get("path"))
        content = item.get("content")
        if rel is None or not isinstance(content, str):
            continue
        data = content.encode("utf-8")
        if len(data) > settings.max_file_bytes:
            continue
        candidates.append((rel, data))
    candidates.sort(key=lambda entry: len(entry[1]))
    written: set[str] = set()
    total = 0
    for rel, data in candidates:
        if total + len(data) > MAX_TOTAL_BYTES:
            left_out += 1
            continue
        try:
            target = resolve_in_root(root, rel, allow_root=False)
        except PathSecurityError:
            continue
        total += len(data)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        written.add(rel)
    for rel in scan(root):
        if rel not in written:
            try:
                (root / rel).unlink()
            except OSError:
                pass
    return ImportResult(count=len(written), left_out=left_out)


@dataclass
class LocalLink:
    """A workspace folder on the server that is mirrored to a folder on the user's computer.

    `known` is what the user's folder already has (relative path -> stamp). Anything new or changed in the workspace is sent
    to the browser in batches; the browser writes it and acknowledges, and only then is it counted as in sync.
    `fresh` means the folder has not received the workspace yet (a repository that was just cloned)."""

    name: str
    known: dict[str, tuple[int, int]] = field(default_factory=dict)
    pending: dict | None = None
    fresh: bool = False
    location: str = ""  # the folder's path on the user's computer, as typed by the user (display only)
    listed: list[dict] = field(default_factory=list)  # found on the user's computer but not copied: {path, size, why}

    def plan(self, root: Path) -> dict | None:
        """The next batch of changes for the browser to write, or None when everything is in sync."""
        if self.pending is None:
            current = snapshot(root)
            writes: list[dict[str, str]] = []
            stamps: dict[str, tuple[int, int]] = {}
            size = 0
            deletes = [path for path in self.known if path not in current][:BATCH_FILES]
            for rel, stamp in current.items():
                if self.known.get(rel) == stamp:
                    continue
                if len(writes) >= BATCH_FILES or size >= BATCH_BYTES:
                    break
                try:
                    raw = (root / rel).read_bytes()
                except OSError:
                    self.known[rel] = stamp  # unreadable: leave it alone
                    continue
                size += len(raw)
                try:
                    writes.append({"path": rel, "content": raw.decode("utf-8")})
                except UnicodeDecodeError:
                    writes.append({"path": rel, "base64": base64.b64encode(raw).decode("ascii")})
                stamps[rel] = stamp
            if not writes and not deletes:
                return None
            self.pending = {"id": secrets.token_urlsafe(6), "writes": writes, "deletes": deletes, "stamps": stamps}
        return {key: self.pending[key] for key in ("id", "writes", "deletes")}

    def acknowledge(self, batch_id: object) -> None:
        """The browser finished writing that batch (files it could not write are not retried forever)."""
        batch = self.pending
        if batch is None or batch["id"] != batch_id:
            return
        self.known.update(batch["stamps"])
        for path in batch["deletes"]:
            self.known.pop(path, None)
        self.pending = None


def clean_location(text: object) -> str:
    """The folder's path on the user's computer as the user typed it, with forward slashes. It is only shown, never used for file access."""
    if not isinstance(text, str):
        return ""
    cleaned = re.sub(r"[\x00-\x1f]", "", text).strip().strip("\"'").replace("\\", "/")
    return re.sub(r"/{2,}", "/", cleaned).rstrip("/")[:200]


def sidecar_path(root: Path) -> Path:
    """Where the link details are kept: next to the workspace copy, never inside it, so they never sync to the user's folder."""
    return root.parent / f".{root.name}.rk.json"


def load_sidecar(root: Path) -> dict:
    try:
        data = json.loads(sidecar_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def update_sidecar(root: Path, **changes: object) -> dict:
    data = load_sidecar(root)
    data.update(changes)
    try:
        sidecar_path(root).write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass
    return data


def clean_listing(items: object) -> list[dict]:
    """The files the browser found but did not copy, as {path, size, why}. Malformed entries are dropped."""
    if not isinstance(items, list):
        return []
    cleaned: list[dict] = []
    for item in items[:LISTED_LIMIT]:
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        if not isinstance(path, str) or not path or "\x00" in path or len(path) > 500:
            continue
        parts = path.replace("\\", "/").strip("/").split("/")
        if any(part in {"", ".", ".."} for part in parts):
            continue
        size = item.get("size")
        why = item.get("why")
        cleaned.append({
            "path": "/".join(parts),
            "size": int(size) if isinstance(size, (int, float)) and size >= 0 else 0,
            "why": why[:80] if isinstance(why, str) and why else "not copied",
        })
    return cleaned


def listed_entries(listed: list[dict], cwd: str) -> list[dict]:
    """The not-copied files directly inside folder `cwd`, shaped like `list_dir` entries, plus the folders that only exist for them."""
    prefix = f"{cwd}/" if cwd else ""
    entries: dict[str, dict] = {}
    for item in listed:
        path = item["path"]
        if not path.startswith(prefix):
            continue
        head, sep, _ = path[len(prefix):].partition("/")
        if not head:
            continue
        if sep:
            full = prefix + head
            entries.setdefault(full, {"name": head, "path": full, "type": "dir", "size": 0, "ignored": False, "language": None, "listed": True, "why": ""})
        else:
            entries[path] = {"name": head, "path": path, "type": "file", "size": item["size"], "ignored": False, "language": None, "listed": True, "why": item["why"]}
    return list(entries.values())
