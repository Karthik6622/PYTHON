"""Piece-by-piece transfer of a local folder: each piece is acknowledged, and the last piece starts the import."""

from ui import local_folder


def _run(monkeypatch, event):
    monkeypatch.setattr(local_folder, "_event", lambda key, name: event)
    local_folder._on_chunk()


def test_pieces_are_acknowledged_and_the_last_one_finishes(monkeypatch):
    state = {}
    finished = []
    monkeypatch.setattr(local_folder.st, "session_state", state)
    monkeypatch.setattr(local_folder, "_finish", lambda pending: finished.append(pending))

    _run(monkeypatch, {"job": "j1", "index": 0, "total": 2, "name": "proj", "meta": {"skipped": 1},
                       "files": [{"path": "a.py", "content": "x"}]})
    assert state[local_folder._ACK_KEY] == {"job": "j1", "count": 1}
    assert finished == []

    _run(monkeypatch, {"job": "j1", "index": 1, "total": 2, "name": "proj", "meta": None,
                       "files": [{"path": "b.py", "content": "y"}]})
    assert state[local_folder._ACK_KEY] == {"job": "j1", "count": 2}
    assert len(finished) == 1
    assert [item["path"] for item in finished[0]["files"]] == ["a.py", "b.py"]
    assert finished[0]["meta"] == {"skipped": 1}
    assert finished[0]["name"] == "proj"
    assert local_folder._IMPORT_KEY not in state


def test_single_piece_folder_finishes_at_once(monkeypatch):
    state = {}
    finished = []
    monkeypatch.setattr(local_folder.st, "session_state", state)
    monkeypatch.setattr(local_folder, "_finish", lambda pending: finished.append(pending))

    _run(monkeypatch, {"job": "j3", "index": 0, "total": 1, "name": "solo", "meta": {}, "files": []})
    assert len(finished) == 1
    assert state[local_folder._ACK_KEY] == {"job": "j3", "count": 1}


def test_out_of_order_piece_is_not_acknowledged(monkeypatch):
    state = {}
    monkeypatch.setattr(local_folder.st, "session_state", state)
    monkeypatch.setattr(local_folder, "_finish", lambda pending: None)

    _run(monkeypatch, {"job": "j2", "index": 1, "total": 3, "name": "p", "meta": None, "files": []})
    assert local_folder._ACK_KEY not in state
