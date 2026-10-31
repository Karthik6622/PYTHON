"""GitHub client and service against an in-memory fake of the GitHub REST API (no network)."""

from __future__ import annotations

import io
import json
import re
import zipfile

import httpx
import pytest

from ats.ai.agents import GitHubAgent
from ats.analysis.patching import patch_locators
from ats.automation.bundle_store import BundleStore
from ats.errors import GitHubError
from ats.execution.executor import ExecutionContext
from ats.github.client import GitHubClient, parse_repo, valid_branch
from ats.github.service import GitHubService
from tests.fakes import FakeClient

TOKEN = "ghp_exampletoken1234567890abcdef"
LOCATORS = {"login.go": {"page": "login", "intent": "", "role": "button", "name": "Sign in", "preferred": {"kind": "role", "value": "button", "name": "Sign in"}, "alternatives": []}}


class FakeGitHub:
    def __init__(self, can_push: bool = True) -> None:
        self.can_push = can_push
        self.branches = {"main": "base111"}
        self.trees: list[dict] = []
        self.commits: list[dict] = []
        self.pulls: list[dict] = []
        self.requests: list[tuple[str, str]] = []
        self.auth: set[str] = set()
        self.archive = self._zip({"login.spec.ts": "test('x')", ".env": "SECRET=1", "node_modules/a.js": "x", "README.md": "# r"})

    @staticmethod
    def _zip(files: dict[str, str]) -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as z:
            for name, text in files.items():
                z.writestr(f"owner-repo-abc123/{name}", text)
        return buffer.getvalue()

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.auth.add(request.headers.get("authorization", ""))
        method, path = request.method, request.url.path
        self.requests.append((method, path))
        if request.headers.get("authorization") != f"Bearer {TOKEN}":
            return httpx.Response(401, json={"message": "Bad credentials"})
        if path == "/repos/owner/repo":
            return httpx.Response(200, json={"full_name": "owner/repo", "default_branch": "main", "private": False, "permissions": {"push": self.can_push}, "html_url": "https://github.com/owner/repo"})
        if path == "/repos/owner/repo/branches":
            return httpx.Response(200, json=[{"name": n} for n in self.branches])
        if m := re.fullmatch(r"/repos/owner/repo/git/ref/heads/(.+)", path):
            sha = self.branches.get(m.group(1))
            return httpx.Response(200, json={"object": {"sha": sha}}) if sha else httpx.Response(404, json={"message": "Not Found"})
        if re.fullmatch(r"/repos/owner/repo/git/commits/\w+", path) and method == "GET":
            return httpx.Response(200, json={"tree": {"sha": "tree000"}})
        if path == "/repos/owner/repo/git/trees":
            self.trees.append(json.loads(request.content))
            return httpx.Response(201, json={"sha": "tree111"})
        if path == "/repos/owner/repo/git/commits" and method == "POST":
            self.commits.append(json.loads(request.content))
            return httpx.Response(201, json={"sha": "commit222"})
        if path == "/repos/owner/repo/git/refs" and method == "POST":
            body = json.loads(request.content)
            self.branches[body["ref"].removeprefix("refs/heads/")] = body["sha"]
            return httpx.Response(201, json={})
        if path == "/repos/owner/repo/pulls" and method == "POST":
            self.pulls.append(json.loads(request.content))
            return httpx.Response(201, json={"html_url": "https://github.com/owner/repo/pull/7", "number": 7})
        if path.startswith("/repos/owner/repo/zipball/"):
            return httpx.Response(200, content=self.archive)
        return httpx.Response(404, json={"message": "Not Found"})


@pytest.fixture()
def gh():
    return FakeGitHub()


def make_service(repo, gh: FakeGitHub, handlers: dict | None = None) -> GitHubService:
    agent = GitHubAgent(FakeClient(handlers or {"GitHub Agent": {"branch_name": "ai-tests/shop-login", "commit_title": "Add tests", "commit_body": "b", "pr_title": "Shop tests", "pr_body": "Body"}}), repo)
    return GitHubService(repo, BundleStore(), agent, httpx.MockTransport(gh))


def make_project_with_bundle(repo, link: bool = True):
    project = repo.create_project("owner", name="Shop", url="http://shop.example", base_url="http://shop.example")
    files = {"tests/test_login.py": "# TC_LOG_001\n", "config/locators.json": json.dumps(LOCATORS), ".env": "PASSWORD=secret-value", "storage_state.json": "{}"}
    bundle_id = repo.create_bundle(project.id, "playwright_python", "chromium", {}, [{"test_case_id": "TC_LOG_001", "title": "Login works"}])
    BundleStore().write(project.id, bundle_id, files)
    if link:
        repo.save_github(project.id, repo_url="https://github.com/owner/repo", default_branch="main")
    return project, bundle_id


def test_parse_repo_variants():
    for text in ("https://github.com/owner/repo", "https://github.com/owner/repo.git", "git@github.com:owner/repo.git", "owner/repo", "https://github.com/owner/repo/"):
        assert parse_repo(text) == ("owner", "repo")
    with pytest.raises(GitHubError):
        parse_repo("https://gitlab.com/owner/repo")


def test_branch_name_validation():
    assert valid_branch("ai-tests/shop-login-20240101") and not valid_branch("bad branch") and not valid_branch("a..b") and not valid_branch("x/")


