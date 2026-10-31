import shutil
import sys

import pytest
from git import Repo

from studio.services import git_detect, repository_service, secret_store
from studio.services.git_detect import GitInfo, connection_state, inspect_folder, remote_slug, strip_credentials
from studio.services.git_service import GitService

IDENTITY = ["-c", "user.name=Test", "-c", "user.email=test@example.com"]

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def commit(repo: Repo, message: str = "first") -> None:
    repo.git.execute(["git", "-c", "user.name=Test", "-c", "user.email=test", "commit", "-m", message])


def make_repo(path, files=None, branch="main") -> Repo:
    path.mkdir(parents=True, exist_ok=True)
    repo = Repo.init(path, initial_branch=branch)
    for name, text in (files or {}).items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    if files:
        repo.git.add("-A")
        commit(repo)
    return repo


# ---------------------------------------------------------------- detection
def test_a_normal_folder_is_not_a_repository(tmp_path):
    (tmp_path / "notes.txt").write_text("hi")
    info = inspect_folder(tmp_path)
    assert not info.is_repo and info.root is None and info.branch == "" and info.error == ""


def test_a_folder_inside_a_git_directory_is_not_a_working_tree(tmp_path):
    make_repo(tmp_path / "r", {"a.txt": "1"})
    assert not inspect_folder(tmp_path / "r" / ".git").is_repo


def test_repository_with_spaces_in_its_path(tmp_path):
    root = tmp_path / "my project (copy)"
    make_repo(root, {"a.txt": "1"})
    info = inspect_folder(root)
    assert info.is_repo
    assert info.name == "my project (copy)"
    assert info.branch == "main" and info.has_commits and not info.detached
    assert info.remote_url == "" and info.changes == 0


def test_nested_folder_reports_the_repository_root(tmp_path):
    make_repo(tmp_path / "repo", {"pkg/src/a.txt": "1"})
    info = inspect_folder(tmp_path / "repo" / "pkg" / "src")
    assert info.is_repo and info.name == "repo" and info.root.samefile(tmp_path / "repo")


def test_repository_without_commits(tmp_path):
    make_repo(tmp_path / "empty", branch="trunk")
    info = inspect_folder(tmp_path / "empty")
    assert info.is_repo and not info.has_commits and not info.detached
    assert info.branch == "trunk" and info.head == ""


def test_detached_head(tmp_path):
    repo = make_repo(tmp_path / "r", {"a.txt": "1"})
    repo.git.checkout("--detach")
    info = inspect_folder(tmp_path / "r")
    assert info.is_repo and info.detached and info.branch == ""
    assert info.branch_label.startswith("detached at ") and info.head


def test_linked_worktree_is_detected_although_dot_git_is_a_file(tmp_path):
    repo = make_repo(tmp_path / "main", {"a.txt": "1"})
    repo.git.worktree("add", str(tmp_path / "wt"), "-b", "feature")
    assert (tmp_path / "wt" / ".git").is_file()
    info = inspect_folder(tmp_path / "wt")
    assert info.is_repo and info.branch == "feature" and info.name == "wt"


def test_origin_is_read_without_credentials(tmp_path):
    repo = make_repo(tmp_path / "r", {"a.txt": "1"})
    repo.git.remote("add", "origin", "https://user:secret-token-value@github.com/octo/hello.git")
    info = inspect_folder(tmp_path / "r")
    assert info.remote_url == "https://github.com/octo/hello.git"
    assert "secret-token-value" not in repr(info)
    assert info.remote_slug == "octo/hello"


def test_ssh_remote_is_understood(tmp_path):
    repo = make_repo(tmp_path / "r", {"a.txt": "1"})
    repo.git.remote("add", "origin", "git@github.com:octo/hello.git")
    assert inspect_folder(tmp_path / "r").remote_slug == "octo/hello"


def test_changes_are_counted_and_follow_outside_edits(tmp_path):
    make_repo(tmp_path / "r", {"a.txt": "1"})
    assert inspect_folder(tmp_path / "r").changes == 0
    (tmp_path / "r" / "a.txt").write_text("2")
    (tmp_path / "r" / "b.txt").write_text("new")
    assert inspect_folder(tmp_path / "r").changes == 2


