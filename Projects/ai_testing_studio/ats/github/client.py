"""GitHub integration over the REST API (no git binary needed). Tokens are passed in per call and never stored."""

from __future__ import annotations

import io
import re
import zipfile
from typing import Any
from urllib.parse import quote

import httpx

from ats.config import get_settings
from ats.errors import GitHubError
from ats.logging_setup import get_logger
from ats.security import mask, register_secret

LOGGER = get_logger("github.client")
MAX_ARCHIVE_BYTES = 60_000_000
MAX_FILES = 600
BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/_.-]{1,98}[A-Za-z0-9]$")


def parse_repo(url: str) -> tuple[str, str]:
    """Accepts https://github.com/owner/repo(.git), git@github.com:owner/repo.git or owner/repo."""
    text = (url or "").strip()
    match = (
        re.match(r"^(?:https?://)?(?:www\.)?github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?/?(?:[#?].*)?$", text)
        or re.match(r"^git@github\.com:([\w.-]+)/([\w.-]+?)(?:\.git)?$", text)
        or re.match(r"^([\w.-]+)/([\w.-]+?)(?:\.git)?$", text)
    )
    if not match:
        raise GitHubError("Enter the repository as https://github.com/owner/repository.")
    return match.group(1), match.group(2)


def valid_branch(name: str) -> bool:
    return bool(BRANCH_RE.match(name)) and ".." not in name and not name.endswith((".lock", "/")) and "//" not in name


