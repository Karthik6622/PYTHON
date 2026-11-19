"""Locator strategy, live relocation and the auto-fix loop (every failing test, up to 3 verified attempts, one push)."""

from __future__ import annotations

import json

import pytest

from ats.analysis.autofix import AutoFixer
from ats.analysis.healing import HealingEngine
from ats.analysis.pipeline import FailureAnalyzer
from ats.analysis.relocate import Relocation, Relocator, best_match, score
from ats.execution.executor import ExecutionContext, ExecutionService, run_dir
from ats.locators.builder import build_locators, build_selectors, fingerprint
from ats.models import DiscoveryResult, PageSnapshot, RepairEdit, RepairResult, Selector
from tests.test_pipeline import TC, prepared, wait_for  # noqa: F401 - fixtures shared with the pipeline tests


# ------------------------------------------------------------------------------------------ locator strategy
def test_framework_test_ids_are_never_the_preferred_selector():
    el = {"tag": "button", "role": "button", "name": "Send", "text": "Send", "testid": "stBaseButton-primary", "testid_attr": "data-testid", "visible": True, "counts": {"testid": 1}, "css": "div > button"}
    selectors, _ = build_selectors(el)
    assert selectors[0] == Selector(kind="role", value="button", name="Send", exact=True)
    assert all(s.kind != "testid" for s in selectors)  # the bare widget marker is dropped ...
    assert any(s.kind == "css" and ':has-text("Send")' in s.value for s in selectors)  # ... it only survives narrowed by the label


def test_application_test_ids_still_win():
    el = {"tag": "button", "role": "button", "name": "Send", "testid": "send-message", "testid_attr": "data-testid", "visible": True, "counts": {"testid": 1}}
    assert build_selectors(el)[0][0] == Selector(kind="testid", value="send-message")
    assert build_selectors(el, {"send-message"})[0][0].kind == "role"  # the same id on another view: not an identity


def test_text_blocks_get_a_text_selector_and_button_labels_are_not_separate_elements():
    page = PageSnapshot(url="http://x/", page_key="home", elements=[
        {"tag": "button", "role": "button", "name": "Get started", "text": "Get started", "visible": True, "xpath": "/html/body/div/button", "css": "div > button", "counts": {}},
        {"tag": "div", "role": "", "name": "", "text": "Get started", "testid": "stMarkdownContainer", "visible": True, "xpath": "/html/body/div/button/div", "css": "div > button > div", "counts": {"testid": 3}},
        {"tag": "div", "role": "", "name": "", "text": "Message sent", "testid": "stMarkdownContainer", "visible": True, "xpath": "/html/body/div/div[3]", "css": "#stMain > div:nth-of-type(3)", "counts": {"testid": 3}},
        {"tag": "header", "role": "", "name": "", "text": "", "testid": "stHeader", "visible": True, "xpath": "/html/body/header", "css": "header", "counts": {"testid": 1}},
    ])  # fmt: skip
    specs = {s.element_key: s for s in build_locators(DiscoveryResult(start_url="http://x/", pages=[page]))}
    assert set(specs) == {"home.get_started_button", "home.message_sent_div"}  # no inner label copy, no layout wrapper
    assert specs["home.message_sent_div"].preferred == Selector(kind="text", value="Message sent", exact=True)
    assert fingerprint({"role": "button", "name": "Send", "tag": "button"}) == {"role": "button", "name": "Send", "tag": "button"}


# ------------------------------------------------------------------------------------------ live matching
LIVE = [
    {"tag": "button", "role": "button", "name": "Log in", "text": "Log in"},
    {"tag": "input", "role": "textbox", "name": "Email address", "label": "Email address"},
    {"tag": "button", "role": "button", "name": "Create account", "text": "Create account"},
]


def test_the_failing_element_is_matched_by_what_a_person_sees():
    found, _ = best_match({"role": "textbox", "name": "Email"}, LIVE)
    assert found is LIVE[1]
    assert score({"role": "button", "name": "Sign in"}, LIVE[0]) < 5  # a different label is not guessed
    assert best_match({"role": "button", "name": "Sign in"}, LIVE)[0] is None
    twins = [{"tag": "button", "role": "button", "name": "Save"}, {"tag": "button", "role": "button", "name": "Save"}]
    element, why = best_match({"role": "button", "name": "Save"}, twins)
    assert element is None and "alike" in why


# ------------------------------------------------------------------------------------------ the fix loop
TEST_FILE = "tests/web/test_flow.py"
SOURCE = "import pytest\n\n" + "".join(
    f"\n@pytest.mark.tc('{tc}')\ndef test_{tc.lower()}(app):\n    app.locator('{key}')\n\n"
    for tc, key in (("TC_A", "home.a_button"), ("TC_B", "home.b_button"), ("TC_C", "home.c_button"), ("TC_D", "home.d_button"), ("TC_E", "home.e_button"))
)
LOCATORS = {k: {"page": "home", "role": "button", "name": k, "preferred": {"kind": "css", "value": f"#{k}"}, "alternatives": []} for k in ("home.a_button", "home.b_button", "home.c_button", "home.d_button", "home.e_button")}


