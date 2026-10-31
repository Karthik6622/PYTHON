"""Streamlit AppTest: the app starts, the tabs render and a plan can be created with a fake model."""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from conftest import FakeLLM

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def signed_in_app(user_id: str) -> AppTest:
    """An app session that is already signed in as ``user_id`` (the login page itself is tested in test_auth.py)."""
    at = AppTest.from_file(APP, default_timeout=60)
    at.session_state["auth_user"] = {"id": user_id, "name": "Test Reader", "email": "reader@example.com"}
    return at


def test_app_creates_plan_and_renders_every_tab(tmp_path, monkeypatch):
    import services.project_storage as storage_module
    import components.state as state_module

    monkeypatch.setattr(storage_module, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(state_module, "NvidiaClient", FakeLLM)

    at = signed_in_app("u" + "1" * 32).run()
    assert not at.exception
    assert len(at.radio(key="nav").options) == 7
    assert any("Create Book Plan" in b.label for b in at.button)

    at.session_state["in_idea"] = "A lighthouse keeper protects a fishing village from a great storm."
    at.session_state["in_author"] = "Test Author"
    at.run()
    next(b for b in at.button if "Create Book Plan" in b.label).click()
    at.run()
    assert not at.exception, [e.value for e in at.exception]

    import time

    deadline = time.time() + 60
    while time.time() < deadline and not (at.session_state["book_plan"] is not None and at.session_state["generation_status"] == "planned"):
        time.sleep(0.2)
        at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.session_state["book_plan"] is not None
    assert at.session_state["generation_status"] == "planned"

    at.radio(key="nav").set_value("plan").run()
    assert not at.exception, [e.value for e in at.exception]
    next(b for b in at.button if "Generate Complete Book" in b.label).click()
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.session_state["nav"] == "chapters"

    import time

    deadline = time.time() + 60
    while time.time() < deadline and not (at.session_state["project"].status.stage == "completed" and at.session_state["nav"] == "preview"):
        time.sleep(0.2)
        at.run()
    assert at.session_state["project"].status.stage == "completed"
    assert at.session_state["nav"] == "preview"


def test_two_browsers_do_not_affect_each_other(tmp_path, monkeypatch):
    import time

    import components.state as state_module
    import services.project_storage as storage_module

    monkeypatch.setattr(storage_module, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(state_module, "NvidiaClient", FakeLLM)
    state_module.get_storage.clear()

    first = signed_in_app("u" + "a" * 32).run()
    second = signed_in_app("u" + "b" * 32).run()
    assert not first.exception and not second.exception
    assert first.session_state["owner_id"] != second.session_state["owner_id"]

    first.session_state["in_idea"] = "A lighthouse keeper protects a fishing village from a great storm."
    first.session_state["in_author"] = "First Author"
    first.run()
    next(b for b in first.button if "Create Book Plan" in b.label).click()
    first.run()

    deadline = time.time() + 60
    while time.time() < deadline and first.session_state["generation_status"] != "planned":
        time.sleep(0.2)
        first.run()
        second.run()  # the other browser keeps refreshing while the first one's plan is being made
    assert first.session_state["generation_status"] == "planned"

    second.run()
    assert not second.exception, [e.value for e in second.exception]
    assert second.session_state["project"] is None
    assert second.session_state["book_plan"] is None
    assert second.radio(key="nav").value == "create"
    assert not [m.value for m in second.success] and not [m.value for m in second.error]
    storage = state_module.get_storage()
    assert len(storage.list_projects(owner=first.session_state["owner_id"])) == 1
    assert storage.list_projects(owner=second.session_state["owner_id"]) == []
