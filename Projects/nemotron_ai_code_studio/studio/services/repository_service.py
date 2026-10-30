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
from .git_service import GitError, GitService, clone_repository
from .github_service import GitHubError, GitHubService, RepoRef, parse_repository
from .indexing_service import RepositoryIndex
from .search_service import SearchService
from .terminal_service import TerminalService
from .workspace_service import WorkspaceService

STATE_FILE = PROJECT_ROOT / ".studio_state.json"


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
    def __init__(self) -> None:
        self._active: ActiveRepository | None = None
        self._lock = threading.Lock()

    # ---------------------------------------------------------------- state
    @property
    def active(self) -> ActiveRepository | None:
        return self._active

    def require(self) -> ActiveRepository:
        if self._active is None:
            raise RepositoryError("No repository is connected. Connect a GitHub repository or open a workspace folder first.", 409)
        return self._active

    def _remember(self, path: Path, github: dict[str, Any]) -> None:
        try:
            STATE_FILE.write_text(json.dumps({"path": str(path), "github": github}), encoding="utf-8")
        except OSError:
            pass

    def _activate(self, path: Path, name: str, github: dict[str, Any] | None = None) -> ActiveRepository:
        workspace = WorkspaceService(path)
        is_git = _is_git(path)
        git = GitService(path) if is_git else None
        index = RepositoryIndex(workspace, git)
        index.build()
        repo = ActiveRepository(
            name=name, path=path.resolve(), is_git=is_git, workspace=workspace, git=git, index=index,
            search=SearchService(workspace, index), context=ContextEngine(index, workspace, name),
            terminal=TerminalService(path), github=github or {},
        )
        with self._lock:
            self._active = repo
        self._remember(path, repo.github)
        return repo

    # ---------------------------------------------------------------- connect
    def connect_github(self, repository: str, branch: str | None = None) -> ActiveRepository:
        """Validate the token, clone (or reuse) the repository inside WORKSPACE_PATH and index it. Blocking."""
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
        root = settings.workspace_path
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
        return self._activate(destination, info["full_name"], github)

    @staticmethod
    def _destination(root: Path, ref: RepoRef) -> Path:
        try:
            return resolve_in_root(root, ref.folder, allow_root=False)
        except PathSecurityError as exc:
            raise RepositoryError(str(exc), 400) from exc

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

    # ---------------------------------------------------------------- local workspace
    def list_workspaces(self) -> list[dict[str, Any]]:
        root = settings.workspace_path
        found: list[dict[str, Any]] = []
        if not root.is_dir():
            return found
        if _is_git(root):
            found.append({"name": root.name, "folder": "", "is_git": True})
        for child in sorted(root.iterdir(), key=lambda item: item.name.lower()):
            if child.is_dir() and not child.name.startswith("."):
                found.append({"name": child.name, "folder": child.name, "is_git": _is_git(child)})
        return found

    def open_local(self, folder: str) -> ActiveRepository:
        """Open a folder that lives inside WORKSPACE_PATH ('' opens WORKSPACE_PATH itself)."""
        root = settings.workspace_path
        try:
            path = resolve_in_root(root, folder or "")
        except PathSecurityError as exc:
            raise RepositoryError(str(exc), 400) from exc
        if not path.is_dir():
            raise RepositoryError("That workspace folder does not exist.", 404)
        return self._activate(path, path.name)

    def restore_last(self) -> ActiveRepository | None:
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            path = Path(data["path"]).resolve()
            resolve_in_root(settings.workspace_path, str(path.relative_to(settings.workspace_path)))
        except (OSError, ValueError, KeyError, PathSecurityError):
            return None
        if not path.is_dir():
            return None
        github = data.get("github") if isinstance(data.get("github"), dict) else {}
        return self._activate(path, github.get("full_name") or path.name, github)

    def disconnect(self) -> None:
        with self._lock:
            self._active = None
        try:
            STATE_FILE.unlink()
        except OSError:
            pass


repositories = RepositoryService()