def passes(test_id: str, files: dict[str, str]) -> bool:
    locators, source = json.loads(files["config/locators.json"]), files[TEST_FILE]
    return {
        "TC_A": locators["home.a_button"]["preferred"]["value"] == "new-a",  # needs the live relocation
        "TC_B": "# fixed TC_B" in source, "TC_C": "# fixed TC_C" in source,  # two script repairs in the same file
        "TC_D": True,  # intermittent: passes again without any change
        "TC_E": False,  # never fixable
    }[test_id]  # fmt: skip


class RuleExecutor(ExecutionService):
    def __init__(self, repo) -> None:
        super().__init__(repo)
        self.reruns: list[list[str]] = []

    def execute(self, execution_id, project, files, secrets, framework, browser, bundle_id=None, test_case_ids=None, mode=None, cancel=None):
        self.reruns.append(sorted(test_case_ids or []))
        rows = []
        for tc in test_case_ids or []:
            ok = passes(tc, files)
            failure = {"element": f"home.{tc[-1].lower()}_button", "action": "click", "error": "Element not found"}
            rows.append({"test_case_id": tc, "test_name": tc, "status": "PASS" if ok else "FAIL", "duration": 1.0, "message": "" if ok else "Element not found", "details": {}, "evidence": {} if ok else {"failure": failure}})
        self.repo.replace_results(execution_id, rows)
        self.repo.update_execution(execution_id, status="completed")
        return ExecutionContext(execution_id, project, run_dir(project.id, execution_id) / "workspace", files, framework, browser, secrets, bundle_id, "local", list(test_case_ids or []))


class FakeRelocator(Relocator):
    def run(self, files, base_url, keys, secrets, ignore_https_errors=False, progress=None):
        return {k: Relocation(k, "relocated", "home", Selector(kind="testid", value="new-a")) if k == "home.a_button" else Relocation(k, "still_matches", "home") for k in keys}


def test_every_failing_test_is_repaired_verified_and_pushed_once(repo):
    executor = RuleExecutor(repo)
    analyzer = FailureAnalyzer(repo)
    pushed: list[dict[str, str]] = []
    fixer = AutoFixer(repo, executor, analyzer, HealingEngine(repo, executor, analyzer), store=None, push=lambda _p, changed, _m: pushed.append(changed) or {"branch": "b"}, relocator=FakeRelocator())  # type: ignore[arg-type]
    asked: list[str] = []

    def repair(_ctx, finding, files, _previous, _live=None):
        asked.append(finding.test_case_id)
        if finding.test_case_id in {"TC_B", "TC_C"}:
            find = f"def test_{finding.test_case_id.lower()}(app):"
            return RepairResult(verdict="fixed", explanation="wait for the view", edits=[RepairEdit(path=TEST_FILE, find=find, replace=f"{find}\n    # fixed {finding.test_case_id}")])
        return RepairResult(verdict="cannot_determine", explanation="no idea")

    fixer.repair = repair  # type: ignore[method-assign]
    project = repo.create_project("owner", name="Loop", url="http://127.0.0.1:9", base_url="http://127.0.0.1:9")
    files = {TEST_FILE: SOURCE, "config/locators.json": json.dumps(LOCATORS), "config/views.json": json.dumps({"views": {"home": {}}})}
    execution_id = executor.create(project, "playwright_python", "chromium", source="bundle")
    ids = ["TC_A", "TC_B", "TC_C", "TC_D", "TC_E"]
    first = [{"test_case_id": t, "test_name": t, "status": "FAIL", "duration": 1.0, "message": "Element not found", "details": {}, "evidence": {"failure": {"element": f"home.{t[-1].lower()}_button", "action": "click", "error": "Element not found"}}} for t in ids]
    repo.replace_results(execution_id, first)
    ctx = ExecutionContext(execution_id, project, run_dir(project.id, execution_id) / "workspace", files, "playwright_python", "chromium", {}, None, "local", ids)
    findings = [analyzer.build(ctx, row, {}) for row in repo.list_results(execution_id)]

    summary = fixer.run(ctx, findings, 3)

    assert summary["relocated"] == ["TC_A"] and sorted(summary["repaired"]) == ["TC_B", "TC_C"]
    assert summary["intermittent"] == ["TC_D"] and summary["unresolved"] == ["TC_E"] and summary["rounds"] == 3
    assert executor.reruns == [ids]  # one re-run verifies everything; unchanged tests are not re-run in later attempts
    assert "TC_A" not in asked and asked.count("TC_E") == 3  # relocated tests need no model call; the rest get 3 attempts
    status = {r["test_case_id"]: r["status"] for r in repo.list_results(execution_id)}
    assert status == {"TC_A": "HEALED", "TC_B": "HEALED", "TC_C": "HEALED", "TC_D": "INCONCLUSIVE", "TC_E": "FAIL"}
    assert len(pushed) == 1
    assert "# fixed TC_B" in pushed[0][TEST_FILE] and "# fixed TC_C" in pushed[0][TEST_FILE]  # both repairs in one file survive
    assert json.loads(pushed[0]["config/locators.json"])["home.a_button"]["preferred"]["value"] == "new-a"
    assert any(h["outcome"] == "relocated_live" for h in repo.list_healings(project.id, execution_id))