def test_git_not_installed_is_reported_not_raised(monkeypatch, tmp_path):
    monkeypatch.setattr(git_detect.shutil, "which", lambda name: None)
    info = inspect_folder(tmp_path)
    assert not info.is_repo and not info.git_available and "Git is not installed" in info.error


def test_missing_and_non_folder_paths(tmp_path):
    assert "no longer exists" in inspect_folder(tmp_path / "gone").error
    (tmp_path / "file.txt").write_text("x")
    assert "not a folder" in inspect_folder(tmp_path / "file.txt").error


def test_dubious_ownership_is_an_error_with_details(monkeypatch, tmp_path):
    monkeypatch.setattr(git_detect, "run_git", lambda *a, **k: (128, "", "fatal: detected dubious ownership in repository at 'X'"))
    info = inspect_folder(tmp_path)
    assert not info.is_repo and "another user" in info.error and "dubious ownership" in info.detail


def test_url_helpers():
    assert strip_credentials("https://me:tok@github.com/a/b.git") == "https://github.com/a/b.git"
    assert strip_credentials("git@github.com:a/b.git") == "git@github.com:a/b.git"
    assert remote_slug("https://github.com/a/b") == "a/b"
    assert remote_slug("") == ""


# ---------------------------------------------------------------- interface states
def test_interface_states():
    repo = GitInfo(is_repo=True, name="r", branch="main")
    assert connection_state(False, GitInfo(), "disconnected") == "A"
    assert connection_state(True, GitInfo(), "disconnected") == "B"
    assert connection_state(True, GitInfo(), "connected") == "B"  # a normal folder never shows GitHub, even when signed in
    assert connection_state(True, repo, "disconnected") == "C"
    assert connection_state(True, repo, "connected") == "D"
    assert connection_state(True, repo, "failed") == "E"
    assert connection_state(True, GitInfo(error="Permission was denied for this folder."), "disconnected") == "E"


# ---------------------------------------------------------------- opening folders
def test_opening_a_subfolder_of_a_repository_turns_git_on(tmp_path):
    make_repo(tmp_path / "repo", {"pkg/a.txt": "1"})
    opened = repository_service.RepositoryService().open_scratch(str(tmp_path / "repo" / "pkg"))
    assert opened.is_git and opened.git is not None and opened.git_info.name == "repo"
    assert opened.name == "pkg"


def test_opening_a_normal_folder_keeps_git_off(tmp_path):
    folder = tmp_path / "plain folder"
    folder.mkdir()
    opened = repository_service.RepositoryService().open_scratch(str(folder))
    assert not opened.is_git and opened.git is None and opened.name == "plain folder"
    assert str(opened.path) == str(folder.resolve())  # the real path, not a copy


def test_studios_own_scratch_folder_is_never_a_repository(tmp_path, monkeypatch):
    make_repo(tmp_path / "install", {"a.txt": "1"})
    scratch = tmp_path / "install" / "workspaces" / "scratch"
    scratch.mkdir(parents=True)
    monkeypatch.setattr(type(repository_service.settings), "scratch_path", property(lambda self: scratch))
    opened = repository_service.RepositoryService().open_scratch(str(scratch))
    assert not opened.is_git and opened.git is None
    assert not opened.refresh_git().is_repo
    other = repository_service.RepositoryService().open_scratch(str(tmp_path / "install"))
    assert other.is_git  # a folder the user selects is still checked with Git


def test_refresh_notices_git_init_and_removal_outside_the_studio(tmp_path):
    folder = tmp_path / "work"
    folder.mkdir()
    opened = repository_service.RepositoryService().open_scratch(str(folder))
    assert opened.git is None
    Repo.init(folder)
    assert opened.refresh_git().is_repo and opened.git is not None
    shutil.rmtree(folder / ".git", ignore_errors=True)
    assert not opened.refresh_git().is_repo and opened.git is None


