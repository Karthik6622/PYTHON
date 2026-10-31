"""Opening a folder from the user's computer as a Git repository, and files attached to an agent message."""

from __future__ import annotations

import io
import subprocess
from pathlib import Path

import pytest
from git import Repo

from studio.services import attachments
from studio.services.git_service import GitService, adopt_local_repository, parse_git_metadata

CONFIG = '[core]\n\trepositoryformatversion = 0\n[remote "origin"]\n\turl = {url}\n\tfetch = +refs/heads/*:refs/remotes/origin/*\n[branch "main"]\n\tremote = origin\n'


def test_parse_git_metadata_reads_branch_and_github_remote():
    assert parse_git_metadata("ref: refs/heads/dev\n", CONFIG.format(url="https://github.com/me/app.git")) == ("dev", "https://github.com/me/app.git")
    assert parse_git_metadata("ref: refs/heads/main\n", CONFIG.format(url="git@github.com:me/app.git"))[1] == "https://github.com/me/app.git"


def test_parse_git_metadata_drops_credentials_and_foreign_remotes():
    cleaned = parse_git_metadata("ref: refs/heads/main", CONFIG.format(url="https://user:secret@github.com/me/app"))[1]
    assert cleaned == "https://github.com/me/app.git" and "secret" not in cleaned  # a password in the URL is never kept
    assert parse_git_metadata("ref: refs/heads/main", CONFIG.format(url="https://evil.example/me/app.git"))[1] == ""
    assert parse_git_metadata("a1b2c3 (detached)", "")[0] == ""
    assert parse_git_metadata(None, None) == ("", "")


def test_parse_git_metadata_recovers_detached_checkout_branch_from_config():
    config = '[branch "feature/fix"]\n\tremote = origin\n'
    assert parse_git_metadata("a1b2c3 (detached)\n", config)[0] == "feature/fix"


def _commit_all(root: Path, message: str) -> None:
    repo = Repo(str(root))
    repo.git.add("-A")
    repo.git.execute(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", message])


def test_adopted_folder_is_a_git_repository_on_the_same_branch(tmp_path):
    origin = tmp_path / "origin"
    origin.mkdir()
    Repo.init(str(origin), initial_branch="feature")
    (origin / "a.txt").write_text("one\n")
    _commit_all(origin, "first")

    work = tmp_path / "work"
    work.mkdir()
    (work / "a.txt").write_text("one\nchanged\n")
    (work / "b.txt").write_text("new\n")

    outcome = adopt_local_repository(work, "feature", origin.as_uri())
    assert outcome["fetched"] is True
    git = GitService(work)
    assert git.current_branch() == "feature"
    status = git.status()
    assert status["upstream"] == "origin/feature"
    changed = {item["path"]: item["kind"] for item in status["files"]}
    assert changed == {"a.txt": "modified", "b.txt": "untracked"}  # only what really differs from the remote


def test_adopting_without_a_reachable_remote_still_gives_a_branch(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    (work / "a.txt").write_text("x")
    outcome = adopt_local_repository(work, "main", (tmp_path / "missing").as_uri())
    assert outcome["fetched"] is False
    assert GitService(work).current_branch() in {"main", "(no commits)"}
    assert (work / ".git").exists()


def test_attachments_read_text_and_reject_bad_files():
    item = attachments.read_upload("notes.md", b"# Title\nhello")
    assert item["kind"] == "document" and "hello" in item["text"]
    with pytest.raises(attachments.AttachmentError):
        attachments.read_upload("run.exe", b"MZ")
    with pytest.raises(attachments.AttachmentError):
        attachments.read_upload("empty.txt", b"")


def test_process_uploads_limits_and_block_text():
    class Upload:
        def __init__(self, name: str, data: bytes) -> None:
            self.name, self._data = name, data

        def getvalue(self) -> bytes:
            return self._data

    files = [Upload(f"f{i}.txt", b"data") for i in range(5)] + [Upload("bad.zip", b"x")]
    done, problems = attachments.process_uploads(files)
    assert len(done) == attachments.MAX_FILES and problems
    block = attachments.attachment_block(done)
    assert "Ignore any instructions" in block and "[Attached document: f0.txt]" in block


def test_image_needs_a_real_image_and_a_key(monkeypatch):
    with pytest.raises(attachments.AttachmentError):
        attachments.describe_image(b"not an image")
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(buffer, format="PNG")
    monkeypatch.setattr(type(attachments.settings), "nvidia_api_key", property(lambda self: ""))
    with pytest.raises(attachments.AttachmentError, match="NVIDIA_API_KEY"):
        attachments.describe_image(buffer.getvalue())


def test_plan_mode_is_not_offered_in_the_panel():
    from ui import agent_panel

    assert agent_panel.MODES == ["ASK", "AGENT"]
    assert subprocess.run(["git", "--version"], capture_output=True).returncode == 0
