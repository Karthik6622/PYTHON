"""Folder browsing for the "where should the repository be cloned" picker (runs on the machine that hosts the app)."""

from __future__ import annotations

import os
import string
from pathlib import Path


class FolderError(Exception):
    pass


def _is_root(path: Path) -> bool:
    return path == path.parent


def parse_location(text: str) -> Path:
    """An absolute folder path typed or picked by the user. ~ is expanded; relative paths are rejected."""
    raw = (text or "").strip().strip('"').strip("'")
    if not raw:
        raise FolderError("Choose a folder for the clone first.")
    path = Path(os.path.expandvars(raw)).expanduser()
    if not path.is_absolute():
        raise FolderError("Enter a full path, for example C:\\Users\\you\\projects or /home/you/projects.")
    return path.resolve()


def prepare_location(text: str) -> Path:
    """Validates the folder, creating it when it does not exist yet, and checks that it can be written to."""
    path = parse_location(text)
    if _is_root(path):
        raise FolderError("Pick a folder inside the drive, not the drive root itself.")
    if path.exists() and not path.is_dir():
        raise FolderError("That path is a file, not a folder.")
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise FolderError(f"Could not create that folder: {exc.strerror or exc}") from exc
    if not os.access(path, os.W_OK):
        raise FolderError("You do not have permission to write to that folder.")
    return path


def list_folders(text: str) -> dict:
    """Sub-folders of a folder (hidden ones skipped). An empty path lists the drives (Windows) or the root."""
    raw = (text or "").strip()
    if not raw and os.name == "nt":
        drives = [f"{letter}:\\" for letter in string.ascii_uppercase if Path(f"{letter}:\\").exists()]
        return {"path": "", "parent": None, "folders": [{"name": d, "path": d} for d in drives]}
    path = parse_location(raw or "/")
    while not path.is_dir() and not _is_root(path):
        path = path.parent
    folders: list[dict] = []
    try:
        for entry in sorted(os.scandir(path), key=lambda item: item.name.lower()):
            if entry.name.startswith(".") or entry.name.startswith("$"):
                continue
            try:
                if entry.is_dir(follow_symlinks=False):
                    folders.append({"name": entry.name, "path": str(Path(entry.path))})
            except OSError:
                continue
    except OSError:
        pass
    parent = None if _is_root(path) and os.name != "nt" else ("" if _is_root(path) else str(path.parent))
    return {"path": str(path), "parent": parent, "folders": folders}


def quick_places() -> list[tuple[str, str]]:
    """Handy starting points that exist on this machine."""
    home = Path.home()
    places = [("Home", home)]
    for name in ("Desktop", "Documents", "Downloads", "source", "projects", "Projects"):
        candidate = home / name
        if candidate.is_dir():
            places.append((name, candidate))
    return [(label, str(path)) for label, path in places]


def make_folder(parent: str, name: str) -> Path:
    clean = (name or "").strip()
    if not clean or clean in {".", ".."} or any(ch in clean for ch in '\\/:*?"<>|'):
        raise FolderError("Use a simple folder name without slashes or special characters.")
    path = parse_location(parent) / clean
    try:
        path.mkdir(parents=False, exist_ok=True)
    except OSError as exc:
        raise FolderError(f"Could not create the folder: {exc.strerror or exc}") from exc
    return path
