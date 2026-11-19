"""Durable storage: a wiped host gets its accounts, projects and files back, and a bad start never overwrites a good backup."""

from __future__ import annotations

import io
import sqlite3
import tarfile
from pathlib import Path

import pytest

from ats import persistence
from ats.persistence import Durable, FolderBackend, Layout, make_snapshot, restore_snapshot, signature


def _layout(root: Path) -> Layout:
    return Layout(data_dir=root, db=root / "studio.db", users_db=root / "users.db")


def _seed(layout: Layout) -> None:
    layout.data_dir.mkdir(parents=True, exist_ok=True)
    for path, table in ((layout.db, "projects"), (layout.users_db, "users")):
        conn = sqlite3.connect(path)
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute(f"CREATE TABLE {table} (id TEXT PRIMARY KEY, name TEXT)")
        conn.execute(f"INSERT INTO {table} VALUES ('1', 'kept')")
        conn.commit()
        conn.close()
    (layout.data_dir / "projects" / "p1" / "discovery").mkdir(parents=True)
    (layout.data_dir / "projects" / "p1" / "discovery" / "home.png").write_bytes(b"png-bytes")
    (layout.data_dir / "secure").mkdir()
    (layout.data_dir / "secure" / "connections.key").write_bytes(b"secret-key")
    (layout.data_dir / "runs" / "r1").mkdir(parents=True)
    (layout.data_dir / "runs" / "r1" / "workspace.txt").write_text("temporary")


def _rows(path: Path, table: str) -> list[tuple]:
    conn = sqlite3.connect(path)
    try:
        return conn.execute(f"SELECT id, name FROM {table}").fetchall()
    finally:
        conn.close()


def test_snapshot_and_restore_bring_everything_back(tmp_path) -> None:
    source = _layout(tmp_path / "before")
    _seed(source)
    archive = tmp_path / "snap.tar.gz"
    assert make_snapshot(source, archive) == 4  # two databases, the screenshot and the key; run workspaces are not part of it

    wiped = _layout(tmp_path / "after")  # a restarted host: nothing on disk
    assert wiped.is_fresh()
    assert restore_snapshot(wiped, archive) == 4
    assert _rows(wiped.db, "projects") == [("1", "kept")]
    assert _rows(wiped.users_db, "users") == [("1", "kept")]
    assert (wiped.data_dir / "projects" / "p1" / "discovery" / "home.png").read_bytes() == b"png-bytes"
    assert (wiped.data_dir / "secure" / "connections.key").read_bytes() == b"secret-key"
    assert not (wiped.data_dir / "runs").exists()


def test_a_fresh_host_restores_the_newest_snapshot_automatically(tmp_path) -> None:
    backup = FolderBackend(tmp_path / "backup")
    old_host = _layout(tmp_path / "host1")
    _seed(old_host)
    first = Durable(old_host, backup)
    first.status.uploads_enabled = True
    assert first.snapshot_now()

    new_host = _layout(tmp_path / "host2")
    second = Durable(new_host, backup)
    second.restore_if_fresh()
    assert second.status.restored_from.startswith("snapshot-")
    assert second.status.uploads_enabled
    assert _rows(new_host.db, "projects") == [("1", "kept")]


def test_existing_local_data_is_never_overwritten_by_a_restore(tmp_path) -> None:
    backup = FolderBackend(tmp_path / "backup")
    other = _layout(tmp_path / "other")
    _seed(other)
    seeded = Durable(other, backup)
    seeded.status.uploads_enabled = True
    seeded.snapshot_now()

    local = _layout(tmp_path / "local")
    local.data_dir.mkdir()
    conn = sqlite3.connect(local.db)
    conn.execute("CREATE TABLE projects (id TEXT PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO projects VALUES ('9', 'local only')")
    conn.commit()
    conn.close()
    service = Durable(local, backup)
    service.restore_if_fresh()
    assert service.status.restored_from == ""
    assert _rows(local.db, "projects") == [("9", "local only")]


def test_a_failed_restore_switches_uploads_off(tmp_path) -> None:
    class Broken(FolderBackend):
        def get(self, name: str, target: Path) -> None:
            raise OSError("network down")

    backup = Broken(tmp_path / "backup")
    seeded = _layout(tmp_path / "seed")
    _seed(seeded)
    good = Durable(seeded, FolderBackend(tmp_path / "backup"))
    good.status.uploads_enabled = True
    good.snapshot_now()

    fresh = Durable(_layout(tmp_path / "fresh"), backup)
    fresh.restore_if_fresh()
    assert "network down" in fresh.status.restore_error
    assert not fresh.status.uploads_enabled
    assert fresh.snapshot_now(force=True) is False  # an empty start must not replace the good backup
    assert len(backup.names()) == 1


def test_first_start_with_an_empty_backup_enables_uploads(tmp_path) -> None:
    service = Durable(_layout(tmp_path / "new"), FolderBackend(tmp_path / "backup"))
    service.restore_if_fresh()
    assert service.status.uploads_enabled and not service.status.restore_error


def test_unchanged_data_is_not_uploaded_again_and_old_snapshots_are_pruned(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(persistence, "KEEP", 2)
    backup = FolderBackend(tmp_path / "backup")
    layout = _layout(tmp_path / "host")
    _seed(layout)
    service = Durable(layout, backup)
    service.status.uploads_enabled = True
    assert service.snapshot_now()
    assert service.snapshot_now() is False  # nothing changed

    for index in range(3):  # force three more with distinct names
        (backup.folder / f"snapshot-2000010{index}T000000.tar.gz").write_bytes(b"x")
    assert service.snapshot_now(force=True)
    assert len(backup.names()) == 2
    assert backup.names()[-1] == service.status.last_snapshot_name  # the newest one always survives


def test_a_change_is_noticed(tmp_path) -> None:
    layout = _layout(tmp_path / "host")
    _seed(layout)
    before = signature(layout)
    conn = sqlite3.connect(layout.db)
    conn.execute("INSERT INTO projects VALUES ('2', 'new')")
    conn.commit()
    conn.close()
    assert signature(layout) != before


def test_archive_members_outside_the_known_folders_are_ignored(tmp_path) -> None:
    archive_path = tmp_path / "evil.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        for name in ("../escape.txt", "/abs.txt", "files/projects/../../escape2.txt", "random.txt", "files/secure/ok.txt"):
            data = b"x"
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    layout = _layout(tmp_path / "host")
    assert restore_snapshot(layout, archive_path) == 1
    assert (layout.data_dir / "secure" / "ok.txt").exists()
    assert not (tmp_path / "escape.txt").exists() and not (tmp_path / "escape2.txt").exists()


def test_backend_choice_follows_the_settings(tmp_path) -> None:
    assert persistence.backend_from_settings(lambda _name: "") is None
    chosen = persistence.backend_from_settings(lambda name: str(tmp_path) if name == "BACKUP_DIR" else "")
    assert isinstance(chosen, FolderBackend)


@pytest.mark.parametrize(("root", "home", "expected"), [("/mount/src/rk/app", "", True), ("/srv/app", "/home/adminuser", True), ("/srv/app", "/root", False)])
def test_ephemeral_host_detection(monkeypatch, root, home, expected) -> None:
    monkeypatch.setenv("HOME", home)
    assert persistence.is_ephemeral_host(Path(root)) is expected
