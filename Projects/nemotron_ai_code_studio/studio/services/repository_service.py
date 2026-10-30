"""Connects to a GitHub repository (or opens a local workspace folder) and holds everything tied to the active repository."""

from __future__ import annotations

import json
import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import PROJECT_ROOT, settings
from ..security import PathSecurityError, resolve_in_root
from .change_tracker import ChangeTracker
from .context_service import ContextEngine
from .folders import FolderError, prepare_location
from .git_service import GitError, GitService, clone_repository
from .github_service import GitHubError, GitHubService, RepoRef, parse_repository
from .indexing_service import RepositoryIndex
from .search_service import SearchService
from .terminal_service import TerminalService
from .workspace_service import WorkspaceService

STATE_FILE = PROJECT_ROOT / ".studio_state.json"
PREFS_FILE = PROJECT_ROOT / ".studio_prefs.json"


class RepositoryError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


@dataclass
class ActiveRepository:
    name: str
    path: Path
    is_git: bool
    workspace: WorkspaceService
    git: GitService | None
    index: RepositoryIndex
    search: SearchService
    context: ContextEngine
    terminal: TerminalService
    tracker: ChangeTracker = field(default_factory=ChangeTracker)
    github: dict[str, Any] = field(default_factory=dict)
    lock: threading.RLock = field(default_factory=threading.RLock)
    scratch: bool = False  # True for a plain folder that is not a connected GitHub repository

    def info(self) -> dict[str, Any]:
        branch, remote = "", ""
        if self.git is not None:
            try:
                branch, remote = self.git.current_branch(), self.git.remote_url()
            except GitError:
                pass
        return {
            "name": self.name, "path": str(self.path), "is_git": self.is_git, "branch": branch, "remote": remote,
            "github": self.github, "index": self.index.summary(),
        }

    def reindex(self) -> None:
        self.index.build()


def _is_git(path: Path) -> bool:
    return (path / ".git").exists()


