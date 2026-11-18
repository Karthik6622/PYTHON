"""Sign-in check after discovery: deterministic signals, the merge with the model, the workflow order and the Connections page."""

from __future__ import annotations

from streamlit.testing.v1 import AppTest

from ats.ai.agents import AuthRequirementAgent
from ats.ai.agents.discovery_agents import AuthRequirement, AuthRequirementCheck
from ats.discovery.authcheck import auth_signals, build_authentication
from ats.discovery.service import DiscoveryService
from ats.models import DiscoveryResult, PageSnapshot
from ats.services import build_services
from ats.workflow import compute_workflow, next_page
from tests.fakes import FakeClient

OWNER = "d" * 32
LOGIN_PAGE = "http://127.0.0.1:9/login"


def _result(*pages: PageSnapshot) -> DiscoveryResult:
    return DiscoveryResult(start_url="http://127.0.0.1:9", pages=list(pages))


def _login_result() -> DiscoveryResult:
    return _result(PageSnapshot(url=LOGIN_PAGE, title="Login", elements=[{"tag": "input", "type": "password", "name": "Password", "visible": True}]))


def _silent(*_args, **_kwargs) -> None:  # noqa: ANN002, ANN003
    return None


# ------------------------------------------------------------------ (a) deterministic signals
def test_password_field_is_a_ui_account_signal():
    signals = auth_signals(_login_result())
    assert signals == [{"kind": "ui_account", "where": "Login", "evidence": "password field on Login", "confidence": "high", "source": "signal"}]


def test_pages_without_evidence_give_no_signal():
    home = PageSnapshot(url="http://127.0.0.1:9/", title="Home", elements=[{"tag": "input", "type": "text", "name": "Search", "visible": True}])
    assert auth_signals(_result(home)) == []


def test_http_401_and_key_parameters_are_signals_and_values_never_appear():
    denied = PageSnapshot(
        url="http://127.0.0.1:9/app", title="App", status=401, requires_auth=True,
        network=[{"method": "GET", "url": "http://127.0.0.1:9/api/me?api_key=SECRET-VALUE", "status": 401}],
    )  # fmt: skip
    signals = {item["kind"]: item for item in auth_signals(_result(denied))}
    assert signals["ui_account"]["confidence"] == "high"
    assert "HTTP 401" in signals["ui_account"]["evidence"]
    assert signals["api_key"]["evidence"] == "GET /api/me sends a 'api_key' query parameter"
    assert "SECRET-VALUE" not in str(signals)


# ------------------------------------------------------------------ (b) merge
def test_merge_dedupes_by_kind_signals_win_and_the_model_summary_is_kept():
    check = AuthRequirementCheck(
        requires_authentication=True,
        summary="The login form needs a UI test account.",
        requirements=[
            AuthRequirement(kind="ui_account", where="Sign-in", evidence="model guess", confidence="low"),
            {"kind": "OAuth", "where": "/token", "evidence": "token endpoint", "confidence": "HIGH"},
        ],
    )
    merged = build_authentication(auth_signals(_login_result()), check, now="2026-01-01T00:00:00+00:00")
    assert [item["kind"] for item in merged["requirements"]] == ["ui_account", "oauth2"]
    by_kind = {item["kind"]: item for item in merged["requirements"]}
    assert by_kind["ui_account"]["source"] == "signal" and by_kind["ui_account"]["evidence"] == "password field on Login"
    assert by_kind["oauth2"]["source"] == "model" and by_kind["oauth2"]["confidence"] == "high"
    assert merged["summary"] == "The login form needs a UI test account."
    assert merged["requires_authentication"] is True
    assert merged["checked_by"] == "model+signals" and merged["checked_at"] == "2026-01-01T00:00:00+00:00"


def test_without_a_model_the_summary_comes_from_the_signals():
    merged = build_authentication(auth_signals(_login_result()))
    assert merged["checked_by"] == "signals" and merged["requires_authentication"] is True
    assert "sign-in" in merged["summary"]


def test_a_model_summary_that_contradicts_the_evidence_is_not_used():
    merged = build_authentication(auth_signals(_login_result()), AuthRequirementCheck(requires_authentication=False, summary="No sign-in is needed."))
    assert merged["requires_authentication"] is True
    assert merged["summary"] != "No sign-in is needed."


def test_auth_check_asks_the_model_and_keeps_the_existing_analysis(repo):
    reply = {
        "requires_authentication": True,
        "summary": "The application has a sign-in form, so the tests need a UI test account.",
        "requirements": [{"kind": "ui_account", "where": "Login", "evidence": "password field", "confidence": "high"}],
    }
    client = FakeClient({"Sign-in Requirements Agent": reply})
    service = DiscoveryService(repo, auth_agent=AuthRequirementAgent(client=client, repository=repo))
    project = repo.create_project("owner", name="Shop", url="http://127.0.0.1:9")
    result = _login_result()
    result.analysis = {"modules": [{"name": "Login"}], "risks": ["captcha"]}
    service._auth_check(project, result, _silent)
    assert client.count("Sign-in Requirements Agent") == 1
    assert result.analysis["modules"] == [{"name": "Login"}] and result.analysis["risks"] == ["captcha"]
    auth = result.analysis["authentication"]
    assert auth["checked_by"] == "model+signals"
    assert auth["summary"] == reply["summary"]
    assert [item["kind"] for item in auth["requirements"]] == ["ui_account"]