class GitHubClient:
    def __init__(self, token: str, api_url: str | None = None, transport: httpx.BaseTransport | None = None) -> None:
        token = (token or "").strip()
        if not token:
            raise GitHubError("A GitHub personal access token is required. It is kept only for this browser session.")
        register_secret(token)
        self.base = (api_url or get_settings().github_api_url).rstrip("/")
        self._http = httpx.Client(
            base_url=self.base, transport=transport, timeout=httpx.Timeout(30.0, connect=10.0), follow_redirects=True,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "ai-testing-studio"},
        )  # fmt: skip

    def close(self) -> None:
        self._http.close()

    # ------------------------------------------------------------------ plumbing
    def request(self, method: str, path: str, *, ok: tuple[int, ...] = (200, 201), **kwargs: Any) -> httpx.Response:
        try:
            response = self._http.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise GitHubError("GitHub did not answer in time. Try again.") from exc
        except httpx.HTTPError as exc:
            LOGGER.warning("GitHub request failed: %s", mask(str(exc)))
            raise GitHubError("GitHub could not be reached. Check the network connection.") from exc
        if response.status_code in ok:
            return response
        raise GitHubError(self._explain(response))

    @staticmethod
    def _explain(response: httpx.Response) -> str:
        try:
            detail = str(response.json().get("message", ""))
        except ValueError:
            detail = ""
        code = response.status_code
        if code == 401:
            return "GitHub rejected the token. Create a new token and try again."
        if code == 403:
            if response.headers.get("x-ratelimit-remaining") == "0":
                return "GitHub rate limit reached. Try again later."
            return "The token is not allowed to do that. It needs repository 'Contents' and 'Pull requests' write access."
        if code == 404:
            return "The repository, branch or file was not found, or the token cannot see it."
        if code == 409:
            return f"GitHub reported a conflict: {mask(detail)[:200]}"
        if code == 422:
            return f"GitHub rejected the request: {mask(detail)[:200]}"
        return f"GitHub returned an error ({code})."

    # ------------------------------------------------------------------ reads
    def get_repo(self, owner: str, name: str) -> dict[str, Any]:
        data = self.request("GET", f"/repos/{owner}/{name}").json()
        return {
            "full_name": data.get("full_name", f"{owner}/{name}"), "default_branch": data.get("default_branch", "main"),
            "private": bool(data.get("private")), "can_push": bool((data.get("permissions") or {}).get("push", False)), "html_url": data.get("html_url", ""),
        }  # fmt: skip

    def list_branches(self, owner: str, name: str, limit: int = 100) -> list[str]:
        data = self.request("GET", f"/repos/{owner}/{name}/branches", params={"per_page": min(limit, 100)}).json()
        return [b["name"] for b in data]

    def download_files(self, owner: str, name: str, ref: str) -> dict[str, bytes]:
        """Repository snapshot at ``ref`` (branch, tag or sha) as {path: bytes}; the archive's top folder is removed."""
        response = self.request("GET", f"/repos/{owner}/{name}/zipball/{quote(ref, safe='')}", ok=(200,))
        if len(response.content) > MAX_ARCHIVE_BYTES:
            raise GitHubError("The repository is too large to import. Point to a smaller test repository.")
        files: dict[str, bytes] = {}
        try:
            with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
                for info in archive.infolist():
                    if info.is_dir() or info.file_size > 2_000_000:
                        continue
                    parts = info.filename.split("/", 1)
                    if len(parts) == 2 and parts[1]:
                        files[parts[1]] = archive.read(info)
                    if len(files) > 5000:
                        break
        except zipfile.BadZipFile as exc:
            raise GitHubError("GitHub returned an archive that could not be read.") from exc
        return files

    # ------------------------------------------------------------------ writes
    def branch_head(self, owner: str, name: str, branch: str) -> str | None:
        response = self.request("GET", f"/repos/{owner}/{name}/git/ref/heads/{quote(branch, safe='/')}", ok=(200, 404))
        return response.json()["object"]["sha"] if response.status_code == 200 else None

    def commit_files(self, owner: str, name: str, *, branch: str, base_branch: str, files: dict[str, str], message: str) -> dict[str, str]:
        """Commit ``files`` onto ``branch`` (created from ``base_branch`` when missing). Never force-pushes."""
        if not valid_branch(branch):
            raise GitHubError("The branch name contains characters GitHub does not accept.")
        if not files:
            raise GitHubError("There is nothing to commit.")
        if len(files) > MAX_FILES:
            raise GitHubError(f"Too many files to commit in one go ({len(files)}).")
        head = self.branch_head(owner, name, branch)
        parent = head or self.branch_head(owner, name, base_branch)
        if parent is None:
            raise GitHubError(f"The base branch '{base_branch}' was not found.")
        commit = self.request("GET", f"/repos/{owner}/{name}/git/commits/{parent}").json()
        tree = self.request(
            "POST", f"/repos/{owner}/{name}/git/trees",
            json={"base_tree": commit["tree"]["sha"], "tree": [{"path": p, "mode": "100644", "type": "blob", "content": c} for p, c in sorted(files.items())]},
        ).json()  # fmt: skip
        created = self.request("POST", f"/repos/{owner}/{name}/git/commits", json={"message": message, "tree": tree["sha"], "parents": [parent]}).json()
        if head:
            self.request("PATCH", f"/repos/{owner}/{name}/git/refs/heads/{quote(branch, safe='/')}", json={"sha": created["sha"], "force": False})
        else:
            self.request("POST", f"/repos/{owner}/{name}/git/refs", json={"ref": f"refs/heads/{branch}", "sha": created["sha"]})
        base = f"https://github.com/{owner}/{name}"
        return {"commit_sha": created["sha"], "commit_url": f"{base}/commit/{created['sha']}", "branch_url": f"{base}/tree/{branch}"}

    def open_pull_request(self, owner: str, name: str, *, head: str, base: str, title: str, body: str) -> dict[str, Any]:
        response = self.request("POST", f"/repos/{owner}/{name}/pulls", ok=(201, 422), json={"title": title[:250], "head": head, "base": base, "body": body[:60000]})
        if response.status_code == 201:
            data = response.json()
            return {"url": data["html_url"], "number": data["number"], "existing": False}
        existing = self.request("GET", f"/repos/{owner}/{name}/pulls", params={"head": f"{owner}:{head}", "state": "open"}).json()
        if existing:
            return {"url": existing[0]["html_url"], "number": existing[0]["number"], "existing": True}
        raise GitHubError(self._explain(response))