# ------------------------------------------------------------------------------------------ parallel runs
def test_python_projects_run_in_parallel_browsers_when_possible(tmp_path, monkeypatch):
    from ats.execution.runner import RunRequest, run_env

    monkeypatch.setenv("EXECUTION_WORKERS", "3")
    local = RunRequest(framework="playwright_python", browser="chromium", workdir=tmp_path, base_url="http://x", mode="local")
    assert run_env(local, "http://x")["PYTEST_ADDOPTS"] == "-n 3" and run_env(local, "http://x")["WORKERS"] == "3"
    (tmp_path / "requirements.txt").write_text("pytest>=8.0\npytest-playwright>=0.5\n", encoding="utf-8")  # generated before parallel runs
    docker = RunRequest(framework="playwright_python", browser="chromium", workdir=tmp_path, base_url="http://x", mode="docker")
    assert "PYTEST_ADDOPTS" not in run_env(docker, "http://x")
    (tmp_path / "requirements.txt").write_text("pytest>=8.0\npytest-xdist>=3.5\n", encoding="utf-8")
    assert run_env(docker, "http://x")["PYTEST_ADDOPTS"] == "-n 3"
    api = RunRequest(framework="api_python", browser="none", workdir=tmp_path, base_url="http://x", mode="local")
    assert "PYTEST_ADDOPTS" not in run_env(api, "http://x")


# ------------------------------------------------------------------------------------------ real browser
def _break(files: dict[str, str], key: str, keep_fingerprint: bool, name: str | None = None) -> dict[str, str]:
    locators = json.loads(files["config/locators.json"])
    entry = locators[key]
    entry["preferred"], entry["alternatives"] = {"kind": "css", "value": "#gone"}, [{"kind": "xpath", "value": "//nothing"}]
    if not keep_fingerprint:
        entry["fingerprint"] = {"role": entry["role"], "name": name or entry["name"]}
        entry["name"] = name or entry["name"]
    return {**files, "config/locators.json": json.dumps(locators, indent=2)}


def _sign_in_key(files: dict[str, str]) -> str:
    return next(k for k, v in json.loads(files["config/locators.json"]).items() if v["role"] == "button" and "sign in" in v["name"].lower())


SECRETS = {"TEST_APP_USERNAME": "user@example.com", "TEST_APP_PASSWORD": "pw-for-test"}


def test_the_runtime_finds_an_element_by_its_fingerprint_when_every_selector_is_stale(prepared, repo):  # noqa: F811
    project, service = prepared
    bundle_id = service.generate(project, "playwright_python", "chromium")
    files = service.store.read_all(project.id, bundle_id)
    key = _sign_in_key(files)
    assert json.loads(files["config/locators.json"])[key]["fingerprint"]["name"].lower() == "sign in"
    executor = ExecutionService(repo)
    execution_id = executor.start(project, _break(files, key, keep_fingerprint=True), secrets=SECRETS, framework="playwright_python", browser="chromium", bundle_id=bundle_id, analyze=False)
    wait_for(repo, execution_id)
    result = next(r for r in repo.list_results(execution_id) if r["test_case_id"] == TC)
    assert result["status"] == "PASS", result["message"]
    assert result["evidence"]["fallbacks"][key]["fingerprint"] is True


def test_live_relocation_finds_a_renamed_element_on_the_real_page(prepared, repo):  # noqa: F811
    project, service = prepared
    bundle_id = service.generate(project, "playwright_python", "chromium")
    files = service.store.read_all(project.id, bundle_id)
    key = _sign_in_key(files)
    broken = _break(files, key, keep_fingerprint=False, name="Sign inn")  # the label drifted: the runtime cannot match it exactly
    found = Relocator().run(broken, project.app_base_url, [key], SECRETS)[key]
    assert found.status == "relocated", found.detail
    assert found.selector == Selector(kind="testid", value="login-submit")  # the application's own test id, verified unique on the live page
    assert any(s.kind == "role" and (s.name or "").lower() == "sign in" for s in found.alternatives)
