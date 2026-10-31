"""Smoke tests for the Streamlit pages using Streamlit's AppTest harness (no browser needed)."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

OWNER = "a" * 32

SCRIPT = """
import streamlit as st
from ats.ui.session import get_services
svc = get_services()
st.session_state["owner_id"] = "{owner}"
existing = svc.repo.list_projects("{owner}")
project = existing[0] if existing else svc.repo.create_project("{owner}", name="Demo", url="http://127.0.0.1:9", environment="QA")
st.session_state["project_id"] = project.id
from ats.ui import {module}
{module}.{call}(svc)
"""

PAGES = [
    ("page_projects", "render"),
    ("page_discovery", "render"),
    ("page_review", "render_scenarios"),
    ("page_review", "render_test_cases"),
    ("page_automation", "render"),
    ("page_github", "render"),
    ("page_execute", "render"),
    ("page_results", "render"),
    ("page_reports", "render"),
    ("page_audit", "render"),
]


@pytest.mark.parametrize(("module", "call"), PAGES)
def test_page_renders_without_error(module: str, call: str) -> None:
    app = AppTest.from_string(SCRIPT.format(owner=OWNER, module=module, call=call), default_timeout=30).run()
    assert not app.exception, [e.value for e in app.exception]


SEEDED = """
import streamlit as st
from ats.ui.session import get_services
svc = get_services()
st.session_state["owner_id"] = "{owner}"
st.session_state["project_id"] = "{project_id}"
from ats.ui import {module}
{module}.{call}(svc)
"""


@pytest.mark.parametrize("module", ["page_results", "page_reports", "page_execute", "page_projects", "page_audit", "page_github"])
def test_pages_render_with_a_finished_run(repo, monkeypatch, browser_ready, module) -> None:
    if not browser_ready:
        pytest.skip("Chromium is not installed")
    from ats.services import build_services
    from tests.test_analysis import build_service, classification, healing_reply, make_failed_execution

    service, executor, _client, _ = build_service(repo, classification(), healing_reply(), "PASS")
    project, ctx = make_failed_execution(repo, executor, error="Timeout 30000ms exceeded waiting for get_by_role('button', name='Sign in')")
    service.post_run(ctx)  # manual policy: leaves a proposed healing for the review UI
    assert repo.list_healings(project.id, ctx.execution_id)
    repo.db.execute("UPDATE projects SET owner_id = ? WHERE id = ?", (OWNER, project.id))
    svc = build_services(repo)
    monkeypatch.setattr("ats.ui.session.get_services", lambda: svc)
    app = AppTest.from_string(SEEDED.format(owner=OWNER, project_id=project.id, module=module, call="render"), default_timeout=60).run()
    assert not app.exception, [e.value for e in app.exception]
    if module == "page_results":
        assert any("Self-healing" in s.value for s in app.subheader), "healing panel missing"
        assert any(b.label == "Approve and verify" for b in app.button)


def test_app_entry_point_loads() -> None:
    app = AppTest.from_file(str(Path(__file__).resolve().parent.parent / "app.py"), default_timeout=30).run()
    assert not app.exception, [e.value for e in app.exception]


def test_project_form_creates_a_project() -> None:
    script = SCRIPT.format(owner="b" * 32, module="page_projects", call="render").replace('project = existing[0] if existing else svc.repo.create_project("' + "b" * 32 + '", name="Demo", url="http://127.0.0.1:9", environment="QA")\nst.session_state["project_id"] = project.id\n', "")
    app = AppTest.from_string(script, default_timeout=30).run()
    assert not app.exception
    names = [t for t in app.text_input if t.label == "Project name"]
    urls = [t for t in app.text_input if t.label == "Application URL"]
    assert names and urls
    names[0].input("Shop")
    urls[0].input("http://127.0.0.1:9")
    submit = [b for b in app.button if "Create project" in b.label]
    assert submit
    submit[0].click().run()
    assert not app.exception, [e.value for e in app.exception]
    from ats.ui.session import get_services

    assert any(p.name == "Shop" for p in get_services().repo.list_projects("b" * 32))
