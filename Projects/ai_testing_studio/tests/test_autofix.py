"""Automatic repair: safety checks on proposed repairs, fallback-selector promotion and locator ranking from live checks."""

from __future__ import annotations

import json

import pytest

from ats.analysis.autofix import AutoFixer, RepairRejected, apply_repair, test_function as find_test_function
from ats.analysis.healing import HealingEngine
from ats.analysis.pipeline import FailureAnalyzer
from ats.execution.executor import ExecutionContext, ExecutionService, run_dir
from ats.locators.builder import build_selectors
from ats.models import LocatorUpdate, RepairEdit, RepairResult, Selector
from tests.test_pipeline import TC, prepared, wait_for  # noqa: F401 - fixtures and helpers shared with the pipeline tests

TEST_FILE = '''import pytest
from playwright.sync_api import expect


@pytest.mark.tc('TC_LOG_001')
def test_tc_log_001_login(app):
    with app.step("Open", action="open_view", element=""):
        app.open_view("login")
    with app.step("Visible", action="expect_visible", element="login.go"):
        expect(app.pages.login.go).to_be_visible()


@pytest.mark.tc('TC_LOG_002')
def test_tc_log_002_other(app):
    pass
'''
LOGIN = "tests/web/test_login.py"
FILES = {LOGIN: TEST_FILE, "config/locators.json": json.dumps({"login.go": {"preferred": {"kind": "role", "value": "button", "name": "Go"}, "alternatives": []}})}


def edit(**fields) -> RepairResult:
    return RepairResult(verdict="fixed", explanation="x", **fields)


def test_a_valid_edit_is_applied_to_exactly_one_place():
    result = edit(edits=[RepairEdit(path=LOGIN, find='app.open_view("login")', replace='app.open_view("login")\n        app.settle()')])
    fixed = apply_repair(FILES, result)
    assert "app.settle()" in fixed[LOGIN] and fixed["config/locators.json"] == FILES["config/locators.json"]


@pytest.mark.parametrize(
    "bad",
    [
        RepairEdit(path="utils/app.py", find="x", replace="y"),  # not a file the repair may touch
        RepairEdit(path=LOGIN, find="not in the file", replace="y"),
        RepairEdit(path=LOGIN, find="expect(app.pages.login.go).to_be_visible()", replace="pass"),  # drops an assertion
        RepairEdit(path=LOGIN, find="@pytest.mark.tc('TC_LOG_001')", replace=""),  # drops the test id marker
        RepairEdit(path=LOGIN, find='app.open_view("login")', replace='password = "hunter2hunter2"'),
        RepairEdit(path=LOGIN, find='app.open_view("login")', replace="app.open_view("),  # breaks the syntax
    ],
)
def test_unsafe_repairs_are_refused(bad):
    with pytest.raises(RepairRejected):
        apply_repair(FILES, edit(edits=[bad]))


def test_locator_updates_change_only_the_named_element():
    update = LocatorUpdate(element_key="login.go", preferred=Selector(kind="testid", value="go"), alternatives=[Selector(kind="role", value="button", name="Go")])
    fixed = apply_repair(FILES, edit(locator_updates=[update]))
    entry = json.loads(fixed["config/locators.json"])["login.go"]
    assert entry["preferred"] == {"kind": "testid", "value": "go", "exact": False} and entry["alternatives"][0]["name"] == "Go"
    with pytest.raises(RepairRejected):
        apply_repair(FILES, edit(locator_updates=[LocatorUpdate(element_key="unknown", preferred=Selector(kind="css", value="#x"))]))
    with pytest.raises(RepairRejected):
        apply_repair(FILES, edit())  # nothing to apply


def test_the_failing_test_function_is_located_by_its_id():
    path, source = find_test_function(FILES, "TC_LOG_001")
    assert path == LOGIN and "test_tc_log_001_login" in source and "TC_LOG_002" not in source
    assert find_test_function({**FILES, "tests/api/test_x.py": "@pytest.mark.tc('TC_API_001')\ndef test_x(api): ...\n"}, "TC_API_001")[0] == "tests/api/test_x.py"
    assert find_test_function(FILES, "TC_NOPE_001") == ("", "")


def test_live_selector_checks_decide_which_selector_comes_first():
    element = {
        "role": "button", "name": "Save", "visible": True, "css": "main > button:nth-of-type(2)", "xpath": "//button[2]", "counts": {},
        "checks": [
            {"kind": "role", "value": "button", "name": "Save", "exact": True, "count": 3},  # ambiguous on the live page
            {"kind": "css", "value": "main > button:nth-of-type(2)", "count": 1},
        ],
    }
    selectors, score = build_selectors(element)
    assert selectors[0].kind == "css" and selectors[-1].kind == "role"  # unique first, ambiguous last
    unique = {**element, "checks": [{"kind": "role", "value": "button", "name": "Save", "exact": True, "count": 1}]}
    assert build_selectors(unique)[0][0].kind == "role"
    ambiguous = {**element, "css": "", "xpath": "", "checks": [{"kind": "role", "value": "button", "name": "Save", "exact": True, "count": 3}]}
    assert build_selectors(ambiguous)[1] < build_selectors(unique)[1]  # an element nothing identifies uniquely is flagged as fragile


def test_an_alternative_selector_rescues_the_run_and_is_then_promoted(prepared, repo):  # noqa: F811
    project, service = prepared
    bundle_id = service.generate(project, "playwright_python", "chromium")
    files = service.store.read_all(project.id, bundle_id)
    locators = json.loads(files["config/locators.json"])
    key = next(k for k, v in locators.items() if v["role"] == "button" and "sign in" in v["name"].lower())
    good = locators[key]["preferred"]
    locators[key]["alternatives"] = [good, *locators[key]["alternatives"]]
    locators[key]["preferred"] = {"kind": "css", "value": "#this-id-does-not-exist"}  # the preferred selector went stale
    files["config/locators.json"] = json.dumps(locators, indent=2)

    executor = ExecutionService(repo)
    secrets = {"TEST_APP_USERNAME": "user@example.com", "TEST_APP_PASSWORD": "pw-for-test"}
    execution_id = executor.start(project, files, secrets=secrets, framework="playwright_python", browser="chromium", bundle_id=bundle_id, analyze=False)
    execution = wait_for(repo, execution_id)
    result = next(r for r in repo.list_results(execution_id) if r["test_case_id"] == TC)
    assert execution["status"] == "completed" and result["status"] == "PASS", result["message"]  # found through the alternative
    assert result["evidence"]["fallbacks"][key]["selector"]["value"] == good["value"]

    analyzer = FailureAnalyzer(repo)
    fixer = AutoFixer(repo, executor, analyzer, HealingEngine(repo, executor, analyzer, store=service.store), service.store)
    ctx = ExecutionContext(execution_id, project, run_dir(project.id, execution_id) / "workspace", files, "playwright_python", "chromium", secrets, bundle_id, "local")
    summary = {"promoted": []}
    promoted = fixer._promote(ctx, files, summary)
    assert summary["promoted"] == [key]
    assert json.loads(promoted["config/locators.json"])[key]["preferred"]["value"] == good["value"]
    healing = repo.list_healings(project.id, execution_id)[0]
    assert healing["status"] == "applied" and healing["outcome"] == "fallback_promoted"
    fixer._save(ctx, promoted, {"config/locators.json"}, summary, None)
    assert json.loads(service.store.read_file(project.id, bundle_id, "config/locators.json"))[key]["preferred"]["value"] == good["value"]
