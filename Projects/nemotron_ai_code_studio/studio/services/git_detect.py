"""Deterministic Git detection for a folder the user connected (no AI, no guessing from the file listing).

A folder is a Git repository only when `git -C <folder> rev-parse --is-inside-work-tree` succeeds and prints `true`. That
covers repositories, linked worktrees and sub-folders of a repository, which a plain ".git exists" check would miss.
Every command is run with an argument list (never through a shell), so a path with spaces or special characters is safe."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from ..security import redact

TIMEOUT_SECONDS = 15
_REMOTE_SLUG = re.compile(r"[:/]([\w.-]+)/([\w.-]+?)(?:\.git)?/?$")
_CREDENTIALS_IN_URL = re.compile(r"^([a-z][a-z0-9+.-]*://)[^/@\s]+@", re.I)


@dataclass(frozen=True)
class GitInfo:
    """What Git itself reports about a folder. `error` is a plain message for the user and `detail` the technical text (no secrets)."""

    is_repo: bool = False
    root: Path | None = None
    name: str = ""            # repository root folder name
    remote_url: str = ""      # origin, without any credentials
    remote_slug: str = ""     # owner/repo taken from the origin URL, when it has that shape
    branch: str = ""          # current branch; empty when HEAD is detached
    detached: bool = False
    head: str = ""            # short commit id of HEAD (empty before the first commit)
    has_commits: bool = False
    changes: int = 0          # entries reported by `git status --porcelain`
    git_available: bool = True
    error: str = ""
    detail: str = field(default="", repr=False)

    @property
    def branch_label(self) -> str:
        if self.detached:
            return f"detached at {self.head}" if self.head else "detached HEAD"
        return self.branch or "(no branch)"

    @property
    def display_name(self) -> str:
        """The repository root folder name, or the origin's repository name when the folder has none."""
        if self.name:
            return self.name
        return self.remote_slug.rsplit("/", 1)[-1] if self.remote_slug else ""


def strip_credentials(url: str) -> str:
    """The URL without the `user:token@` part, so it is safe to show and log."""
    return _CREDENTIALS_IN_URL.sub(r"\1", url.strip())


def remote_slug(url: str) -> str:
    match = _REMOTE_SLUG.search(url or "")
    return f"{match.group(1)}/{match.group(2)}" if match else ""


def _environment() -> dict[str, str]:
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_OPTIONAL_LOCKS"] = "0"  # a status check must not take the index lock away from a running commit
    env["LC_ALL"] = "C"
    return env


def run_git(path: Path, *args: str, timeout: int = TIMEOUT_SECONDS) -> tuple[int, str, str]:
    """(exit code, stdout, stderr) of `git -C <path> <args>`. Raises FileNotFoundError when Git is not installed."""
    command = ["git", "-C", str(path), *args]
    kwargs: dict = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        done = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
            stdin=subprocess.DEVNULL, env=_environment(), **kwargs,
        )
    except subprocess.TimeoutExpired:
        return 124, "", f"git {args[0] if args else ''} did not finish within {timeout} seconds"
    return done.returncode, done.stdout, done.stderr


def _folder_problem(path: Path) -> str:
    if not path.exists():
        return "The selected folder no longer exists. It may have been moved or deleted."
    if not path.is_dir():
        return "The selected path is not a folder."
    try:
        with os.scandir(path):
            pass
    except PermissionError:
        return "Permission was denied for this folder."
    except OSError as exc:
        return f"This folder cannot be read: {exc.strerror or exc}"
    return ""


def inspect_folder(path: Path | str) -> GitInfo:
    """Ask Git whether `path` is inside a working tree and collect the repository details."""
    folder = Path(path)
    problem = _folder_problem(folder)
    if problem:
        return GitInfo(error=problem)
    if shutil.which("git") is None:
        return GitInfo(git_available=False, error="Git is not installed or is not on PATH, so Git features are unavailable.")
    try:
        code, out, err = run_git(folder, "rev-parse", "--is-inside-work-tree")
    except FileNotFoundError:
        return GitInfo(git_available=False, error="Git is not installed or is not on PATH, so Git features are unavailable.")
    except OSError as exc:
        return GitInfo(error="Git could not be started.", detail=redact(str(exc)))
    if code != 0:
        lowered = err.lower()
        if "not a git repository" in lowered:
            return GitInfo()  # an ordinary folder: no error, simply no repository
        if "dubious ownership" in lowered or "safe.directory" in lowered:
            return GitInfo(
                error="Git refuses to open this folder because it belongs to another user. Add it to Git's safe directories to use it.",
                detail=redact(err.strip()),
            )
        return GitInfo(error="Git could not read this folder.", detail=redact(err.strip()))
    if out.strip() != "true":
        return GitInfo()  # inside a .git directory or a bare repository: there is no working tree

    code, top, err = run_git(folder, "rev-parse", "--show-toplevel")
    root = Path(top.strip()) if code == 0 and top.strip() else folder

    def read(*args: str) -> tuple[int, str]:
        try:
            result = run_git(folder, *args)
        except OSError:
            return 1, ""
        return result[0], result[1].strip()

    with ThreadPoolExecutor(max_workers=4) as pool:
        remote = pool.submit(read, "remote", "get-url", "origin")
        branch = pool.submit(read, "branch", "--show-current")
        head = pool.submit(read, "rev-parse", "--verify", "--quiet", "--short", "HEAD")
        status = pool.submit(run_git, folder, "status", "--porcelain")
        remote_code, remote_text = remote.result()
        _, branch_text = branch.result()
        head_code, head_text = head.result()
        try:
            status_code, status_out, _ = status.result()
        except OSError:
            status_code, status_out = 1, ""

    url = strip_credentials(remote_text) if remote_code == 0 else ""
    has_commits = head_code == 0 and bool(head_text)
    return GitInfo(
        is_repo=True,
        root=root,
        name=root.name or folder.name,
        remote_url=redact(url),
        remote_slug=remote_slug(url),
        branch=branch_text,
        detached=has_commits and not branch_text,
        head=head_text if has_commits else "",
        has_commits=has_commits,
        changes=len([line for line in status_out.splitlines() if line.strip()]) if status_code == 0 else 0,
    )


def connection_state(opened: bool, info: GitInfo, github: str) -> str:
    """Which of the five interface states applies.

    A: no folder.  B: ordinary folder.  C: Git repository, GitHub not connected.  D: Git repository, GitHub connected.
    E: an error to explain (Git or the folder cannot be used, or GitHub refused the credentials).
    `github` is "connected", "failed" or "disconnected", as validated by the backend."""
    if not opened:
        return "A"
    if info.error:
        return "E"
    if not info.is_repo:
        return "B"
    if github == "failed":
        return "E"
    return "D" if github == "connected" else "C"
