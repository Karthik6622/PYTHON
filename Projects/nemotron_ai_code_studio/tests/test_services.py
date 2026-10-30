import pytest

from studio.services.change_tracker import ChangeTracker
from studio.services.git_service import GitError
from studio.services.workspace_service import WorkspaceError


def test_workspace_operations(active):
    ws = active.workspace
    assert ws.read_text("app/auth.py")["language"] == "python"
    ws.write_text("new/dir/file.txt", "hi")
    assert ws.read_text("new/dir/file.txt")["content"] == "hi"
    ws.rename("new/dir/file.txt", "new/moved.txt")
    ws.delete("new")
    with pytest.raises(WorkspaceError):
        ws.read_text("new/moved.txt")
    for bad in ["../x.txt", ".git/config"]:
        with pytest.raises(WorkspaceError):
            ws.write_text(bad, "x")
    names = [e["name"] for e in ws.list_dir("")]
    assert ".git" not in names and "app" in names


def test_change_tracker_accept_reject(active):
    tracker, ws = ActiveTracker(active)
    cid = tracker.begin()
    tracker.snapshot(cid, ws, "app/utils.py")
    tracker.snapshot(cid, ws, "brand_new.py")
    ws.write_text("app/utils.py", "def slugify(t):\n    return t\n")
    ws.write_text("brand_new.py", "x = 1\n")
    summary = {item["path"]: item["status"] for item in tracker.summary(cid, ws)}
    assert summary == {"app/utils.py": "modified", "brand_new.py": "added"}
    assert "+x = 1" in tracker.diff_text(cid, ws)
    restored = tracker.reject(cid, ws)
    assert set(restored) == {"app/utils.py", "brand_new.py"}
    assert "lower()" in ws.read_text("app/utils.py")["content"]
    assert not (ws.root / "brand_new.py").exists()


def ActiveTracker(active):
    return ChangeTracker(), active.workspace


def test_git_service_flow(active):
    git, root = active.git, active.path
    assert git.status()["clean"]
    (root / "app/utils.py").write_text("def slugify(t):\n    return t\n", encoding="utf-8")
    (root / "fresh.txt").write_text("new\n", encoding="utf-8")
    status = {f["path"]: f["kind"] for f in git.status()["files"]}
    assert status == {"app/utils.py": "modified", "fresh.txt": "untracked"}
    assert "return t" in git.diff() and "fresh.txt" in git.diff()
    with pytest.raises(GitError):
        git.commit("nothing staged")
    git.stage(["app/utils.py"])
    assert git.commit("Change slugify")["message"] == "Change slugify"
    assert git.log(1)[0]["message"] == "Change slugify"
    git.discard(["fresh.txt"])
    assert not (root / "fresh.txt").exists()
    git.create_branch("feature/x")
    assert git.current_branch() == "feature/x"
    assert git.branches()["remote"] == []  # no origin: must not raise
    with pytest.raises(GitError):
        git.create_branch("bad name")
    with pytest.raises(GitError):
        git.stage(["../outside.txt"])


def test_discard_restores_tracked_file(active):
    (active.path / "app/utils.py").write_text("broken", encoding="utf-8")
    active.git.discard(["app/utils.py"])
    assert "slugify" in (active.path / "app/utils.py").read_text(encoding="utf-8")


def test_index_and_context(active):
    index = active.index
    assert "app/auth.py" in index.files and ".env" not in index.files
    assert any(s.name == "login_user" for s in index.symbols["login_user"])
    assert "app/main.py" in index.imported_by["app/auth.py"]
    bundle = active.context.build("login_user always returns True, please fix the authentication bug")
    paths = [f.path for f in bundle.files]
    assert paths[0] == "app/auth.py"
    assert "tests/test_auth.py" in paths
    assert "nvapi-super-secret" not in bundle.to_prompt()
    assert "app/utils.py" not in paths[:2]
    assert bundle.to_prompt().count("class AuthService") == 1


def test_context_respects_named_files(active):
    bundle = active.context.build("explain `slugify` in app/utils.py")
    assert bundle.files[0].path == "app/utils.py"


def test_search(active):
    hits = active.search.search_text("slugify")
    assert {h["path"] for h in hits} == {"app/utils.py"}
    assert active.search.search_filename("auth")[0] == "app/auth.py"
    refs = active.search.find_references("login_user")
    assert refs["definitions"][0]["path"] == "app/auth.py"
    assert any(r["path"] == "app/main.py" for r in refs["references"])
    assert active.search.search_text("NVIDIA_API_KEY") == []  # .env is never indexed
