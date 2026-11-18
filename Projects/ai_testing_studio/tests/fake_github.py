"""In-memory GitHub with a real object model (blobs, trees, commits, refs) behind httpx.MockTransport. Never touches the network."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import dataclass, field

import httpx

from ats.github.merge import blob_sha

TOKEN = "ghp_exampletoken1234567890abcdef"


@dataclass
class FakeRepo:
    default_branch: str = "main"
    branches: dict[str, str] = field(default_factory=dict)
    commits: dict[str, dict] = field(default_factory=dict)  # sha -> {"tree": sha, "parents": [...], "message": str}
    trees: dict[str, dict[str, str]] = field(default_factory=dict)  # tree sha -> {path: blob sha}
    blobs: dict[str, bytes] = field(default_factory=dict)


class FakeGitHub:
    """Several repositories, the Git Data endpoints the studio uses, and a request log. ``truncate`` makes recursive listings truncated."""

    def __init__(self, repos: tuple[str, ...] = ("owner/repo",), can_push: bool = True, truncate: bool = False) -> None:
        self.repos = {name.lower(): FakeRepo() for name in repos}
        self.can_push, self.truncate = can_push, truncate
        self.requests: list[tuple[str, str]] = []
        self.writes: list[tuple[str, str]] = []
        for name in self.repos:
            self.seed(name, "main", {"README.md": "# Upstream readme\n", "src/app.py": "print('hello')\n"})

    # ------------------------------------------------------------------ helpers for tests
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)

    def seed(self, repo: str, branch: str, files: dict[str, str], parent: str | None = None) -> str:
        """Create or move ``branch`` to a new commit holding exactly ``files``."""
        r = self.repos[repo.lower()]
        tree = {path: self._blob(r, text.encode("utf-8")) for path, text in files.items()}
        sha = self._commit(r, tree, [parent] if parent else [], f"seed {branch}")
        r.branches[branch] = sha
        return sha

    def files(self, repo: str, branch: str) -> dict[str, str]:
        r = self.repos[repo.lower()]
        return {path: r.blobs[sha].decode("utf-8") for path, sha in r.trees[r.commits[r.branches[branch]]["tree"]].items()}

    def head(self, repo: str, branch: str) -> str:
        return self.repos[repo.lower()].branches[branch]

    def commit_count(self, repo: str) -> int:
        return len([c for c in self.repos[repo.lower()].commits.values() if not c["message"].startswith("seed")])

    # ------------------------------------------------------------------ object model
    @staticmethod
    def _blob(r: FakeRepo, data: bytes) -> str:
        sha = blob_sha(data)
        r.blobs[sha] = data
        return sha

    @staticmethod
    def _commit(r: FakeRepo, tree: dict[str, str], parents: list[str], message: str) -> str:
        tree_sha = hashlib.sha1(json.dumps(sorted(tree.items())).encode()).hexdigest()  # noqa: S324
        r.trees[tree_sha] = dict(tree)
        sha = hashlib.sha1(f"{tree_sha}{parents}{message}{len(r.commits)}".encode()).hexdigest()  # noqa: S324
        r.commits[sha] = {"tree": tree_sha, "parents": parents, "message": message}
        return sha

    @staticmethod
    def _ancestors(r: FakeRepo, sha: str) -> set[str]:
        seen, todo = set(), [sha]
        while todo:
            current = todo.pop()
            if current not in seen:
                seen.add(current)
                todo += r.commits[current]["parents"]
        return seen

    @staticmethod
    def _children(tree_sha: str, tree: dict[str, str], prefix: str) -> list[dict]:
        entries: dict[str, dict] = {}
        for path, sha in tree.items():
            if not path.startswith(prefix):
                continue
            head, _, rest = path[len(prefix) :].partition("/")
            entries[head] = {"path": head, "type": "tree", "sha": f"sub|{tree_sha}|{prefix}{head}/"} if rest else {"path": head, "type": "blob", "sha": sha, "mode": "100644"}
        return list(entries.values())

    # ------------------------------------------------------------------ HTTP
    def __call__(self, request: httpx.Request) -> httpx.Response:
        method, path = request.method, request.url.path
        self.requests.append((method, path))
        if method in {"POST", "PATCH", "PUT", "DELETE"}:
            self.writes.append((method, path))
        if request.headers.get("authorization") != f"Bearer {TOKEN}":
            return httpx.Response(401, json={"message": "Bad credentials"})
        match = re.match(r"/repos/([^/]+/[^/]+)(/.*)?$", path)
        if not match or match.group(1).lower() not in self.repos:
            return httpx.Response(404, json={"message": "Not Found"})
        r, rest = self.repos[match.group(1).lower()], match.group(2) or ""
        body = json.loads(request.content) if request.content else {}
        if rest == "":
            return httpx.Response(200, json={"full_name": match.group(1), "default_branch": r.default_branch, "private": False, "permissions": {"push": self.can_push}, "html_url": f"https://github.com/{match.group(1)}"})
        if rest == "/branches":
            return httpx.Response(200, json=[{"name": n} for n in r.branches])
        if m := re.fullmatch(r"/git/ref/heads/(.+)", rest):
            sha = r.branches.get(m.group(1))
            return httpx.Response(200, json={"object": {"sha": sha}}) if sha else httpx.Response(404, json={"message": "Not Found"})
        if (m := re.fullmatch(r"/git/commits/(\w+)", rest)) and method == "GET":
            commit = r.commits.get(m.group(1))
            if not commit:
                return httpx.Response(404, json={"message": "Not Found"})
            return httpx.Response(200, json={"sha": m.group(1), "tree": {"sha": commit["tree"]}, "parents": [{"sha": p} for p in commit["parents"]]})
        if (m := re.fullmatch(r"/git/trees/(.+)", rest)) and method == "GET":
            return self._get_tree(r, m.group(1), request.url.params.get("recursive") == "1")
        if (m := re.fullmatch(r"/git/blobs/(\w+)", rest)) and method == "GET":
            data = r.blobs.get(m.group(1))
            if data is None:
                return httpx.Response(404, json={"message": "Not Found"})
            return httpx.Response(200, json={"sha": m.group(1), "size": len(data), "encoding": "base64", "content": base64.b64encode(data).decode()})
        if (m := re.fullmatch(r"/contents/(.+)", rest)) and method == "GET":
            branch = request.url.params.get("ref", r.default_branch)
            sha = r.trees[r.commits[r.branches[branch]]["tree"]].get(m.group(1)) if branch in r.branches else None
            if sha is None:
                return httpx.Response(404, json={"message": "Not Found"})
            return httpx.Response(200, json={"type": "file", "sha": sha, "encoding": "base64", "content": base64.b64encode(r.blobs[sha]).decode()})
        if rest == "/git/trees" and method == "POST":
            return self._post_tree(r, body)
        if rest == "/git/commits" and method == "POST":
            tree_sha = body["tree"]
            sha = self._commit_from_tree(r, tree_sha, body["parents"], body["message"])
            return httpx.Response(201, json={"sha": sha})
        if rest == "/git/refs" and method == "POST":
            name = body["ref"].removeprefix("refs/heads/")
            if name in r.branches:
                return httpx.Response(422, json={"message": "Reference already exists"})
            r.branches[name] = body["sha"]
            return httpx.Response(201, json={})
        if (m := re.fullmatch(r"/git/refs/heads/(.+)", rest)) and method == "PATCH":
            assert body["force"] is False  # fast-forward only
            current = r.branches.get(m.group(1))
            if current is None:
                return httpx.Response(404, json={"message": "Not Found"})
            if current not in self._ancestors(r, body["sha"]):
                return httpx.Response(422, json={"message": "Update is not a fast forward"})
            r.branches[m.group(1)] = body["sha"]
            return httpx.Response(200, json={})
        return httpx.Response(404, json={"message": "Not Found"})

    def _get_tree(self, r: FakeRepo, ref: str, recursive: bool) -> httpx.Response:
        prefix = ""
        if ref.startswith("sub|"):
            _, ref, prefix = ref.split("|", 2)
        tree = r.trees.get(ref)
        if tree is None:
            return httpx.Response(404, json={"message": "Not Found"})
        if recursive and not self.truncate:
            return httpx.Response(200, json={"sha": ref, "truncated": False, "tree": [{"path": p, "type": "blob", "sha": s, "mode": "100644"} for p, s in sorted(tree.items())]})
        if recursive:
            return httpx.Response(200, json={"sha": ref, "truncated": True, "tree": []})
        return httpx.Response(200, json={"sha": ref, "truncated": False, "tree": self._children(ref, tree, prefix)})

    def _post_tree(self, r: FakeRepo, body: dict) -> httpx.Response:
        tree = dict(r.trees[body["base_tree"]]) if body.get("base_tree") else {}
        for entry in body["tree"]:
            tree[entry["path"]] = self._blob(r, entry["content"].encode("utf-8")) if "content" in entry else entry["sha"]
        sha = hashlib.sha1(json.dumps(sorted(tree.items())).encode()).hexdigest()  # noqa: S324
        r.trees[sha] = tree
        return httpx.Response(201, json={"sha": sha})

    def _commit_from_tree(self, r: FakeRepo, tree_sha: str, parents: list[str], message: str) -> str:
        sha = hashlib.sha1(f"{tree_sha}{parents}{message}{len(r.commits)}".encode()).hexdigest()  # noqa: S324
        r.commits[sha] = {"tree": tree_sha, "parents": parents, "message": message}
        return sha