class RepositoryService:
    """Opens folders and clones repositories. Nothing here is global: every browser window owns the workspace it opened."""

    def __init__(self) -> None:
        self._lock = threading.Lock()

    # ---------------------------------------------------------------- windows
    # Each browser window has an id (in the page address). The folder a window works in is remembered under that id,
    # so a reload reopens it and a new window never shares or replaces another window's folder.
    def _read_windows(self) -> dict[str, Any]:
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) and isinstance(data.get("windows"), dict) else {}

    def remember(self, window: str, path: Path, github: dict[str, Any] | None = None, scratch: bool = False,
                 link: str = "", fresh: bool = False) -> None:
        """`link` is the name of the folder on the user's computer this window mirrors; `fresh` means it still has to receive every file."""
        with self._lock:
            data = self._read_windows()
            windows = {key: value for key, value in data.get("windows", {}).items() if key != window}
            windows[window] = {"path": str(path), "github": github or {}, "scratch": scratch, "link": link, "fresh": bool(link and fresh)}
            windows = dict(list(windows.items())[-40:])
            try:
                STATE_FILE.write_text(json.dumps({"windows": windows, "last": window}), encoding="utf-8")
            except OSError:
                pass

    def window_link(self, window: str) -> tuple[str, bool]:
        """(name of the linked folder on the user's computer, still has to receive every file) for a window."""
        entry = self._read_windows().get("windows", {}).get(window)
        if not isinstance(entry, dict) or not isinstance(entry.get("link"), str):
            return "", False
        return entry["link"], bool(entry.get("fresh"))

    def mark_synced(self, window: str) -> None:
        with self._lock:
            data = self._read_windows()
            entry = data.get("windows", {}).get(window)
            if isinstance(entry, dict) and entry.get("fresh"):
                entry["fresh"] = False
                try:
                    STATE_FILE.write_text(json.dumps(data), encoding="utf-8")
                except OSError:
                    pass

    def last_window(self) -> str | None:
        last = self._read_windows().get("last")
        return last if isinstance(last, str) and last else None

    def recall(self, window: str) -> ActiveRepository | None:
        """Reopen what this window had open, or None when it is new or the folder is gone."""
        entry = self._read_windows().get("windows", {}).get(window)
        if not isinstance(entry, dict):
            return None
        try:
            path = Path(entry["path"]).resolve()
        except (KeyError, TypeError, OSError):
            return None
        if not path.is_dir():
            return None
        github = entry.get("github") if isinstance(entry.get("github"), dict) else {}
        scratch = bool(entry.get("scratch"))
        return self._activate(path, github.get("full_name") or path.name, github, scratch)

    # ---------------------------------------------------------------- where repositories live
    def load_prefs(self) -> None:
        """Use the folder the user picked last time (call once when the app starts)."""
        try:
            data = json.loads(PREFS_FILE.read_text(encoding="utf-8"))
            chosen = Path(data["workspace_root"])
        except (OSError, ValueError, KeyError, TypeError):
            return
        if chosen.is_dir():
            settings.set_workspace_path(chosen)

    @property
    def location_chosen(self) -> bool:
        """True once the user picked a folder (or the deployment set WORKSPACE_PATH)."""
        return settings.workspace_configured

    def _set_location(self, path: Path) -> None:
        settings.set_workspace_path(path)
        try:
            PREFS_FILE.write_text(json.dumps({"workspace_root": str(path)}), encoding="utf-8")
        except OSError:
            pass

    def choose_location(self, text: str) -> Path:
        """Validate the folder the user typed or browsed to, create it if needed, and remember it for the next clone."""
        try:
            path = prepare_location(text)
        except FolderError as exc:
            raise RepositoryError(str(exc), 400) from exc
        self._set_location(path)
        return path

    def _activate(self, path: Path, name: str, github: dict[str, Any] | None = None, scratch: bool = False) -> ActiveRepository:
        workspace = WorkspaceService(path)
        is_git = _is_git(path)
        git = GitService(path) if is_git else None
        index = RepositoryIndex(workspace, git)
        index.build()
        return ActiveRepository(
            name=name, path=path.resolve(), is_git=is_git, workspace=workspace, git=git, index=index,
            search=SearchService(workspace, index), context=ContextEngine(index, workspace, name),
            terminal=TerminalService(path), github=github or {}, scratch=scratch,
        )

    # ---------------------------------------------------------------- work without a repository
    def open_scratch(self, text: str | None = None) -> ActiveRepository:
        """A plain folder to create and run files in (no GitHub). Without a path it uses the default scratch folder."""
        try:
            if text and text.strip():
                path = prepare_location(text)
            else:
                path = settings.scratch_path
                path.mkdir(parents=True, exist_ok=True)
        except (FolderError, OSError) as exc:
            raise RepositoryError(str(exc), 400) from exc
        return self._activate(path, path.name, scratch=True)

    # ---------------------------------------------------------------- connect
    def clone_github(self, repository: str, branch: str | None = None, root: Path | None = None) -> tuple[Path, dict[str, Any]]:
        """Validate the token, then clone (or reuse) the repository inside `root` (the folder the user picked). Blocking.

        Returns the repository folder and the GitHub details. It is not opened here: the caller opens it in its own window."""
        try:
            ref = parse_repository(repository)
            service = GitHubService()
            token_user = ""
            if settings.github_token:
                token_user = service.validate_token()["login"]
            info = service.get_repository(ref)
        except GitHubError as exc:
            raise RepositoryError(exc.message, exc.status) from exc
        wanted = (branch or "").strip() or None
        root = root or settings.workspace_path
        root.mkdir(parents=True, exist_ok=True)
        destination = self._destination(root, ref)
        created = False
        try:
            if destination.exists():
                self._reuse(destination, ref)
            else:
                created = True
                clone_repository(ref.clone_url, destination, wanted, settings.github_token or None)
            git = GitService(destination)
            if wanted and git.current_branch() != wanted:
                git.checkout(wanted)
        except GitError as exc:
            if created and destination.exists():
                shutil.rmtree(destination, ignore_errors=True)
            raise RepositoryError(exc.message, exc.status) from exc
        github = {
            "full_name": info["full_name"], "default_branch": info["default_branch"], "private": info["private"],
            "can_push": info["can_push"], "user": token_user,
        }
        return destination, github

    @staticmethod
    def _destination(root: Path, ref: RepoRef) -> Path:
        """<chosen folder>/<repo name>, like a plain `git clone`; owner__repo is the fallback when that name is taken by something else."""
        for name in (ref.name, ref.folder):
            try:
                destination = resolve_in_root(root, name, allow_root=False)
            except PathSecurityError as exc:
                raise RepositoryError(str(exc), 400) from exc
            if not destination.exists():
                return destination
            if _is_git(destination):
                remote = GitService(destination).remote_url().lower().rstrip("/").removesuffix(".git")
                if remote.endswith(f"github.com/{ref.owner}/{ref.name}".lower()):
                    return destination
        raise RepositoryError(f"The folder '{ref.name}' already exists in {root} and is not a clone of {ref.owner}/{ref.name}. Pick another location.", 409)

    @staticmethod
    def _reuse(destination: Path, ref: RepoRef) -> None:
        if not _is_git(destination):
            raise RepositoryError(f"The folder '{destination.name}' already exists in the workspace and is not a Git repository.", 409)
        remote = GitService(destination).remote_url().lower().rstrip("/").removesuffix(".git")
        if not remote.endswith(f"github.com/{ref.owner}/{ref.name}".lower()):
            raise RepositoryError(f"The folder '{destination.name}' already exists and points to a different repository.", 409)
        try:
            GitService(destination).fetch()
        except GitError:
            pass  # offline or no access: the existing clone is still usable

repositories = RepositoryService()