def test_token_is_required_and_rejected_tokens_are_explained(gh):
    with pytest.raises(GitHubError):
        GitHubClient("")
    client = GitHubClient("wrong-token-value-1234", transport=httpx.MockTransport(gh))
    with pytest.raises(GitHubError) as err:
        client.get_repo("owner", "repo")
    assert "rejected the token" in err.value.user_message and "wrong-token" not in err.value.user_message


def test_link_saves_repo_and_default_branch(repo, gh):
    project = repo.create_project("owner", name="Shop", url="http://shop.example")
    info = make_service(repo, gh).link(project, "https://github.com/owner/repo", TOKEN)
    assert info["can_push"] and info["branches"] == ["main"]
    assert repo.get_github(project.id)["default_branch"] == "main"
    assert TOKEN not in json.dumps(repo.get_github(project.id)) and TOKEN not in json.dumps(repo.list_audit(project.id))


def test_commit_bundle_creates_branch_commit_and_pr_without_secrets(repo, gh):
    project, bundle_id = make_project_with_bundle(repo)
    result = make_service(repo, gh).commit_bundle(project, bundle_id, TOKEN)
    assert result["branch"].startswith("ai-tests/") and result["pr_url"].endswith("/pull/7") and result["commit_sha"] == "commit222"
    committed = {item["path"] for item in gh.trees[0]["tree"]}
    assert committed == {"tests/test_login.py", "config/locators.json"}  # no .env, no storage state
    assert gh.commits[0]["parents"] == ["base111"] and gh.pulls[0]["base"] == "main" and gh.pulls[0]["head"] == result["branch"]
    assert ("PATCH", f"/repos/owner/repo/git/refs/heads/{result['branch']}") not in gh.requests  # new branch, never a force update
    link = repo.get_github(project.id)
    assert link["pr_url"].endswith("/pull/7") and link["branch"] == result["branch"] and repo.get_bundle(bundle_id)["status"] == "committed"


def test_commit_refuses_default_branch_and_read_only_tokens(repo, gh):
    project, bundle_id = make_project_with_bundle(repo)
    with pytest.raises(GitHubError, match="never directly"):
        make_service(repo, gh).commit_bundle(project, bundle_id, TOKEN, branch="main")
    read_only = FakeGitHub(can_push=False)
    with pytest.raises(GitHubError, match="cannot push"):
        make_service(repo, read_only).commit_bundle(project, bundle_id, TOKEN)
    assert read_only.commits == []


def test_model_outage_uses_fallback_text(repo, gh):
    class Down(FakeClient):
        def complete(self, *_a, **_k):
            from ats.errors import ModelError

            raise ModelError("down")

    project, bundle_id = make_project_with_bundle(repo)
    service = GitHubService(repo, BundleStore(), GitHubAgent(Down(), repo), httpx.MockTransport(gh))
    result = service.commit_bundle(project, bundle_id, TOKEN)
    assert result["branch"].startswith("ai-tests/shop-") and gh.pulls[0]["title"]


def test_unsafe_model_branch_name_is_replaced(repo, gh):
    project, bundle_id = make_project_with_bundle(repo)
    service = make_service(repo, gh, {"GitHub Agent": {"branch_name": "main", "commit_title": "t", "pr_title": "p"}})
    assert service.commit_bundle(project, bundle_id, TOKEN)["branch"].startswith("ai-tests/")


def test_import_tests_filters_secrets_and_build_output(repo, gh):
    project, _ = make_project_with_bundle(repo)
    files, ref = make_service(repo, gh).import_tests(project, TOKEN)
    assert ref == "main" and set(files) == {"login.spec.ts", "README.md"}


def test_healing_pr_changes_only_the_locator_file(repo, gh):
    project, bundle_id = make_project_with_bundle(repo)
    record = repo.create_healing(
        project.id, "EX-1", test_case_ids=["TC_LOG_001"], element_key="login.go", old_locator=LOCATORS["login.go"]["preferred"],
        new_locator={"kind": "role", "value": "button", "name": "Log in", "exact": False}, reason="renamed", confidence=0.91, status="verified",
    )
    execution_id = repo.create_execution(project.id, framework="playwright_python", browser="chromium")
    files = BundleStore().read_all(project.id, bundle_id)
    ctx = ExecutionContext(execution_id, project, BundleStore().root(project.id, bundle_id), files, "playwright_python", "chromium", {}, bundle_id)
    url = make_service(repo, gh).open_healing_pr(ctx, [record], TOKEN)
    assert url.endswith("/pull/7")
    assert [item["path"] for item in gh.trees[0]["tree"]] == ["config/locators.json"]
    patched = json.loads(gh.trees[0]["tree"][0]["content"])
    assert patched["login.go"]["preferred"]["name"] == "Log in" and patched["login.go"]["alternatives"][0]["name"] == "Sign in"
    assert "HEALED" in gh.pulls[0]["body"] or gh.pulls[0]["body"] == "Body"
    assert repo.get_healing(record)["status"] == "pr_opened" and repo.get_healing(record)["pr_url"] == url
    assert patch_locators  # imported helper stays the single patching implementation


def test_pr_callback_without_token_is_a_noop(repo, gh):
    project, _ = make_project_with_bundle(repo)
    execution_id = repo.create_execution(project.id, framework="playwright_python", browser="chromium")
    ctx = ExecutionContext(execution_id, project, BundleStore().root(project.id, 1), {}, "playwright_python", "chromium", {})
    make_service(repo, gh).pr_callback(lambda: "")(ctx, [1])
    assert gh.requests == [] and any(a["action"] == "github.heal_pr_skipped" for a in repo.list_audit(project.id))
