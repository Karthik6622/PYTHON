"""Folder browsing for the "where should the repository be cloned" picker (runs on the machine that hosts the app)."""

from __future__ import annotations

import importlib.util
import os
import string
import subprocess
import sys
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


_PICKER = (
    "import sys, tkinter as tk\n"
    "from tkinter import filedialog\n"
    "root = tk.Tk(); root.withdraw()\n"
    "try: root.attributes('-topmost', True)\n"
    "except Exception: pass\n"
    "root.update()\n"
    "print(filedialog.askdirectory(parent=root, title=sys.argv[1], initialdir=sys.argv[2] or None, mustexist=False) or '')\n"
    "root.destroy()\n"
)


def native_picker_available() -> bool:
    """True when this process runs on the user's own desktop, so the operating system's folder dialog can be shown.

    A hosted deployment (Streamlit Cloud, Docker, a Linux server without a display) can never open a dialog on the visitor's computer.
    """
    if os.environ.get("NATIVE_FOLDER_DIALOG", "").strip().lower() in {"0", "false", "no", "off"}:
        return False
    if importlib.util.find_spec("tkinter") is None:
        return False
    return os.name == "nt" or sys.platform == "darwin" or bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def pick_folder_native(initial: str = "", title: str = "Choose where to save the repository") -> str | None:
    """Shows the Windows/macOS/Linux folder dialog (in a child process, so it cannot disturb the web server). None when cancelled."""
    start = ""
    try:
        if initial.strip():
            candidate = parse_location(initial)
            while not candidate.is_dir() and not _is_root(candidate):
                candidate = candidate.parent
            start = str(candidate)
    except FolderError:
        start = ""
    try:
        done = subprocess.run([sys.executable, "-c", _PICKER, title, start], capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.SubprocessError) as exc:
        raise FolderError(f"The folder dialog could not be opened: {exc}") from exc
    if done.returncode != 0:
        raise FolderError("The folder dialog could not be opened on this machine.")
    chosen = done.stdout.strip().splitlines()[-1].strip() if done.stdout.strip() else ""
    return str(Path(chosen)) if chosen else None


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
