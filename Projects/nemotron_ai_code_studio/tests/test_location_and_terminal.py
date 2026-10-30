import os
import sys
import time

import pytest

from studio.config import settings
from studio.services import folders, repository_service
from studio.services.command_policy import classify_command
from studio.services.git_service import GitService
from studio.services.github_service import parse_repository
from studio.services.terminal_hints import hint_for
from studio.services.terminal_service import clean_environment
from studio.services.workspace_service import WorkspaceService


@pytest.fixture(autouse=True)
def prefs(monkeypatch, tmp_path):
    monkeypatch.setattr(repository_service, "PREFS_FILE", tmp_path / "prefs.json")
    before = dict(settings._overrides)
    yield
    settings._overrides.clear()
    settings._overrides.update(before)


def test_prepare_location_creates_folder(tmp_path):
    target = tmp_path / "a" / "b"
    assert folders.prepare_location(str(target)) == target.resolve()
    assert target.is_dir()


def test_relative_and_empty_locations_rejected():
    with pytest.raises(folders.FolderError):
        folders.prepare_location("")
    with pytest.raises(folders.FolderError):
        folders.prepare_location("some/relative")


def test_file_is_not_a_location(tmp_path):
    file = tmp_path / "f.txt"
    file.write_text("x")
    with pytest.raises(folders.FolderError):
        folders.prepare_location(str(file))


def test_list_folders_skips_hidden_and_files(tmp_path):
    (tmp_path / "one").mkdir()
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "file.txt").write_text("x")
    listing = folders.list_folders(str(tmp_path))
    assert [item["name"] for item in listing["folders"]] == ["one"]
    assert listing["parent"] == str(tmp_path.parent)


def test_make_folder_rejects_bad_names(tmp_path):
    assert folders.make_folder(str(tmp_path), "ok").is_dir()
    for bad in ("", "..", "a/b", "a:b"):
        with pytest.raises(folders.FolderError):
            folders.make_folder(str(tmp_path), bad)


def test_choose_location_is_used_and_remembered(tmp_path):
    service = repository_service.RepositoryService()
    chosen = service.choose_location(str(tmp_path / "mine"))
    assert settings.workspace_path == chosen
    assert repository_service.PREFS_FILE.is_file()
    settings._overrides.pop("workspace_path")
    service.load_prefs()
    assert settings.workspace_path == chosen


def test_destination_uses_repo_name_like_git_clone(tmp_path):
    ref = parse_repository("Karthik6622/PYTHON")
    root = folders.prepare_location(str(tmp_path / "root"))
    assert repository_service.RepositoryService._destination(root, ref) == root / "PYTHON"


def test_destination_falls_back_when_name_taken_by_other_folder(tmp_path):
    ref = parse_repository("Karthik6622/PYTHON")
    root = folders.prepare_location(str(tmp_path / "root"))
    (root / "PYTHON").mkdir()
    (root / "PYTHON" / "x.txt").write_text("x")
    assert repository_service.RepositoryService._destination(root, ref) == root / ref.folder


def test_user_typed_installs_run_without_confirmation():
    assert classify_command("pip install requests").level == "approve"
    assert classify_command("pip install requests", user_initiated=True).level == "allow"
    assert classify_command("python -m playwright install chromium", user_initiated=True).level == "allow"
    assert classify_command("python -m playwright install chromium").level == "approve"


def test_dangerous_commands_stay_denied_for_the_user():
    assert classify_command("sudo rm -rf /", user_initiated=True).level == "deny"


def test_terminal_environment_puts_this_python_first():
    env = clean_environment()
    first = env["PATH"].split(os.pathsep)[0]
    assert os.path.normcase(first) == os.path.normcase(os.path.dirname(sys.executable))
    assert env["PIP_DISABLE_PIP_VERSION_CHECK"] == "1"


def test_hints():
    assert "pip install requests" in hint_for("python a.py", "ModuleNotFoundError: No module named 'requests'", 1)
    assert "opencv-python" in hint_for("python a.py", "ModuleNotFoundError: No module named 'cv2'", 1)
    assert "playwright install chromium" in hint_for("python a.py", "Executable doesn't exist at /x", 1)
    assert hint_for("python a.py", "ModuleNotFoundError: No module named 'x'", 0) == ""
    assert hint_for("ls", "", 1) == ""


def test_cached_status_reuses_until_token_changes(repo_dir):
    git = GitService(repo_dir)
    first = git.cached_status(1)
    assert git.cached_status(1) is first
    assert git.cached_status(2) is not first


def test_workspace_version_bumps_on_change(repo_dir):
    workspace = WorkspaceService(repo_dir)
    before = workspace.version
    workspace.write_text("new_file.txt", "hi")
    assert workspace.version == before + 1
    time.sleep(0)
