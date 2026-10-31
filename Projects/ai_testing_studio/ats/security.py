"""Secret masking and URL safety checks.

Masking is applied to logs, execution output, reports and anything shown from model/runner output.
"""

from __future__ import annotations

import ipaddress
import re
import socket
import threading
from typing import Any
from urllib.parse import urlparse

REDACTED = "***"

_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"nvapi-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-~+/]{8,}=*"),
    re.compile(r"(?im)^(\s*(?:set-)?cookie\s*:).*$"),
    re.compile(r"(?im)^(\s*authorization\s*:).*$"),
    re.compile(r"(?i)((?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key)\s*[=:]\s*)(['\"]?)[^\s'\",;&]+"),
)

_lock = threading.Lock()
_runtime_secrets: set[str] = set()


def register_secret(value: str | None) -> None:
    """Remember a secret so it is masked everywhere, even if it does not match a known pattern."""
    if value and len(value) >= 6:
        with _lock:
            _runtime_secrets.add(value)


def clear_secrets() -> None:
    with _lock:
        _runtime_secrets.clear()


def mask(text: Any, extra: list[str] | None = None) -> str:
    """Return ``text`` with tokens, keys, cookies, authorization headers and password assignments hidden."""
    result = text if isinstance(text, str) else str(text)
    with _lock:
        secrets = sorted(_runtime_secrets | {s for s in (extra or []) if s and len(s) >= 6}, key=len, reverse=True)
    for secret in secrets:
        result = result.replace(secret, REDACTED)
    for pattern in _PATTERNS:
        if pattern.groups:
            result = pattern.sub(_keep_prefix, result)
        else:
            result = pattern.sub(REDACTED, result)
    return result


def _keep_prefix(match: re.Match[str]) -> str:
    groups = match.groups()
    prefix = groups[0] + (groups[1] if len(groups) > 1 else "")
    return f"{prefix} {REDACTED}" if len(groups) == 1 else f"{prefix}{REDACTED}"


def mask_obj(value: Any) -> Any:
    """Mask every string inside nested dicts/lists (used before reports and exports are written)."""
    if isinstance(value, str):
        return mask(value)
    if isinstance(value, dict):
        return {key: mask_obj(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [mask_obj(item) for item in value]
    return value


def token_hint(token: str) -> str:
    """How a token may be displayed: only its first and last characters."""
    if not token:
        return ""
    return f"{token[:4]}…{token[-2:]}" if len(token) > 10 else "•" * len(token)


class UnsafeURLError(ValueError):
    """The URL is not allowed (bad scheme, missing host, or a private address while that is disabled)."""


def is_private_address(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False  # unresolvable hosts are reported later as "unreachable", not as unsafe
    for info in infos:
        address = ipaddress.ip_address(info[4][0].split("%")[0])
        if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved or address.is_multicast:
            return True
    return False


def normalize_url(raw: str) -> str:
    """Add a missing scheme and strip whitespace. Raises ``UnsafeURLError`` for anything that is not http(s)."""
    value = (raw or "").strip()
    if not value:
        raise UnsafeURLError("Enter the application URL.")
    if "://" not in value:
        value = "https://" + value
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        raise UnsafeURLError("Only http:// and https:// URLs are supported.")
    if not parsed.hostname:
        raise UnsafeURLError("The URL has no host name.")
    if parsed.username or parsed.password:
        raise UnsafeURLError("Do not put credentials in the URL; configure authentication instead.")
    return value


def validate_target_url(raw: str, allow_private: bool) -> str:
    """Normalise and check a URL the studio will open with a browser."""
    value = normalize_url(raw)
    host = urlparse(value).hostname or ""
    if not allow_private and is_private_address(host):
        raise UnsafeURLError(
            "This address is on a private or local network. Set ALLOW_PRIVATE_NETWORK=true in .env to test "
            "applications on localhost or an intranet."
        )
    return value
