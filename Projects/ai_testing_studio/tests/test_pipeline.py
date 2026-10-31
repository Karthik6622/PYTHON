"""End-to-end without a model or GitHub: real discovery of the fixture site, scripted generation through a fake model,
rendering, and a real local run of the generated project."""

from __future__ import annotations

import time

import pytest

from ats.ai.agents import ScriptGenerationAgent
from ats.automation.bundle_store import BundleStore, UnsafePathError
from ats.discovery.service import DiscoveryService
from ats.execution.executor import ExecutionService
from ats.models import Scenario, TestCase
from ats.automation.script_service import ScriptService
from ats.workflow import compute_workflow
from tests.fakes import FakeClient

TC = "TC_LOG_001"


def plan(_system: str, payload: dict) -> dict:
    """What a well-behaved model returns: element keys copied from the supplied list."""
    by_name = {}
    for element in payload["elements"]:
        if not element["key"].startswith("login."):
            continue
        by_name.setdefault((element["role"], (element["name"] or "").lower()), element["key"])
    email = next(k for (role, name), k in by_name.items() if "email" in name)
    password = next(k for (role, name), k in by_name.items() if name.startswith("password"))
    submit = next(k for (role, name), k in by_name.items() if role == "button" and "sign in" in name)
    return {
        "scripts": [
            {
                "test_case_id": TC, "title": "Login form is usable", "notes": "",
                "steps": [
                    {"action": "goto", "value": "/login.html", "description": "Open the sign in page"},
                    {"action": "fill", "element": email, "value": "{{env:TEST_APP_USERNAME}}", "description": "Enter the email"},
                    {"action": "fill", "element": password, "value": "{{env:TEST_APP_PASSWORD}}", "description": "Enter the password"},
                    {"action": "expect_visible", "element": submit, "description": "Sign in button is shown"},
                ],
            },
            {"test_case_id": "TC_LOG_999", "title": "invented", "notes": "", "steps": [{"action": "click", "element": "does.not_exist", "description": "x"}]},
        ]
    }


@pytest.fixture()
def prepared(repo, site_url, monkeypatch, browser_ready):
    if not browser_ready:
        pytest.skip("Chromium is not installed")
    monkeypatch.setattr(DiscoveryService, "_ai_understanding", lambda *_a, **_k: None)
    monkeypatch.setattr(DiscoveryService, "_enrich", lambda _self, _project, specs, _say, _result: specs)
    project = repo.create_project("owner", name="Fixture shop", url=f"{site_url}/login.html", base_url=site_url)
    DiscoveryService(repo).run(project)
    repo.save_scenarios(project.id, [Scenario(scenario_id="SC_LOG_001", title="Login", module="Login", status="approved")])
    cases = [
        TestCase(test_case_id=TC, scenario_id="SC_LOG_001", module="Login", title="Login form is usable", steps=["Open the sign in page", "Enter the email and password"], expected_result="The Sign in button is shown", status="approved"),
        TestCase(test_case_id="TC_LOG_999", scenario_id="SC_LOG_001", module="Login", title="Unmappable case", steps=["Do something"], status="approved"),
    ]
    repo.save_test_cases(project.id, cases)
    service = ScriptService(repo, BundleStore(), ScriptGenerationAgent(FakeClient({"ROLE: Script Generation Agent.": plan}), repo))
    return project, service


def wait_for(repo, execution_id: str, seconds: int = 240) -> dict:
    end = time.time() + seconds
    while time.time() < end:
        execution = repo.get_execution(execution_id)
        if execution["status"] not in {"queued", "running", "analyzing"}:
            return execution
        time.sleep(1)
    raise AssertionError("execution did not finish")


@pytest.mark.parametrize("framework", ["playwright_python", "selenium_python"])
def test_generated_project_runs_and_passes(prepared, repo, framework):
    project, service = prepared
    bundle_id = service.generate(project, framework, "chromium")
    bundle = repo.get_bundle(bundle_id)
    assert bundle["status"] == "draft"
    trace = {row["test_case_id"]: row for row in bundle["traceability"]}
    assert trace[TC]["automated"] is True and trace[TC]["file"].startswith("tests/")
    assert trace["TC_LOG_999"]["automated"] is False  # invented element keys are rejected, not guessed
    assert bundle["plan"]["skipped"][0]["test_case_id"] == "TC_LOG_999"

    files = service.store.read_all(project.id, bundle_id)
    assert "TEST_APP_PASSWORD" in "".join(files.values()) and "hunter2" not in "".join(files.values())
    assert not any(name.endswith(".env") for name in files)

    service.approve(project.id, bundle_id)
    executor = ExecutionService(repo)
    execution_id = executor.start(
        project, files, secrets={"TEST_APP_USERNAME": "user@example.com", "TEST_APP_PASSWORD": "pw-for-test"},
        framework=framework, browser="chromium", bundle_id=bundle_id, analyze=False,
    )
    execution = wait_for(repo, execution_id)
    results = {r["test_case_id"]: r for r in repo.list_results(execution_id)}
    assert execution["status"] == "completed", execution.get("error")
    assert results[TC]["status"] == "PASS", results[TC]["message"]
    assert results[TC]["evidence"].get("steps")
    assert "pw-for-test" not in executor.log_tail(project.id, execution_id, 500)

    state = compute_workflow(repo, project)
    assert [s.name for s in state.stages][:2] == ["Setup", "Discover"]
    assert next(s for s in state.stages if s.name == "Execute").status == "done"


def test_bundle_store_rejects_traversal_and_hides_secrets(repo, tmp_path):
    store = BundleStore()
    store.write("p1", 1, {"tests/test_a.py": "x = 1\n", ".env": "SECRET=1", "config/state.json": "{}"})
    with pytest.raises(UnsafePathError):
        store.write_file("p1", 1, "../evil.py", "boom")
    with pytest.raises(UnsafePathError):
        store.read_file("p1", 1, "/etc/passwd")
    assert "tests/test_a.py" in store.list_files("p1", 1)
    assert ".env" not in store.list_files("p1", 1)
