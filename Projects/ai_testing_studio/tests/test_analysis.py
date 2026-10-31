"""Failure analysis, self-healing and defect drafting, using a fake model and real Chromium for DOM checks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ats.ai.agents import FailureAnalysisAgent, ReportAgent, SelfHealingAgent
from ats.analysis import dom
from ats.analysis.classifier import classify
from ats.analysis.defects import DefectBuilder
from ats.analysis.healing import HealingEngine, is_grounded
from ats.analysis.patching import PatchError, patch_locators
from ats.analysis.pipeline import FailureAnalyzer
from ats.analysis.service import AnalysisService
from ats.execution.executor import ExecutionContext, ExecutionService, run_dir
from ats.execution.junit import read_evidence
from ats.models import Selector
from tests.fakes import FakeClient

TC = "TC_LOG_001"
KEY = "login.sign_in_button"
OLD_PAGE = Path(__file__).parent / "fixtures" / "site" / "login.html"
CHANGED_DOM = OLD_PAGE.read_text(encoding="utf-8").replace('<button type="submit" data-testid="login-submit">Sign in</button>', '<button type="submit" id="go">Log in</button>')
LOCATORS = {
    KEY: {"page": "login", "intent": "submit the login form", "role": "button", "name": "Sign in", "preferred": {"kind": "role", "value": "button", "name": "Sign in", "exact": True}, "alternatives": []},
    "login.email_textbox": {"page": "login", "intent": "", "role": "textbox", "name": "Email address", "preferred": {"kind": "label", "value": "Email address"}, "alternatives": []},
}
TEST_FILE = f"tests/test_login.py\n"


def classification(category: str = "LOCATOR DRIFT", confidence: float = 0.85, fixable: bool = True) -> dict:
    return {"category": category, "confidence": confidence, "summary": "The Sign in button was renamed.", "reasoning": "Locator no longer matches.", "evidence_used": ["dom", "error"], "automation_fixable": fixable, "recommended_action": "Update locator"}


def healing_reply(name: str = "Log in", confidence: float = 0.9, behavior_changed: bool = False) -> dict:
    if behavior_changed:
        return {"element_key": KEY, "behavior_changed": True, "explanation": "The page now shows a different flow.", "proposals": []}
    return {"element_key": KEY, "intended_action": "click", "behavior_changed": False, "explanation": "Button label changed.", "proposals": [{"selector": {"kind": "role", "value": "button", "name": name}, "confidence": confidence, "reason": "Same position and purpose."}]}


class StubExecutor(ExecutionService):
    """Real bookkeeping, but the 'run' is replaced: reruns report whatever ``rerun_status`` says."""

    def __init__(self, repo, rerun_status: str = "PASS") -> None:
        super().__init__(repo)
        self.rerun_status = rerun_status
        self.reruns: list[dict[str, str]] = []

    def execute(self, execution_id, project, files, secrets, framework, browser, bundle_id=None, test_case_ids=None, mode=None, cancel=None):
        self.reruns.append({"id": execution_id, "locators": files.get("config/locators.json", "")})
        rows = [{"test_case_id": t, "test_name": t, "status": self.rerun_status, "duration": 1.0, "message": "", "details": {}, "evidence": {}} for t in test_case_ids or []]
        self.repo.replace_results(execution_id, rows)
        self.repo.update_execution(execution_id, status="completed", phase="Results collected")
        return ExecutionContext(execution_id, project, run_dir(project.id, execution_id) / "workspace", files, framework, browser, secrets, bundle_id, "local", list(test_case_ids or []))


def make_failed_execution(repo, executor, *, error: str, action: str = "click", element: str = KEY, dom_html: str = CHANGED_DOM, console: list[str] | None = None):
    project = repo.create_project("owner", name="Shop", url="http://127.0.0.1:9", base_url="http://127.0.0.1:9")
    execution_id = executor.create(project, "playwright_python", "chromium", source="bundle")
    workdir = run_dir(project.id, execution_id) / "workspace"
    evidence_dir = workdir / "reports" / "evidence" / TC
    evidence_dir.mkdir(parents=True)
    (evidence_dir / "steps.json").write_text(json.dumps([{"index": 1, "description": "Open the login page", "action": "goto", "element": "", "status": "passed"}, {"index": 2, "description": "Click Sign in", "action": action, "element": element, "status": "failed"}]), encoding="utf-8")
    (evidence_dir / "failure.json").write_text(json.dumps({"test_case_id": TC, "step": "Click Sign in", "action": action, "element": element, "error": error, "url": "http://127.0.0.1:9/login.html", "title": "Acme Shop", "console": console or []}), encoding="utf-8")
    if dom_html:
        (evidence_dir / "dom.html").write_text(dom_html, encoding="utf-8")
    files = {"config/locators.json": json.dumps(LOCATORS, indent=2), "tests/test_login.py": f"def test_login():\n    # {TC}\n    pass\n"}
    for rel, content in files.items():
        (workdir / rel).parent.mkdir(parents=True, exist_ok=True)
        (workdir / rel).write_text(content, encoding="utf-8")
    repo.replace_results(execution_id, [{"test_case_id": TC, "test_name": "test_login", "status": "FAIL", "duration": 2.0, "message": error, "details": {}, "evidence": read_evidence(workdir, TC)}])
    repo.update_execution(execution_id, status="completed", totals={"total": 1, "failed": 1})
    ctx = ExecutionContext(execution_id, project, workdir, files, "playwright_python", "chromium", {}, None, "local", [TC])
    return project, ctx


def build_service(repo, analysis: dict, healing: dict | None = None, rerun_status: str = "PASS", defect: dict | None = None):
    handlers = {"Failure Analysis Agent": analysis, "Self-Healing Agent": healing or healing_reply(), "(defect mode)": defect or {"title": "Login button missing", "description": "d", "severity": "High", "priority": "High", "actual_result": "no button"}}
    client = FakeClient(handlers)
    executor = StubExecutor(repo, rerun_status)
    analyzer = FailureAnalyzer(repo, FailureAnalysisAgent(client, repo))
    healer = HealingEngine(repo, executor, analyzer, SelfHealingAgent(client, repo))
    verified: list[list[int]] = []
    service = AnalysisService(repo, executor, analyzer, healer, DefectBuilder(repo, ReportAgent(client, repo)), on_verified=lambda _ctx, ids: verified.append(ids))
    return service, executor, client, verified


# ------------------------------------------------------------------------------------------ pure logic
def test_classifier_rules():
    assert classify("Environment variable LOGIN_PASSWORD is not set", "fill", "x", None).category == "TEST DATA ISSUE"
    assert classify("net::ERR_CONNECTION_REFUSED at http://x", "goto", "", None).category == "ENVIRONMENT ISSUE"
    assert classify("Timeout 30000ms exceeded waiting for get_by_role('button')", "click", "k", False).category == "LOCATOR DRIFT"
    assert classify("Timeout waiting for locator", "click", "k", True).category == "TIMEOUT/SYNCHRONIZATION"
    assert classify("Actual value 'a' unexpected value 'b'", "expect_text", "k", True).category == "ASSERTION FAILURE"
    assert classify("boom", "click", "k", True).category == "UNKNOWN"


def test_grounding_blocks_invented_text():
    assert is_grounded(Selector(kind="role", value="button", name="Log in"), CHANGED_DOM)
    assert not is_grounded(Selector(kind="role", value="button", name="Totally new"), CHANGED_DOM)
    assert not is_grounded(Selector(kind="id", value="does-not-exist"), CHANGED_DOM)
    assert is_grounded(Selector(kind="id", value="go"), CHANGED_DOM)


def test_patch_locators_keeps_old_as_alternative_and_resolves_selenium():
    files = {"config/locators.json": json.dumps({KEY: {**LOCATORS[KEY], "resolved": {"by": "xpath", "value": "old"}}})}
    patched, old, new = patch_locators(files, KEY, Selector(kind="id", value="go"), selenium=True)
    assert new["preferred"] == {"kind": "id", "value": "go", "exact": False}
    assert new["alternatives"][0]["name"] == "Sign in"
    assert new["resolved"]["value"] != "old"
    assert old["preferred"]["name"] == "Sign in"
    assert json.loads(patched["config/locators.json"])[KEY] == new
    with pytest.raises(PatchError):
        patch_locators(files, "missing.key", Selector(kind="id", value="go"), selenium=False)
    with pytest.raises(PatchError):
        patch_locators(files, KEY, Selector.model_validate(LOCATORS[KEY]["preferred"]), selenium=False)


# ------------------------------------------------------------------------------------------ browser backed
def test_dom_check_finds_missing_locator_and_a_candidate(browser_ready):
    if not browser_ready:
        pytest.skip("Chromium is not available")
    old = Selector.model_validate(LOCATORS[KEY]["preferred"])
    results, current = dom.analyze_failure_dom(CHANGED_DOM, "http://x/login.html", [old])
    assert results[0]["count"] == 0
    from ats.models import LocatorSpec

    spec = LocatorSpec(element_key=KEY, preferred=old, role="button", name="Sign in", intent="submit the login form", tag="button")
    ranked = dom.rank_candidates(spec, current)
    assert ranked and ranked[0]["name"] == "Log in" and ranked[0]["role"] == "button"


def test_auto_policy_heals_and_marks_healed_not_pass(repo, browser_ready):
    if not browser_ready:
        pytest.skip("Chromium is not available")
    service, executor, client, verified = build_service(repo, classification())
    service.policies = {}
    project, ctx = make_failed_execution(repo, executor, error="Timeout 30000ms exceeded waiting for get_by_role('button', name='Sign in', exact=True)")
    service.policies[project.id] = "auto_pr"
    service.post_run(ctx)

    row = repo.list_results(ctx.execution_id)[0]
    assert row["status"] == "HEALED"
    assert row["analysis"]["category"] == "LOCATOR DRIFT"
    assert row["analysis"]["locator_check"]["preferred_count"] == 0
    healing = repo.list_healings(project.id)[0]
    assert healing["status"] == "verified" and healing["outcome"] == "rerun_passed"
    assert healing["new_locator"]["name"] == "Log in" and healing["old_locator"]["name"] == "Sign in"
    assert "Log in" in healing["proposed_code"]
    assert json.loads(executor.reruns[0]["locators"])[KEY]["preferred"]["name"] == "Log in"  # the rerun used the patched file only
    execution = repo.get_execution(ctx.execution_id)
    assert execution["status"] == "completed" and execution["totals"]["healed"] == 1 and execution["totals"]["passed"] == 0
    assert verified == [[healing["id"]]]
    assert repo.list_defects(project.id) == []


def test_manual_policy_waits_for_approval_then_reruns(repo, browser_ready):
    if not browser_ready:
        pytest.skip("Chromium is not available")
    service, executor, _client, verified = build_service(repo, classification())
    project, ctx = make_failed_execution(repo, executor, error="Timeout waiting for get_by_role('button', name='Sign in')")
    service.post_run(ctx)
    row = repo.list_results(ctx.execution_id)[0]
    assert row["status"] == "FAIL" and row["analysis"]["healing"]["status"] == "proposed"
    assert executor.reruns == [] and verified == []
    healing = repo.list_healings(project.id)[0]
    assert healing["status"] == "proposed"

    service.healer.approve(healing["id"], project, {}, background=False)
    assert repo.list_results(ctx.execution_id)[0]["status"] == "HEALED"
    assert repo.get_healing(healing["id"])["status"] == "verified"
    diff = service.healer.apply(healing["id"], project)
    assert "Log in" in diff and repo.get_healing(healing["id"])["status"] == "applied"


def test_failed_rerun_keeps_failure_visible(repo, browser_ready):
    if not browser_ready:
        pytest.skip("Chromium is not available")
    service, executor, _client, _ = build_service(repo, classification(), rerun_status="FAIL")
    project, ctx = make_failed_execution(repo, executor, error="Timeout waiting for get_by_role('button', name='Sign in')")
    service.policies[project.id] = "auto_pr"
    service.post_run(ctx)
    assert repo.list_results(ctx.execution_id)[0]["status"] == "FAIL"
    assert repo.list_healings(project.id)[0]["status"] == "failed"


def test_ungrounded_or_low_confidence_proposal_is_rejected(repo, browser_ready):
    if not browser_ready:
        pytest.skip("Chromium is not available")
    for reply in (healing_reply(name="Invented label"), healing_reply(confidence=0.2)):
        service, executor, _client, _ = build_service(repo, classification(), healing=reply)
        project, ctx = make_failed_execution(repo, executor, error="Timeout waiting for get_by_role('button', name='Sign in')")
        service.policies[project.id] = "auto_pr"
        service.post_run(ctx)
        assert repo.list_results(ctx.execution_id)[0]["status"] == "FAIL"
        assert repo.list_healings(project.id) == [] and executor.reruns == []


def test_behavior_change_is_reported_as_defect_not_healed(repo, browser_ready):
    if not browser_ready:
        pytest.skip("Chromium is not available")
    service, executor, _client, _ = build_service(repo, classification(), healing=healing_reply(behavior_changed=True))
    project, ctx = make_failed_execution(repo, executor, error="Timeout waiting for get_by_role('button', name='Sign in')")
    service.policies[project.id] = "auto_pr"
    service.post_run(ctx)
    row = repo.list_results(ctx.execution_id)[0]
    assert row["status"] == "FAIL" and row["analysis"]["category"] == "LIKELY APPLICATION DEFECT"
    defect = repo.list_defects(project.id)[0]["data"]
    assert defect["steps_to_reproduce"] == ["Open the login page", "Click Sign in"] and defect["test_case_id"] == TC


def test_locator_that_still_matches_is_not_drift_and_never_healed(repo, browser_ready):
    if not browser_ready:
        pytest.skip("Chromium is not available")
    original = OLD_PAGE.read_text(encoding="utf-8")
    service, executor, _client, _ = build_service(repo, classification("LOCATOR DRIFT"))
    project, ctx = make_failed_execution(repo, executor, error="Element is not enabled", dom_html=original)
    service.policies[project.id] = "auto_pr"
    service.post_run(ctx)
    row = repo.list_results(ctx.execution_id)[0]
    assert row["analysis"]["category"] != "LOCATOR DRIFT"
    assert repo.list_healings(project.id) == []
    assert all(json.loads(r["locators"]) == LOCATORS for r in executor.reruns)  # at most an unchanged re-check, never a patched run


def test_assertion_failure_is_never_healed(repo, browser_ready):
    if not browser_ready:
        pytest.skip("Chromium is not available")
    service, executor, _client, _ = build_service(repo, classification("ASSERTION FAILURE", 0.9, fixable=False))
    project, ctx = make_failed_execution(repo, executor, action="expect_text", error="Actual value 'Welcome' unexpected value 'Hello'", dom_html=OLD_PAGE.read_text(encoding="utf-8"))
    service.post_run(ctx)
    assert repo.list_healings(project.id) == [] and executor.reruns == []
    assert repo.list_defects(project.id)[0]["data"]["category"] == "ASSERTION FAILURE"


def test_environment_failure_is_deterministic_even_if_model_disagrees(repo):
    service, executor, _client, _ = build_service(repo, classification("LIKELY APPLICATION DEFECT", 0.9, fixable=False))
    project, ctx = make_failed_execution(repo, executor, action="goto", element="", error="net::ERR_CONNECTION_REFUSED at http://127.0.0.1:9/", dom_html="")
    service.post_run(ctx)
    row = repo.list_results(ctx.execution_id)[0]
    assert row["analysis"]["category"] == "ENVIRONMENT ISSUE"
    assert repo.list_defects(project.id) == []


def test_flaky_failure_that_passes_on_recheck_is_inconclusive(repo):
    service, executor, _client, _ = build_service(repo, classification("TIMEOUT/SYNCHRONIZATION", 0.5, fixable=False), rerun_status="PASS")
    project, ctx = make_failed_execution(repo, executor, error="Timeout 5000ms exceeded.", element="", action="click", dom_html="")
    service.post_run(ctx)
    row = repo.list_results(ctx.execution_id)[0]
    assert row["status"] == "INCONCLUSIVE" and "re-check" in row["message"]
    assert repo.get_execution(ctx.execution_id)["totals"]["inconclusive"] == 1
    assert [e["kind"] for e in repo.list_executions(project.id)].count("recheck") == 1


def test_model_outage_falls_back_to_rules(repo):
    class Down(FakeClient):
        def complete(self, *_a, **_k):
            from ats.errors import ModelError

            raise ModelError("down")

    executor = StubExecutor(repo)
    analyzer = FailureAnalyzer(repo, FailureAnalysisAgent(Down(), repo))
    healer = HealingEngine(repo, executor, analyzer, SelfHealingAgent(Down(), repo))
    service = AnalysisService(repo, executor, analyzer, healer, DefectBuilder(repo, ReportAgent(Down(), repo)))
    project, ctx = make_failed_execution(repo, executor, error="net::ERR_NAME_NOT_RESOLVED", action="goto", element="", dom_html="")
    service.post_run(ctx)
    row = repo.list_results(ctx.execution_id)[0]
    assert row["analysis"]["category"] == "ENVIRONMENT ISSUE" and row["analysis"]["ai_used"] is False
    assert repo.get_execution(ctx.execution_id)["status"] == "completed"
