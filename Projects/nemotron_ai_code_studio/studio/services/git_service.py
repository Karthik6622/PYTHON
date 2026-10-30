"""Git operations through GitPython. Remote operations authenticate with an HTTP header passed through the environment,
so the token is never written into the remote URL, the git config or a process argument list."""

from __future__ import annotations

import base64
import difflib
import re
import time
from pathlib import Path
from typing import Any

from git import GitCommandError, InvalidGitRepositoryError, NoSuchPathError, Repo

from ..config import settings
from ..security import PathSecurityError, redact, resolve_in_root, valid_branch_name

_READ_ONLY = {"status", "diff", "log", "show", "rev-parse", "rev-list", "ls-files", "cat-file", "for-each-ref", "config"}

COMMIT_FALLBACK_NAME = "RK Studio"
COMMIT_FALLBACK_EMAIL = "studio@localhost"


class GitError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def auth_env(token: str | None = None) -> dict[str, str]:
    """Environment that lets git talk to github.com with the token, without ever prompting."""
    env = {"GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}
    token = token if token is not None else settings.github_token
    if token:
        encoded = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        env.update({
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
            "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {encoded}",
        })
    return env


def _explain(exc: GitCommandError) -> str:
    text = redact(" ".join(str(exc.stderr or exc.stdout or exc).split()))
    text = re.sub(r"^(?:Cmd\(\[?.*?\]\)\s*)?(?:failed!\s*)?(?:cmdline:.*?)?stderr:\s*", "", text)
    return text.strip("'\" ")[:600] or "Git command failed."


def clone_repository(url: str, destination: Path, branch: str | None, token: str | None) -> None:
    try:
        Repo.clone_from(url, str(destination), env=auth_env(token), **({"branch": branch} if branch else {}))
    except GitCommandError as exc:
        raise GitError(_explain(exc), 400) from exc


class GitService:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self._cache: tuple[Any, float, dict[str, Any]] | None = None

    def cached_status(self, token: Any = None, max_age: float = 4.0) -> dict[str, Any]:
        """status() for the status bar, which re-renders on every click: reuse it for a few seconds unless something changed."""
        now = time.monotonic()
        cache = self._cache
        if cache is not None and cache[0] == token and now - cache[1] < max_age:
            return cache[2]
        value = self.status()
        self._cache = (token, now, value)
        return value

    def invalidate(self) -> None:
        self._cache = None

    # ---------------------------------------------------------------- plumbing
    @property
    def repo(self) -> Repo:
        try:
            return Repo(str(self.root))
        except (InvalidGitRepositoryError, NoSuchPathError) as exc:
            raise GitError("This workspace is not a Git repository.", 400) from exc

    def _paths(self, paths: list[str]) -> list[str]:
        clean = []
        for item in paths:
            try:
                resolved = resolve_in_root(self.root, item, allow_root=False)
            except PathSecurityError as exc:
                raise GitError(str(exc), 400) from exc
            clean.append(resolved.relative_to(self.root).as_posix())
        return clean

    def _run(self, repo: Repo, *args: str, network: bool = False) -> str:
        if args and args[0] not in _READ_ONLY:
            self._cache = None  # anything that can change the repository invalidates the cached status
        try:
            if network:
                with repo.git.custom_environment(**auth_env()):
                    return repo.git.execute(["git", *args])
            return repo.git.execute(["git", *args])
        except GitCommandError as exc:
            raise GitError(_explain(exc), 400) from exc

    # ---------------------------------------------------------------- inspection
    def current_branch(self) -> str:
        repo = self.repo
        try:
            return repo.active_branch.name
        except TypeError:
            return "HEAD (detached)"
        except ValueError:
            return "(no commits)"

    def remote_url(self) -> str:
        repo = self.repo
        try:
            return redact(repo.remotes.origin.url)
        except (AttributeError, IndexError):
            return ""

    def has_commits(self) -> bool:
        try:
            return self.repo.head.is_valid()
        except Exception:
            return False

    def status(self) -> dict[str, Any]:
        repo = self.repo
        output = self._run(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all", "-b")
        tokens = [token for token in output.split("\0") if token != ""]
        branch, upstream, ahead, behind = "", "", 0, 0
        if tokens and tokens[0].startswith("## "):
            header = tokens.pop(0)[3:]
            counts = re.search(r"\[(.*?)\]\s*$", header)
            if counts:
                ahead_match = re.search(r"ahead (\d+)", counts.group(1))
                behind_match = re.search(r"behind (\d+)", counts.group(1))
                ahead = int(ahead_match.group(1)) if ahead_match else 0
                behind = int(behind_match.group(1)) if behind_match else 0
                header = header[: counts.start()].strip()
            if header.startswith("No commits yet on "):
                branch = header[len("No commits yet on "):]
            elif "..." in header:
                branch, upstream = header.split("...", 1)
            else:
                branch = header
        files: list[dict[str, Any]] = []
        index = 0
        while index < len(tokens):
            entry = tokens[index]
            index += 1
            if len(entry) < 4:
                continue
            x, y, path = entry[0], entry[1], entry[3:]
            original = None
            if x in "RC" and index < len(tokens):
                original = tokens[index]
                index += 1
            if x == "?" and y == "?":
                kind, staged, unstaged = "untracked", False, True
            elif "U" in (x, y) or (x, y) in {("A", "A"), ("D", "D")}:
                kind, staged, unstaged = "conflicted", False, True
            else:
                staged, unstaged = x not in " ?", y not in " ?"
                letters = {x, y}
                if "R" in letters:
                    kind = "renamed"
                elif "D" in letters:
                    kind = "deleted"
                elif "A" in letters:
                    kind = "added"
                else:
                    kind = "modified"
            files.append({
                "path": path, "kind": kind, "staged": staged, "unstaged": unstaged, "index": x, "worktree": y,
                **({"original_path": original} if original else {}),
            })
        return {"branch": branch or self.current_branch(), "upstream": upstream, "ahead": ahead, "behind": behind,
                "files": files, "clean": not files}

    def is_dirty(self) -> bool:
        return not self.status()["clean"]

    def diff(self, path: str | None = None, staged: bool = False, max_chars: int = 300_000) -> str:
        repo = self.repo
        args = ["diff", "--no-color", "--no-ext-diff"]
        if staged:
            args.append("--cached")
        pathspec: list[str] = self._paths([path]) if path else []
        text = self._run(repo, *args, *(["--", *pathspec] if pathspec else []))
        if not staged:
            text += self._untracked_diff(repo, pathspec)
        return text[:max_chars]

    def _untracked_diff(self, repo: Repo, pathspec: list[str]) -> str:
        names = repo.untracked_files
        if pathspec:
            names = [name for name in names if name in pathspec]
        parts: list[str] = []
        for name in names[:50]:
            path = self.root / name
            try:
                if not path.is_file() or path.stat().st_size > settings.max_file_bytes:
                    continue
                content = path.read_bytes()
                if b"\x00" in content[:8000]:
                    parts.append(f"Binary file {name} (new)\n")
                    continue
                lines = content.decode("utf-8", errors="replace").splitlines(keepends=True)
            except OSError:
                continue
            parts.append(f"diff --git a/{name} b/{name}\nnew file mode 100644\n")
            diff = list(difflib.unified_diff([], lines, fromfile="/dev/null", tofile=f"b/{name}"))
            parts.append("".join(line if line.endswith("\n") else line + "\n" for line in diff))
        return "".join(parts)

    def file_versions(self, path: str) -> dict[str, Any]:
        """HEAD and working-tree text of one file, for the side-by-side diff editor."""
        rel = self._paths([path])[0]
        repo = self.repo
        try:
            original = repo.git.show(f"HEAD:{rel}")
            existed = True
        except GitCommandError:
            original, existed = "", False
        target = self.root / rel
        modified = ""
        if target.is_file():
            data = target.read_bytes()[: settings.max_file_bytes]
            modified = "" if b"\x00" in data[:8000] else data.decode("utf-8", errors="replace")
        return {"path": rel, "original": original, "modified": modified, "existed_in_head": existed, "exists_now": target.is_file()}

    def log(self, count: int = 20) -> list[dict[str, Any]]:
        repo = self.repo
        if not self.has_commits():
            return []
        commits = []
        for commit in repo.iter_commits(max_count=max(1, min(count, 100))):
            commits.append({
                "sha": commit.hexsha, "short": commit.hexsha[:8], "author": str(commit.author),
                "date": commit.committed_datetime.isoformat(), "message": str(commit.message).strip().splitlines()[0] if str(commit.message).strip() else "",
            })
        return commits

    def branches(self) -> dict[str, Any]:
        repo = self.repo
        local = [head.name for head in repo.heads]
        remote: list[str] = []
        try:
            refs = list(repo.remotes.origin.refs)
        except (AttributeError, IndexError):
            refs = []
        for ref in refs:
            name = ref.name.split("/", 1)[1] if "/" in ref.name else ref.name
            if name != "HEAD":
                remote.append(name)
        return {"current": self.current_branch(), "local": sorted(local), "remote": sorted(set(remote))}

    # ---------------------------------------------------------------- changes
    def stage(self, paths: list[str] | None = None) -> None:
        repo = self.repo
        if not paths:
            self._run(repo, "add", "-A")
        else:
            self._run(repo, "add", "-A", "--", *self._paths(paths))

    def unstage(self, paths: list[str] | None = None) -> None:
        repo = self.repo
        pathspec = self._paths(paths) if paths else []
        if self.has_commits():
            self._run(repo, "reset", "-q", "HEAD", *(["--", *pathspec] if pathspec else []))
        else:
            self._run(repo, "rm", "-r", "--cached", "-q", "--", *(pathspec or ["."]))

    def discard(self, paths: list[str]) -> list[str]:
        """Throw away working-tree changes. Untracked files are deleted; tracked files go back to HEAD."""
        repo = self.repo
        discarded: list[str] = []
        untracked = set(repo.untracked_files)
        for rel in self._paths(paths):
            target = self.root / rel
            if rel in untracked:
                if target.is_file():
                    target.unlink()
                    discarded.append(rel)
                continue
            self._run(repo, "restore", "--source=HEAD", "--staged", "--worktree", "--", rel)
            discarded.append(rel)
        return discarded

    def commit(self, message: str) -> dict[str, Any]:
        message = (message or "").strip()
        if not message:
            raise GitError("A commit message is required.", 400)
        if len(message) > 5000:
            raise GitError("The commit message is too long.", 400)
        repo = self.repo
        if not self._run(repo, "diff", "--cached", "--name-only").strip():
            raise GitError("Nothing is staged. Stage files first.", 409)
        identity: list[str] = []
        reader = repo.config_reader()
        for key, fallback in (("name", COMMIT_FALLBACK_NAME), ("email", COMMIT_FALLBACK_EMAIL)):
            try:
                configured = reader.get_value("user", key)
            except Exception:
                configured = ""
            if not configured:
                identity += ["-c", f"user.{key}={fallback}"]
        self._run(repo, *identity, "commit", "-m", message)
        head = repo.head.commit
        return {"sha": head.hexsha, "short": head.hexsha[:8], "message": message.splitlines()[0]}

    # ---------------------------------------------------------------- branches
    def create_branch(self, name: str, checkout: bool = True) -> str:
        if not valid_branch_name(name):
            raise GitError("Invalid branch name.", 400)
        repo = self.repo
        if checkout:
            self._run(repo, "checkout", "-b", name)
        else:
            self._run(repo, "branch", name)
        return name

    def checkout(self, name: str) -> str:
        if not valid_branch_name(name):
            raise GitError("Invalid branch name.", 400)
        repo = self.repo
        if name in [head.name for head in repo.heads]:
            self._run(repo, "checkout", name)
        else:
            remote_names = self.branches()["remote"]
            if name not in remote_names:
                raise GitError(f"Branch '{name}' does not exist.", 404)
            self._run(repo, "checkout", "-b", name, "--track", f"origin/{name}")
        return name

    # ---------------------------------------------------------------- remote
    def fetch(self) -> str:
        return redact(self._run(self.repo, "fetch", "--prune", "origin", network=True)) or "Fetched."

    def pull(self) -> str:
        return redact(self._run(self.repo, "pull", "--ff-only", network=True)) or "Already up to date."

    def push(self, branch: str | None = None) -> str:
        repo = self.repo
        name = branch or self.current_branch()
        if not valid_branch_name(name):
            raise GitError("Invalid branch name.", 400)
        out = self._run(repo, "push", "--set-upstream", "origin", name, network=True)
        return redact(out) or f"Pushed {name} to origin."