def test_a_failing_model_keeps_the_signals_and_adds_a_warning(repo):
    def broken(_system, _payload):  # noqa: ANN001, ANN202
        raise RuntimeError("model unavailable")

    service = DiscoveryService(repo, auth_agent=AuthRequirementAgent(client=FakeClient({"Sign-in Requirements Agent": broken}), repository=repo))
    project = repo.create_project("owner", name="Shop", url="http://127.0.0.1:9")
    result = _login_result()
    service._auth_check(project, result, _silent)
    auth = result.analysis["authentication"]
    assert auth["checked_by"] == "signals" and auth["requires_authentication"] is True
    assert any("sign-in evidence" in warning for warning in result.warnings)


# ------------------------------------------------------------------ (c) workflow order
def test_discover_waits_for_the_connections_of_the_latest_discovery(repo):
    project = repo.create_project("owner", name="Shop", url="http://127.0.0.1:9")
    first = repo.start_discovery(project.id)
    repo.finish_discovery(first, "completed", _login_result())

    state = compute_workflow(repo, project)
    assert state.stage("Discover").status == "current" and state.stage("Discover").detail == "confirm connections"
    assert next_page(state) == "connections"
    assert state.next_step == "Confirm the connections and sign-in details."

    repo.audit(project.id, "user", "connections.confirmed", "connections", {"discovery_id": first})
    state = compute_workflow(repo, project)
    assert state.stage("Discover").status == "done"
    assert next_page(state) == "scenarios"

    second = repo.start_discovery(project.id)  # a newer discovery makes the earlier confirmation stale
    repo.finish_discovery(second, "completed", _login_result())
    assert next_page(compute_workflow(repo, project)) == "connections"


# ------------------------------------------------------------------ (d) Connections page
CONNECTIONS = """
import streamlit as st
from ats.ui.session import get_services
svc = get_services()
st.session_state["owner_id"] = "{owner}"
st.session_state["project_id"] = "{project_id}"
from ats.ui import page_connections
page_connections.render(svc)
"""

AUTH_REQUIRED = {
    "authentication": {
        "requires_authentication": True,
        "summary": "The login form needs a test account.",
        "requirements": [
            {"kind": "ui_account", "where": "Login", "evidence": "password field on Login", "confidence": "high", "source": "signal"},
            {"kind": "api_key", "where": "/api/items", "evidence": "model guess", "confidence": "low", "source": "model"},
        ],
        "checked_by": "model+signals",
        "checked_at": "2026-01-01T00:00:00+00:00",
    }
}


def _page(repo, monkeypatch, *, analysis=None, completed=True):  # noqa: ANN001, ANN202
    project = repo.create_project(OWNER, name="Shop", url="http://127.0.0.1:9")
    if completed:
        discovery = repo.start_discovery(project.id)
        result = _login_result()
        result.analysis = analysis or {}
        repo.finish_discovery(discovery, "completed", result)
    svc = build_services(repo)
    monkeypatch.setattr("ats.ui.session.get_services", lambda: svc)
    return project, svc


def _run(project) -> AppTest:  # noqa: ANN001
    app = AppTest.from_string(CONNECTIONS.format(owner=OWNER, project_id=project.id), default_timeout=60).run()
    assert not app.exception, [e.value for e in app.exception]
    return app


def test_connections_page_without_discovery_points_to_discovery(repo, monkeypatch):
    project, _svc = _page(repo, monkeypatch, completed=False)
    app = _run(project)
    assert any("Run website discovery first" in item.value for item in app.info)
    assert not any(button.label == "Continue to scenarios" for button in app.button)


def test_discovery_from_before_the_check_asks_to_run_it_again(repo, monkeypatch):
    project, _svc = _page(repo, monkeypatch, analysis={"modules": [], "risks": []})
    app = _run(project)
    assert any("Run discovery again" in item.value for item in app.info)
    assert any(button.label == "Run discovery again" for button in app.button)


def test_required_sign_in_is_shown_with_missing_status_and_set_up(repo, monkeypatch):
    project, _svc = _page(repo, monkeypatch, analysis=AUTH_REQUIRED)
    app = _run(project)
    assert any("This application needs sign-in details" in item.value for item in app.warning)
    assert sum(1 for item in app.markdown if "Missing" in item.value) == 2
    setup = [button for button in app.button if button.label == "Set up"]
    assert len(setup) == 2
    setup[1].click().run()  # the API key requirement
    assert app.session_state["conn_template"] == "API key in a header (API_KEY)"
    assert app.selectbox(key="conn_template").value == "API key in a header (API_KEY)"


def test_saved_connection_turns_the_requirement_into_saved(repo, monkeypatch):
    project, svc = _page(repo, monkeypatch, analysis=AUTH_REQUIRED)
    svc.connections.save(project.id, OWNER, "ui-account", "ui_account", values={"username": "tester", "password": "correct-horse"})
    app = _run(project)
    assert any("Saved" in item.value for item in app.markdown)
    assert [button.label for button in app.button].count("Set up") == 1


def test_continue_records_the_confirmation_for_the_latest_discovery(repo, monkeypatch):
    project, _svc = _page(repo, monkeypatch, analysis=AUTH_REQUIRED)
    app = _run(project)
    [button for button in app.button if button.label == "Continue to scenarios"][0].click().run()
    assert not app.exception, [e.value for e in app.exception]
    confirmed = [row for row in repo.list_audit(project.id) if row["action"] == "connections.confirmed"]
    assert confirmed and confirmed[0]["detail"]["discovery_id"] == repo.latest_discovery(project.id)[0]["id"]
    assert repo.connections_confirmed(project.id)


def test_no_sign_in_needed_is_a_success_message(repo, monkeypatch):
    analysis = {"authentication": {"requires_authentication": False, "summary": "Public pages only.", "requirements": [], "checked_by": "signals"}}
    project, _svc = _page(repo, monkeypatch, analysis=analysis)
    app = _run(project)
    assert any("No sign-in details are needed" in item.value for item in app.success)
    assert any(button.label == "Continue to scenarios" for button in app.button)