def test_a_folder_that_was_moved_is_reported(tmp_path, monkeypatch):
    service = repository_service.RepositoryService()
    monkeypatch.setattr(repository_service, "STATE_FILE", tmp_path / "state.json")
    folder = tmp_path / "proj"
    folder.mkdir()
    service.remember("abcd1234", folder)
    assert service.missing_path("abcd1234") == ""
    folder.rmdir()
    assert service.missing_path("abcd1234") == str(folder)
    assert service.recall("abcd1234") is None


# ---------------------------------------------------------------- Git operations from a nested folder
def test_git_service_works_from_a_subfolder(tmp_path):
    repo = make_repo(tmp_path / "repo", {"top.txt": "t", "pkg/a.txt": "old"})
    (tmp_path / "repo" / "pkg" / "a.txt").write_text("new")
    (tmp_path / "repo" / "pkg" / "fresh.txt").write_text("f")
    (tmp_path / "repo" / "top.txt").write_text("changed outside the opened folder")
    git = GitService(tmp_path / "repo" / "pkg")
    assert git.prefix == "pkg"
    files = {item["path"]: item for item in git.status()["files"]}
    assert set(files) == {"a.txt", "fresh.txt"}  # paths are relative to the opened folder; the sibling change is not listed
    git.stage(["a.txt"])
    assert {item["path"]: item["staged"] for item in git.status()["files"]}["a.txt"]
    versions = git.file_versions("a.txt")
    assert versions["path"] == "a.txt" and versions["original"] == "old" and versions["modified"] == "new"
    git.discard(["fresh.txt"])
    assert not (tmp_path / "repo" / "pkg" / "fresh.txt").exists()
    assert (tmp_path / "repo" / "top.txt").read_text() == "changed outside the opened folder"
    assert repo.git.rev_parse("--show-toplevel")


def test_index_lists_files_relative_to_the_opened_folder(tmp_path):
    make_repo(tmp_path / "repo", {"top.txt": "t", "pkg/a.txt": "1"})
    opened = repository_service.RepositoryService().open_scratch(str(tmp_path / "repo" / "pkg"))
    assert "a.txt" in opened.index.files and "top.txt" not in opened.index.files


# ---------------------------------------------------------------- credential storage
class FakeKeyring:
    def __init__(self):
        self.items = {}

    def set_password(self, service, account, value):
        self.items[(service, account)] = value

    def get_password(self, service, account):
        return self.items.get((service, account))

    def delete_password(self, service, account):
        self.items.pop((service, account), None)


def test_token_goes_to_the_credential_manager_when_available(monkeypatch):
    fake = FakeKeyring()
    monkeypatch.setenv("STUDIO_HOSTED", "0")
    monkeypatch.setattr(secret_store, "_keyring", lambda: fake)
    assert secret_store.backend() == "keyring"
    assert secret_store.save("ghp_exampletoken1234567890") == "keyring"
    assert secret_store.load() == "ghp_exampletoken1234567890"
    secret_store.delete()
    assert secret_store.load() == ""


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows only")
def test_token_is_encrypted_on_disk_with_dpapi(monkeypatch, tmp_path):
    monkeypatch.setenv("STUDIO_HOSTED", "0")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(secret_store, "_keyring", lambda: None)
    token = "ghp_exampletoken1234567890"
    assert secret_store.save(token) == "dpapi"
    stored = (tmp_path / "RKStudio" / "github-token.bin").read_bytes()
    assert token.encode() not in stored
    assert secret_store.load() == token
    secret_store.delete()
    assert secret_store.load() == ""


def test_a_hosted_deployment_never_persists_tokens(monkeypatch, tmp_path):
    monkeypatch.setenv("STUDIO_HOSTED", "1")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(secret_store, "_keyring", lambda: FakeKeyring())
    assert secret_store.backend() == ""
    assert secret_store.save("ghp_exampletoken1234567890") == ""
    assert secret_store.load() == ""
    assert not list(tmp_path.iterdir())
