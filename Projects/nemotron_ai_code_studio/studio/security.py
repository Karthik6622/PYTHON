"""Path confinement and secret redaction shared by every service."""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath, PureWindowsPath

from .config import settings


class PathSecurityError(ValueError):
    """A path tried to leave the repository workspace or touch a protected location."""


def resolve_in_root(root: Path, relative: str, *, allow_root: bool = True) -> Path:
    """Resolve a repository-relative path and guarantee it stays inside root (symlinks included).

    Rejects absolute paths, drive letters, UNC paths, NUL bytes and any ../ that escapes the workspace.
    """
    if not isinstance(relative, str):
        raise PathSecurityError("Path must be text.")
    if "\x00" in relative:
        raise PathSecurityError("Path contains a NUL byte.")
    cleaned = relative.replace("\\", "/").strip()
    if cleaned.startswith("/") or PureWindowsPath(cleaned).drive or PureWindowsPath(cleaned).is_absolute():
        raise PathSecurityError("Absolute paths are not allowed; use a path relative to the repository.")
    root_resolved = root.resolve()
    candidate = (root_resolved / PurePosixPath(cleaned)).resolve() if cleaned not in {"", "."} else root_resolved
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise PathSecurityError("Path is outside the repository workspace.") from exc
    if candidate == root_resolved and not allow_root:
        raise PathSecurityError("The repository root cannot be used here.")
    return candidate


def relative_posix(root: Path, path: Path) -> str:
    """Repository-relative path with forward slashes ('' for the root)."""
    rel = path.resolve().relative_to(root.resolve())
    return "" if str(rel) == "." else rel.as_posix()


def is_protected(root: Path, path: Path) -> bool:
    """The .git directory is managed by Git only; file tools must not edit it."""
    try:
        parts = path.resolve().relative_to(root.resolve()).parts
    except ValueError:
        return True
    return bool(parts) and parts[0].lower() == ".git"


_TOKEN_PATTERNS = [
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"nvapi-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?i)(authorization:\s*(?:basic|bearer)\s+)[A-Za-z0-9+/=._\-]{12,}"),
    re.compile(r"(?i)(https?://)[^/\s:@]+:[^/\s@]+@"),
]


def redact(text: str) -> str:
    """Remove configured secrets and anything that looks like a token from text shown to users or the model."""
    if not text:
        return text
    for secret in settings.secret_values():
        text = text.replace(secret, "[REDACTED]")
    text = _TOKEN_PATTERNS[0].sub("[REDACTED]", text)
    text = _TOKEN_PATTERNS[1].sub("[REDACTED]", text)
    text = _TOKEN_PATTERNS[2].sub("[REDACTED]", text)
    text = _TOKEN_PATTERNS[3].sub(r"\1[REDACTED]", text)
    text = _TOKEN_PATTERNS[4].sub(r"\1[REDACTED]@", text)
    return text


_SENSITIVE_NAME = re.compile(
    r"(^\.env(\..+)?$|\.pem$|\.key$|\.p12$|\.pfx$|^id_(rsa|dsa|ecdsa|ed25519)(\.pub)?$|^\.npmrc$|^\.pypirc$|^credentials(\.json)?$)", re.I
)
_ENV_TEMPLATES = {".env.example", ".env.sample", ".env.template", ".env.dist"}


def is_sensitive_path(path: str) -> bool:
    """Files that usually hold secrets (.env, private keys). The agent and the index never read them."""
    name = PurePosixPath(path.replace("\\", "/")).name
    return name.lower() not in _ENV_TEMPLATES and bool(_SENSITIVE_NAME.search(name))


_BRANCH_RE = re.compile(r"^(?!-)(?!.*\.\.)(?!.*//)[A-Za-z0-9._/\-]{1,200}(?<![/.])$")


def valid_branch_name(name: str) -> bool:
    return bool(isinstance(name, str) and _BRANCH_RE.match(name) and not name.endswith(".lock") and "@{" not in name)
