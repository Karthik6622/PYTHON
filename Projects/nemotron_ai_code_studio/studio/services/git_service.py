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

from ..config import is_hosted, settings
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
    """Environment for non-interactive GitHub access.

    Browser-connected folders do not provide the visitor's SSH agent or known_hosts file. When a token is available,
    GitHub SSH remotes use that token over HTTPS; otherwise local desktop SSH keeps its normal host-key verification."""
    env = {"GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}
    config_index = 0
    token = token if token is not None else settings.github_token
    rewrite_ssh = is_hosted() or bool(token)
    if rewrite_ssh:
        env.update({
            "GIT_CONFIG_KEY_0": "url.https://github.com/.insteadOf",
            "GIT_CONFIG_VALUE_0": "git@github.com:",
            "GIT_CONFIG_KEY_1": "url.https://github.com/.insteadOf",
            "GIT_CONFIG_VALUE_1": "ssh://git@github.com/",
        })
        config_index = 2
    if token:
        encoded = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        env.update({
            f"GIT_CONFIG_KEY_{config_index}": "http.https://github.com/.extraheader",
            f"GIT_CONFIG_VALUE_{config_index}": f"AUTHORIZATION: basic {encoded}",
        })
        config_index += 1
    if config_index:
        env["GIT_CONFIG_COUNT"] = str(config_index)
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


_HEAD_REF = re.compile(r"^ref:\s*refs/heads/(\S+)\s*$", re.M)
_ORIGIN_URL = re.compile(r'\[remote\s+"origin"\][^\[]*?\burl\s*=\s*(\S+)', re.S)
_BRANCH_SECTION = re.compile(r'^\[branch\s+"([^"\r\n]+)"\]', re.M)
_GITHUB_REMOTE = re.compile(r"^(?:https://(?:[^@/\s]+@)?github\.com/|git@github\.com:|ssh://git@github\.com/)([\w.-]+)/([\w.-]+?)(?:\.git)?/?$")


def parse_git_metadata(head: object, config: object) -> tuple[str, str]:
    """(branch, GitHub https URL) from the text of a folder's .git/HEAD and .git/config; an empty string for what is not usable.

    Only GitHub remotes are accepted, and any password or token written into the URL is dropped."""
    branch = ""
    match = _HEAD_REF.search(head) if isinstance(head, str) else None
    if match and valid_branch_name(match.group(1)):
        branch = match.group(1)
    if not branch and isinstance(config, str):  # detached HEADs often still have a branch's tracking config
        configured = _BRANCH_SECTION.search(config)
        if configured and valid_branch_name(configured.group(1)):
            branch = configured.group(1)
    url = ""
    found = _ORIGIN_URL.search(config) if isinstance(config, str) else None
    if found:
        remote = _GITHUB_REMOTE.match(found.group(1).strip())
        if remote:
            url = f"https://github.com/{remote.group(1)}/{remote.group(2)}.git"
    return branch, url


def adopt_local_repository(root: Path, branch: str, remote_url: str) -> dict[str, Any]:
    """Make the server copy of a folder from the user's computer a Git repository that matches theirs.

    The browser cannot send the whole .git folder, so this starts a fresh repository on the same branch with the same `origin`,
    fetches that branch from GitHub when it is allowed to, and then points the index at it: the files then show as changed only
    where they differ from GitHub, instead of everything being new.

    Returns {"fetched": bool, "needs_login": bool}. A failed fetch is not an error: the repository is still usable."""
    outcome = {"fetched": False, "needs_login": False}
    name = branch if valid_branch_name(branch) else "main"
    try:
        repo = Repo(str(root)) if (root / ".git").exists() else Repo.init(str(root))
        if not repo.head.is_valid():
            repo.git.execute(["git", "symbolic-ref", "HEAD", f"refs/heads/{name}"])
        if not remote_url:
            return outcome
        if "origin" in [remote.name for remote in repo.remotes]:
            repo.git.execute(["git", "remote", "set-url", "origin", remote_url])
        else:
            repo.git.execute(["git", "remote", "add", "origin", remote_url])
        with repo.git.custom_environment(**auth_env()):
            repo.git.execute(["git", "-c", "gc.auto=0", "fetch", "--depth", "50", "origin", f"+refs/heads/{name}:refs/remotes/origin/{name}"])
        outcome["fetched"] = True
        if not repo.head.is_valid():  # a brand new repository: take the remote history, keep the user's files as they are
            repo.git.execute(["git", "reset", "-q", "--mixed", f"origin/{name}"])
        repo.git.execute(["git", "branch", "--set-upstream-to", f"origin/{name}", name])
    except GitCommandError as exc:
        text = " ".join(str(exc.stderr or exc).split()).lower()
        outcome["needs_login"] = any(
            phrase in text for phrase in ("could not read username", "terminal prompts disabled", "authentication failed", "repository not found", "returned error: 40")
        )
    except (OSError, InvalidGitRepositoryError, NoSuchPathError):
        pass
    return outcome


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
        # The opened folder may be a sub-folder of the repository (or a linked worktree): Git finds the real top level itself.
        try:
            return Repo(str(self.root), search_parent_directories=True)
        except (InvalidGitRepositoryError, NoSuchPathError) as exc:
            raise GitError("This workspace is not a Git repository.", 400) from exc

    @property
    def top(self) -> Path:
        """Top level of the working tree the opened folder belongs to."""
        return Path(self.repo.working_dir).resolve()

    @property
    def prefix(self) -> str:
        """The opened folder relative to the top level ("" when it is the top level itself)."""
        try:
            relative = self.root.relative_to(self.top).as_posix()
        except ValueError:
            return ""
        return "" if relative == "." else relative

    def _from_top(self, path: str) -> str:
        """A path as Git reports it (relative to the top level) as a path inside the opened folder."""
        prefix = self.prefix
        return path[len(prefix) + 1:] if prefix and path.startswith(f"{prefix}/") else path

    def _paths(self, paths: list[str]) -> list[str]:
        """Paths inside the opened folder as Git wants them: relative to the top level of the working tree."""
        prefix = self.prefix
        clean = []
        for item in paths:
            try:
                resolved = resolve_in_root(self.root, item, allow_root=False)
            except PathSecurityError as exc:
                raise GitError(str(exc), 400) from exc
            relative = resolved.relative_to(self.root).as_posix()
            clean.append(f"{prefix}/{relative}" if prefix else relative)
        return clean

    def _run(self, repo: Repo, *args: str, network: bool = False) -> str:
        if args and args[0] not in _READ_ONLY:
            self._cache = None  # anything that can change the repository invalidates the cached status
        # gc.auto=0: no automatic garbage collection after commit/fetch. On Windows it tries to delete empty .git/objects folders,
        # which fails when OneDrive or an antivirus holds them and then asks "Should I try again? (y/n)".
        command = ["git", "-c", "gc.auto=0", *args]
        try:
            if network:
                with repo.git.custom_environment(**auth_env()):
                    return repo.git.execute(command)
            return repo.git.execute(command)
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
        scope = ["--", self.prefix] if self.prefix else []
        output = self._run(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all", "-b", *scope)
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
                "path": self._from_top(path), "kind": kind, "staged": staged, "unstaged": unstaged, "index": x, "worktree": y,
                **({"original_path": self._from_top(original)} if original else {}),
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
        pathspec: list[str] = self._paths([path]) if path else ([self.prefix] if self.prefix else [])
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
            path = self.top / name
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
        target = self.top / rel
        modified = ""
        if target.is_file():
            data = target.read_bytes()[: settings.max_file_bytes]
            modified = "" if b"\x00" in data[:8000] else data.decode("utf-8", errors="replace")
        return {"path": self._from_top(rel), "original": original, "modified": modified, "existed_in_head": existed, "exists_now": target.is_file()}

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
            self._run(repo, "add", "-A", *(["--", self.prefix] if self.prefix else []))
        else:
            self._run(repo, "add", "-A", "--", *self._paths(paths))

    def unstage(self, paths: list[str] | None = None) -> None:
        repo = self.repo
        pathspec = self._paths(paths) if paths else ([self.prefix] if self.prefix else [])
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
            target = self.top / rel
            if rel in untracked:
                if target.is_file():
                    target.unlink()
                    discarded.append(self._from_top(rel))
                continue
            self._run(repo, "restore", "--source=HEAD", "--staged", "--worktree", "--", rel)
            discarded.append(self._from_top(rel))
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

    def last_commit(self) -> dict[str, Any] | None:
        """The newest commit of this branch and whether it is already on a remote branch (then it can no longer be undone here)."""
        if not self.has_commits():
            return None
        repo = self.repo
        head = repo.head.commit
        try:
            containing = repo.git.branch("-r", "--contains", head.hexsha)
        except GitCommandError:
            containing = ""
        pushed = any(line.strip() and "->" not in line for line in containing.splitlines())
        text = str(head.message).strip()
        return {"sha": head.hexsha, "short": head.hexsha[:8], "message": text.splitlines()[0] if text else "", "full_message": text, "pushed": pushed}

    def undo_last_commit(self) -> dict[str, Any]:
        """Take the newest commit back: its changes return to the staged list and its message can be edited and committed again."""
        info = self.last_commit()
        if info is None:
            raise GitError("There is no commit to undo.", 409)
        if info["pushed"]:
            raise GitError("The last commit is already on GitHub, so it cannot be undone here. Make a new commit that fixes it instead.", 409)
        repo = self.repo
        if repo.head.commit.parents:
            self._run(repo, "reset", "--soft", "HEAD~1")
        else:
            self._run(repo, "update-ref", "-d", "HEAD")  # the very first commit: the files stay staged
        return info

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
