"""GitHub REST API access (personal access token now; the token is passed in so OAuth or a GitHub App can replace it later)."""

from __future__ import annotations

import re
import ssl
from dataclasses import dataclass
from typing import Any

import httpx

from ..config import settings
from ..security import redact

GITHUB_API = "https://api.github.com"
_URL_RE = re.compile(r"^https://github\.com/(?P<owner>[A-Za-z0-9][A-Za-z0-9-]{0,38})/(?P<repo>[A-Za-z0-9._-]{1,100}?)(?:\.git)?/?$")
_SHORT_RE = re.compile(r"^(?P<owner>[A-Za-z0-9][A-Za-z0-9-]{0,38})/(?P<repo>[A-Za-z0-9._-]{1,100})$")


class GitHubError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


@dataclass(frozen=True)
class RepoRef:
    owner: str
    name: str

    @property
    def clone_url(self) -> str:
        return f"https://github.com/{self.owner}/{self.name}.git"

    @property
    def folder(self) -> str:
        return f"{self.owner}__{self.name}"


def parse_repository(value: str) -> RepoRef:
    """Accepts https://github.com/owner/repo(.git) or owner/repo. Only github.com over HTTPS is allowed."""
    text = (value or "").strip()
    match = _URL_RE.match(text) or _SHORT_RE.match(text)
    if not match or match.group("repo") in {".", ".."}:
        raise GitHubError("Enter a GitHub repository URL such as https://github.com/owner/repo.", 400)
    return RepoRef(match.group("owner"), match.group("repo"))


class GitHubService:
    def __init__(self, token: str | None = None, transport: httpx.BaseTransport | None = None) -> None:
        self._token = token if token is not None else settings.github_token
        self._transport = transport

    def _client(self) -> httpx.Client:
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "rk-studio"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        kwargs: dict[str, Any] = {"headers": headers, "timeout": httpx.Timeout(20.0), "base_url": GITHUB_API}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        else:
            kwargs["verify"] = ssl.create_default_context()
        return httpx.Client(**kwargs)

    def _get(self, path: str, **params: Any) -> Any:
        try:
            with self._client() as client:
                response = client.get(path, params=params or None)
        except httpx.TimeoutException as exc:
            raise GitHubError("GitHub did not answer in time. Try again.", 504) from exc
        except httpx.HTTPError as exc:
            raise GitHubError("Could not reach GitHub. Check your network connection.", 502) from exc
        if response.status_code == 401:
            raise GitHubError("GitHub rejected the token. Check that it is valid and not expired.", 401)
        if response.status_code == 403:
            remaining = response.headers.get("x-ratelimit-remaining")
            reason = "GitHub's rate limit was reached." if remaining == "0" else "The token does not have access to this resource."
            raise GitHubError(reason, 403)
        if response.status_code == 404:
            raise GitHubError("Repository not found, or the token cannot see it (private repositories need a token with repo access).", 404)
        if not response.is_success:
            raise GitHubError(redact(f"GitHub returned an error ({response.status_code})."), 502)
        return response.json()

    def validate_token(self) -> dict[str, Any]:
        """Returns the authenticated user's login. Raises when there is no token or it is rejected."""
        if not self._token:
            raise GitHubError("No GitHub token configured.", 400)
        data = self._get("/user")
        return {"login": data.get("login", ""), "name": data.get("name") or ""}

    def get_repository(self, ref: RepoRef) -> dict[str, Any]:
        data = self._get(f"/repos/{ref.owner}/{ref.name}")
        permissions = data.get("permissions") or {}
        return {
            "full_name": data.get("full_name", f"{ref.owner}/{ref.name}"),
            "default_branch": data.get("default_branch", "main"),
            "private": bool(data.get("private")),
            "description": data.get("description") or "",
            "can_push": bool(permissions.get("push")),
        }

    def list_branches(self, ref: RepoRef) -> list[str]:
        data = self._get(f"/repos/{ref.owner}/{ref.name}/branches", per_page=100)
        return [item.get("name", "") for item in data if isinstance(item, dict) and item.get("name")]
