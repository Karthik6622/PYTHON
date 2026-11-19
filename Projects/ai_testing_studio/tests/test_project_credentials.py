from streamlit.testing.v1 import AppTest

SCRIPT = """
import streamlit as st
from ats.ui.session import get_services
from ats.ui import page_projects
st.session_state["owner_id"] = "{owner}"
page_projects.render(get_services())
"""
OWNER = "d" * 32


def field(app, label):
    return next(t for t in app.text_input if t.label == label)


def test_credentials_typed_on_the_project_form_are_saved_encrypted() -> None:
    app = AppTest.from_string(SCRIPT.format(owner=OWNER), default_timeout=30).run()
    assert not app.exception, [e.value for e in app.exception]
    field(app, "Project name").input("Secured")
    field(app, "Application URL").input("http://127.0.0.1:9")
    field(app, "Username or email").input("tester@example.com")
    field(app, "Password").input("S3cret!pw")
    next(b for b in app.button if "Create project" in b.label).click().run()
    assert not app.exception, [e.value for e in app.exception]

    from ats.ui.session import get_services

    svc = get_services()
    project = next(p for p in svc.repo.list_projects(OWNER) if p.name == "Secured")
    assert project.auth.mode == "env_credentials"
    env = svc.connections.environment(project.id)
    assert env[project.auth.username_env] == "tester@example.com" and env[project.auth.password_env] == "S3cret!pw"
    rows = svc.repo.list_connection_rows(project.id)
    assert rows and all("S3cret!pw" not in r["value_enc"] and "tester@example.com" not in r["value_enc"] for r in rows)

