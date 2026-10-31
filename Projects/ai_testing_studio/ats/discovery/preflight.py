"""Reachability pre-check with a specific, user-readable failure category (before a browser is launched)."""

from __future__ import annotations

import ssl
from typing import Literal
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field

from ats.config import get_settings
from ats.security import UnsafeURLError, validate_target_url

Category = Literal[
    "ok", "invalid_url", "private_network", "dns", "refused", "timeout", "tls", "blocked", "auth_required",
    "not_found", "server_error", "not_html", "too_many_redirects", "network",
]  # fmt: skip

_BOT_MARKERS = ("just a moment", "cf-chl", "captcha", "attention required", "access denied", "are you a robot", "px-captcha")


class PreflightResult(BaseModel):
    ok: bool
    category: Category = "ok"
    message: str = ""
    final_url: str = ""
    status: int | None = None
    warnings: list[str] = Field(default_factory=list)
    requires_auth_hint: bool = False


def preflight(url: str, ignore_https_errors: bool = False, timeout: float = 15.0) -> PreflightResult:
    settings = get_settings()
    try:
        target = validate_target_url(url, settings.allow_private_network)
    except UnsafeURLError as exc:
        category: Category = "private_network" if "private" in str(exc).lower() else "invalid_url"
        return PreflightResult(ok=False, category=category, message=str(exc))

    headers = {"User-Agent": "Mozilla/5.0 (compatible; AITestingStudio/1.0)", "Accept": "text/html,application/xhtml+xml"}
    try:
        with httpx.Client(follow_redirects=True, timeout=timeout, verify=not ignore_https_errors, max_redirects=8, headers=headers) as client:
            response = client.get(target)
    except httpx.TooManyRedirects:
        return PreflightResult(ok=False, category="too_many_redirects", message="The site redirects in a loop.")
    except httpx.ConnectTimeout:
        return PreflightResult(ok=False, category="timeout", message="The connection timed out. The site may be slow or blocked from this machine.")
    except httpx.ReadTimeout:
        return PreflightResult(ok=False, category="timeout", message="The site accepted the connection but did not respond in time.")
    except httpx.ConnectError as exc:
        text = str(exc).lower()
        if isinstance(exc.__cause__, ssl.SSLError) or "certificate" in text or "ssl" in text:
            return PreflightResult(
                ok=False, category="tls",
                message="The TLS certificate could not be verified. Enable 'Ignore HTTPS errors' for test environments with self-signed certificates.",
            )  # fmt: skip
        if "name or service" in text or "getaddrinfo" in text or "nodename" in text or "11001" in text:
            return PreflightResult(ok=False, category="dns", message="The host name could not be resolved. Check the spelling of the URL.")
        if "refused" in text or "10061" in text:
            return PreflightResult(ok=False, category="refused", message="The connection was refused. Is the application running on that address and port?")
        return PreflightResult(ok=False, category="network", message="The site could not be reached from this machine.")
    except httpx.HTTPError as exc:
        return PreflightResult(ok=False, category="network", message=f"Network error: {type(exc).__name__}.")

    final = str(response.url)
    warnings: list[str] = []
    if urlparse(final).hostname != urlparse(target).hostname:
        warnings.append(f"The URL redirects to a different host ({urlparse(final).hostname}); add it to the allowed domains if it should be explored.")
    content_type = response.headers.get("content-type", "").lower()
    body = response.text[:4000].lower() if "html" in content_type or "text" in content_type else ""
    status = response.status_code
    if status in (401, 403) or (status == 429):
        if any(marker in body for marker in _BOT_MARKERS) or status == 429:
            return PreflightResult(
                ok=False, category="blocked", status=status, final_url=final,
                message="The site blocks automated access (bot protection or rate limiting). Use a test environment or allow-list this machine.",
            )  # fmt: skip
        return PreflightResult(
            ok=True, category="auth_required", status=status, final_url=final, requires_auth_hint=True,
            warnings=[*warnings, "The site requires authentication. Configure an authentication mode to discover protected pages."],
            message="Authentication is required.",
        )  # fmt: skip
    if status == 404:
        return PreflightResult(ok=False, category="not_found", status=status, final_url=final, message="The page returned 404 Not Found.")
    if status >= 500:
        return PreflightResult(ok=False, category="server_error", status=status, final_url=final, message=f"The server returned an error ({status}).")
    if status >= 400:
        return PreflightResult(ok=False, category="blocked", status=status, final_url=final, message=f"The server rejected the request ({status}).")
    if content_type and "html" not in content_type:
        return PreflightResult(ok=False, category="not_html", status=status, final_url=final, message="The URL does not return an HTML page.")
    if any(marker in body for marker in _BOT_MARKERS[:3]):
        warnings.append("The page looks like a bot-protection challenge; discovery may be incomplete.")
    hint = any(h in final.lower() for h in ("login", "signin", "sign-in")) and "login" not in target.lower()
    if hint:
        warnings.append("The URL redirected to a login page; protected content needs an authentication mode.")
    return PreflightResult(ok=True, status=status, final_url=final, warnings=warnings, requires_auth_hint=hint, message="Reachable.")
