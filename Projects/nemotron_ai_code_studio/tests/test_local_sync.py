"""Server half of the browser folder feature: validation of what the browser sends, and planning of what to write back."""

import base64

import pytest

from studio.services import local_sync
from studio.services.local_sync import LocalLink, SyncError


def test_accept_rejects_unsafe_secret_and_tool_paths():
    assert local_sync.accept("src/app.py") == "src/app.py"
    assert local_sync.accept("a\\b.py") == "a/b.py"
    for bad in ["../x.py", "/etc/passwd", "C:/x.py", "a/../../b", ".env", "src/.env.local", "id_rsa", "node_modules/x.js",
                ".git/config", "a/.venv/lib/x.py", "logo.png", "", None, "a\x00b"]:
        assert local_sync.accept(bad) is None, bad
    assert local_sync.accept(".env.example") == ".env.example"
    assert local_sync.accept("logo.png", text_only=False) == "logo.png"


def test_clean_name_is_a_single_safe_folder_name():
    assert not {"/", "\\"} & set(local_sync.clean_name("../../evil"))
    assert local_sync.clean_name("..") == "my-folder"
    assert local_sync.clean_name("") == "my-folder"
    assert local_sync.clean_name("My Project") == "My Project"


def test_import_writes_text_files_skips_the_rest_and_removes_stale_ones(tmp_path):
    root = tmp_path / "ws"
    (root).mkdir()
    (root / "old.py").write_text("stale", encoding="utf-8")
    files = [
        {"path": "app.py", "content": "print(1)\n"},
        {"path": "src/util.py", "content": "x = 1\n"},
        {"path": "../escape.py", "content": "bad"},
        {"path": ".env", "content": "SECRET=1"},
        {"path": "node_modules/a.js", "content": "x"},
        {"path": "bin.png", "content": "x"},
        {"path": "n.py", "content": 5},
    ]
    assert local_sync.import_files(root, files).count == 2
    assert (root / "app.py").read_text(encoding="utf-8") == "print(1)\n"
    assert (root / "src" / "util.py").exists()
    assert not (root / "old.py").exists()
    assert not (tmp_path / "escape.py").exists()
    assert not (root / ".env").exists()


def test_import_keeps_line_endings_and_rejects_bad_input(tmp_path):
    local_sync.import_files(tmp_path / "ws", [{"path": "a.txt", "content": "a\r\nb\r\n"}])
    assert (tmp_path / "ws" / "a.txt").read_bytes() == b"a\r\nb\r\n"
    with pytest.raises(SyncError):
        local_sync.import_files(tmp_path / "ws", "not a list")


def test_import_over_the_budget_leaves_files_out_instead_of_refusing(tmp_path, monkeypatch):
    monkeypatch.setattr(local_sync, "MAX_TOTAL_BYTES", 10)
    files = [
        {"path": "big.py", "content": "x" * 8},
        {"path": "a.py", "content": "y" * 4},
        {"path": "b.py", "content": "z" * 5},
    ]
    result = local_sync.import_files(tmp_path / "ws", files)
    assert result.count == 2 and result.left_out == 1
    assert (tmp_path / "ws" / "a.py").exists() and (tmp_path / "ws" / "b.py").exists()
    assert not (tmp_path / "ws" / "big.py").exists()


def test_link_sends_new_changed_and_deleted_files_once_acknowledged(tmp_path):
    (tmp_path / "a.py").write_text("one", encoding="utf-8")
    link = LocalLink("proj", known=local_sync.scan(tmp_path))
    assert link.plan(tmp_path) is None

    (tmp_path / "b.py").write_text("two", encoding="utf-8")
    batch = link.plan(tmp_path)
    assert [w["path"] for w in batch["writes"]] == ["b.py"] and batch["deletes"] == []
    assert link.plan(tmp_path)["id"] == batch["id"]  # the same batch until the browser acknowledges it
    link.acknowledge("wrong-id")
    assert link.plan(tmp_path)["id"] == batch["id"]
    link.acknowledge(batch["id"])
    assert link.plan(tmp_path) is None

    (tmp_path / "a.py").write_text("one changed", encoding="utf-8")
    (tmp_path / "b.py").unlink()
    batch = link.plan(tmp_path)
    assert [w["content"] for w in batch["writes"]] == ["one changed"] and batch["deletes"] == ["b.py"]
    link.acknowledge(batch["id"])
    assert link.plan(tmp_path) is None


def test_link_with_nothing_known_exports_everything_in_batches(tmp_path, monkeypatch):
    monkeypatch.setattr(local_sync, "BATCH_FILES", 2)
    for i in range(5):
        (tmp_path / f"f{i}.py").write_text(str(i), encoding="utf-8")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "x.py").write_text("tool", encoding="utf-8")
    link = LocalLink("proj")
    sent = []
    while (batch := link.plan(tmp_path)) is not None:
        sent += [w["path"] for w in batch["writes"]]
        link.acknowledge(batch["id"])
    assert sorted(sent) == [f"f{i}.py" for i in range(5)]


def test_export_sends_binary_files_as_base64_and_skips_secrets(tmp_path):
    (tmp_path / "a.py").write_text("x", encoding="utf-8")
    (tmp_path / "img.png").write_bytes(b"\x89PNG\xff\xfe")
    (tmp_path / ".env").write_text("SECRET=1", encoding="utf-8")
    link = LocalLink("proj", fresh=True)
    batch = link.plan(tmp_path)
    by_path = {w["path"]: w for w in batch["writes"]}
    assert sorted(by_path) == ["a.py", "img.png"]
    assert by_path["a.py"]["content"] == "x"
    assert base64.b64decode(by_path["img.png"]["base64"]) == b"\x89PNG\xff\xfe"


def test_window_link_is_remembered_and_marked_synced(tmp_path, monkeypatch):
    from studio.services import repository_service as rs

    monkeypatch.setattr(rs, "STATE_FILE", tmp_path / "state.json")
    service = rs.RepositoryService()
    service.remember("win-1", tmp_path, link="my-folder", fresh=True)
    assert service.window_link("win-1") == ("my-folder", True)
    service.mark_synced("win-1")
    assert service.window_link("win-1") == ("my-folder", False)
    service.remember("win-2", tmp_path)
    assert service.window_link("win-2") == ("", False)
    assert service.window_link("unknown") == ("", False)