"""Streamlit AppTest: the app starts, the tabs render and a plan can be created with a fake model."""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from conftest import FakeLLM

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def test_app_creates_plan_and_renders_every_tab(tmp_path, monkeypatch):
    import services.project_storage as storage_module
    import components.state as state_module

    monkeypatch.setattr(storage_module, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(state_module, "NvidiaClient", FakeLLM)

    at = AppTest.from_file(APP, default_timeout=60).run()
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
