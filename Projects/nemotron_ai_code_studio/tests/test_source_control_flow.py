"""The Source Control panel's git calls, end to end against a local bare repository standing in for GitHub."""

from git import Repo

from studio.services.git_service import GitService


def _clone(tmp_path):
    remote = tmp_path / "remote.git"
    Repo.init(remote, bare=True)
    seed = tmp_path / "seed"
    seed.mkdir()
    repo = Repo.init(seed)
    (seed / "a.txt").write_text("1", encoding="utf-8")
    repo.git.add("-A")
    repo.git.execute(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "first"])
    repo.create_remote("origin", str(remote))
    repo.git.push("--set-upstream", "origin", "HEAD:refs/heads/main")
    return remote, seed, repo


def test_edit_stage_commit_push_flow(tmp_path):
    remote, seed, repo = _clone(tmp_path)
    git = GitService(seed)
    assert git.status()["clean"] and git.status()["ahead"] == 0

    (seed / "a.txt").write_text("2", encoding="utf-8")
    (seed / "b.txt").write_text("new", encoding="utf-8")
    status = git.status()
    assert not status["clean"] and len(status["files"]) == 2  # the badge counts these

    git.stage(None)
    assert all(entry["staged"] for entry in git.status()["files"])
    commit = git.commit("second")
    assert commit["message"] == "second"
    after = git.status()
    assert after["clean"] and after["ahead"] == 1  # committed, not pushed yet: the badge stays
    assert git.last_commit()["pushed"] is False

    git.push()
    done = git.status()
    assert done["clean"] and done["ahead"] == 0  # pushed: the badge goes away
    assert git.last_commit()["pushed"] is True


def test_pull_fast_forwards_and_updates_status_cache(tmp_path):
    remote, seed, _ = _clone(tmp_path)
    other = tmp_path / "other"
    Repo.clone_from(str(remote), other, branch="main")
    (other / "c.txt").write_text("from elsewhere", encoding="utf-8")
    peer = Repo(other)
    peer.git.add("-A")
    peer.git.execute(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "elsewhere"])
    peer.git.push()

    git = GitService(seed)
    git.fetch()
    assert git.cached_status("v1")["behind"] == 1
    git.pull()
    assert git.cached_status("v1")["behind"] == 0 and (seed / "c.txt").exists()
