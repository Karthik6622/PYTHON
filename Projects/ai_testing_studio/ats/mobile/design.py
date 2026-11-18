"""Helpers for mobile test design: build the model input from the analysed screens, and validate what comes back.

The model may only use screens and elements that analysis found. Credentials are never hard-coded: a valid sign-in uses ``{{env:...}}``
placeholders (negative tests may type deliberately invalid fictitious values). Anything else is dropped or weakened, never guessed.
"""

from __future__ import annotations

import re
from typing import Any

from ats.generation.common import module_code, norm_title, valid_id
from ats.mobile.models import (
    ELEMENT_ACTIONS,
    ORIENTATIONS,
    SWIPE_DIRECTIONS,
    VALUE_ACTIONS,
    MobileAnalysis,
    MobileConfig,
    MobileElement,
    MobileScript,
    MobileStep,
)
from ats.models import COVERAGE_GUIDE, TEST_TYPES, Scenario, TestCase
from ats.repository import Project
from ats.security import mask

USERNAME_ENV = "MOBILE_TEST_USERNAME"
PASSWORD_ENV = "MOBILE_TEST_PASSWORD"
ENV_RE = re.compile(r"\{\{env:[A-Za-z_][A-Za-z0-9_]*\}\}")
NEGATIVE_TYPES = {"Negative", "Validation", "Security", "Boundary", "Error Handling"}
NEGATIVE_WORDS = re.compile(r"(?i)\b(invalid|incorrect|wrong|empty|blank|bad|unknown|unregistered|expired|too (?:short|long)|missing|malformed|illegal|special characters?)\b")
SECRET_KEY = re.compile(r"(?i)pass(?:word|wd)?|secret|token|\bpin\b|otp")
USER_KEY = re.compile(r"(?i)user(?:name)?|e-?mail|login|phone|mobile number")
MAX_SCREENS_IN_PROMPT = 14
MAX_ELEMENTS_PER_SCREEN = 40
MAX_PLAN_ELEMENTS = 220


def next_mobile_id(prefix: str, module: str, taken: set[str]) -> str:
    """``SC_M<MODULE>_001`` / ``TC_M<MODULE>_001``: the leading M keeps mobile ids apart from web (and API) ids; one id space per project."""
    code = ("M" + module_code(module))[:6]
    number = 1
    while f"{prefix}_{code}_{number:03d}" in taken:
        number += 1
    value = f"{prefix}_{code}_{number:03d}"
    taken.add(value)
    return value


def is_negative(case: TestCase) -> bool:
    return case.test_type in NEGATIVE_TYPES or bool(NEGATIVE_WORDS.search(f"{case.title} {case.description}"))


# ----------------------------------------------------------------------------------------
# model input
# ----------------------------------------------------------------------------------------
def application(project: Project, config: MobileConfig, analysis: MobileAnalysis) -> dict[str, Any]:
    return {
        "name": project.name, "platform": config.platform, "package": analysis.package or config.package, "launch_activity": analysis.activity or config.activity,
        "environment": project.environment, "description": project.description, "notes": project.test_data_notes,
        "test_account": {"username": f"{{{{env:{USERNAME_ENV}}}}}", "password": f"{{{{env:{PASSWORD_ENV}}}}}"},
    }  # fmt: skip


def element_digest(element: MobileElement) -> dict[str, Any]:
    data: dict[str, Any] = {"key": element.key, "role": element.role, "name": element.name}
    if element.text and element.text != element.name:
        data["text"] = element.text
    if element.accessibility_id and element.accessibility_id != element.name:
        data["accessibility_id"] = element.accessibility_id
    if element.resource_id:
        data["resource_id"] = element.resource_id.split("/", 1)[-1]
    if element.password:
        data["password"] = True
    if not element.enabled:
        data["enabled"] = False
    return data


def screens_digest(analysis: MobileAnalysis, wanted: set[str] | None = None, max_screens: int = MAX_SCREENS_IN_PROMPT) -> list[dict[str, Any]]:
    """The analysed screens for a prompt: wanted screens first, long element lists trimmed."""
    ordered = sorted(analysis.screens, key=lambda s: (s.screen_key not in (wanted or set()), analysis.screens.index(s)))
    return [
        {
            "screen_key": s.screen_key, "title": s.title, "activity": s.activity, "reached_by": s.reached_by,
            "elements": [element_digest(e) for e in s.elements[:MAX_ELEMENTS_PER_SCREEN]],
        }
        for s in ordered[:max_screens]
    ]  # fmt: skip


def allowed_types(project: Project) -> list[str]:
    return project.custom_categories if project.coverage == "CUSTOM" and project.custom_categories else TEST_TYPES


def scenario_payload(project: Project, config: MobileConfig, analysis: MobileAnalysis, requirements: str, allowed: list[str]) -> dict[str, Any]:
    return {
        "application": application(project, config, analysis), "coverage": project.coverage, "coverage_guide": COVERAGE_GUIDE.get(project.coverage, ""),
        "allowed_test_types": allowed, "screens": screens_digest(analysis), "user_requirements": requirements or project.test_data_notes,
    }  # fmt: skip


def testcase_payload(project: Project, config: MobileConfig, analysis: MobileAnalysis, scenarios: list[Scenario], requirements: str, taken: set[str]) -> dict[str, Any]:
    return {
        "scenarios": [s.model_dump() for s in scenarios], "screens": screens_digest(analysis, {s.page for s in scenarios}),
        "application": application(project, config, analysis), "user_requirements": requirements or project.test_data_notes, "existing_test_case_ids": sorted(taken),
    }  # fmt: skip


def script_payload(project: Project, config: MobileConfig, analysis: MobileAnalysis, batch: list[TestCase], actions: list[str]) -> dict[str, Any]:
    wanted = {c.related_page for c in batch}
    ordered = sorted(analysis.screens, key=lambda s: (s.screen_key not in wanted, analysis.screens.index(s)))
    elements = [
        {"key": e.key, "screen": s.screen_key, "role": e.role, "name": e.name, "text": e.text, "password": e.password}
        for s in ordered
        for e in s.elements
    ][:MAX_PLAN_ELEMENTS]  # fmt: skip
    return {
        "application": {"package": analysis.package or config.package, "platform": config.platform},
        "test_cases": [c.model_dump(include={"test_case_id", "title", "steps", "expected_result", "preconditions", "test_data", "test_type", "related_page"}) for c in batch],
        "elements": elements, "allowed_actions": actions,
    }  # fmt: skip


# ----------------------------------------------------------------------------------------
# validating what the model returned
# ----------------------------------------------------------------------------------------
def clean_scenarios(raw: list[Scenario], screens: set[str], taken: set[str], allowed: list[str] | None, already: list[Scenario]) -> list[Scenario]:
    seen = {(norm_title(s.module), norm_title(s.title)) for s in already}
    out: list[Scenario] = []
    for item in raw:
        key = (norm_title(item.module), norm_title(item.title))
        if not item.title or key in seen or (allowed is not None and item.test_type not in allowed):
            continue
        seen.add(key)
        sid = item.scenario_id if valid_id(item.scenario_id, "SC", taken) else next_mobile_id("SC", item.module, taken)
        taken.add(sid)
        page = item.page if item.page in screens else next((k for k in screens if item.page and (k in item.page or item.page.lower().replace(" ", "_") == k)), item.page)
        out.append(item.model_copy(update={"scenario_id": sid, "status": "draft", "source": "ai", "page": page, "layer": "mobile"}))
    return out


def guard_credentials(data: dict[str, str], negative: bool) -> dict[str, str]:
    """Test data of a positive test never carries a typed credential: it becomes an ``{{env:...}}`` placeholder."""
    cleaned: dict[str, str] = {}
    for name, value in data.items():
        value = mask(value)
        if not negative and value and not ENV_RE.search(value):
            if SECRET_KEY.search(name):
                value = f"{{{{env:{PASSWORD_ENV}}}}}"
            elif USER_KEY.search(name):
                value = f"{{{{env:{USERNAME_ENV}}}}}"
        cleaned[name] = value
    return cleaned


def clean_testcases(raw: list[TestCase], scenario_ids: set[str], taken: set[str], already: list[TestCase]) -> list[TestCase]:
    seen = {(t.scenario_id, norm_title(t.title)) for t in already}
    out: list[TestCase] = []
    for item in raw:
        if item.scenario_id not in scenario_ids or not item.title or not item.steps:
            continue
        key = (item.scenario_id, norm_title(item.title))
        if key in seen:
            continue
        seen.add(key)
        tid = item.test_case_id if valid_id(item.test_case_id, "TC", taken) else next_mobile_id("TC", item.module, taken)
        taken.add(tid)
        out.append(item.model_copy(update={"test_case_id": tid, "status": "draft", "source": "ai", "layer": "mobile", "api": None, "test_data": guard_credentials(item.test_data, is_negative(item))}))
    return out


# ----------------------------------------------------------------------------------------
# automation scripts
# ----------------------------------------------------------------------------------------
def build_corpus(case: TestCase, analysis: MobileAnalysis) -> str:
    parts = [case.title, case.description, case.expected_result, *case.steps, *case.preconditions, *case.test_data.values()]
    for screen in analysis.screens:
        parts += [screen.title]
        for element in screen.elements:
            parts += [element.name, element.text, element.accessibility_id]
    return "\n".join(p for p in parts if p).lower()


def _screen_has_password(elements: dict[str, MobileElement], key: str) -> bool:
    screen = key.split(".", 1)[0]
    return any(e.password for e in elements.values() if e.screen == screen)


def _looks_like_username(element: MobileElement) -> bool:
    return element.role == "textbox" and not element.password and bool(USER_KEY.search(f"{element.name} {element.resource_id}"))


def validate_script(script: MobileScript, case: TestCase, elements: dict[str, MobileElement], corpus: str) -> MobileScript | None:
    """A safe script, or ``None`` when nothing usable remains. Only trims, weakens or swaps typed credentials for placeholders."""
    notes: list[str] = [script.notes] if script.notes else []
    negative = is_negative(case)
    steps: list[MobileStep] = []
    for index, step in enumerate(script.steps, 1):
        problem = ""
        value = (step.value or "").strip()
        if step.action in ELEMENT_ACTIONS and (not step.element or step.element not in elements):
            problem = f"unknown element '{step.element}'"
        elif step.action in VALUE_ACTIONS and step.action != "type" and not value:
            problem = "missing value"
        elif step.action == "swipe" and value.lower() not in SWIPE_DIRECTIONS:
            problem = f"swipe direction '{value}' is not up, down, left or right"
        elif step.action == "rotate" and value.lower() not in ORIENTATIONS:
            problem = f"orientation '{value}' is not portrait or landscape"
        elif step.action == "wait" and not re.fullmatch(r"\d+(\.\d+)?", value):
            problem = "wait needs a number of seconds"
        if problem:
            notes.append(f"Script stopped at step {index}: {problem}.")
            break
        step = step.model_copy()
        if step.action not in ELEMENT_ACTIONS:
            step.element = None
        if step.action in {"swipe", "rotate"}:
            step.value = value.lower()
        if step.action == "wait":
            step.value = str(min(float(value), 10.0)).rstrip("0").rstrip(".")
        if step.action == "type" and step.element:
            element = elements[step.element]
            typed = step.value or ""
            if not ENV_RE.search(typed) and not negative and typed:
                if element.password:
                    step.value = f"{{{{env:{PASSWORD_ENV}}}}}"
                    notes.append(f"Step {index}: the typed password was replaced by the placeholder {{{{env:{PASSWORD_ENV}}}}}.")
                elif _looks_like_username(element) and _screen_has_password(elements, step.element):
                    step.value = f"{{{{env:{USERNAME_ENV}}}}}"
                    notes.append(f"Step {index}: the typed user name was replaced by the placeholder {{{{env:{USERNAME_ENV}}}}}.")
        if step.action == "expect_text" and not ENV_RE.search(value) and value.lower() not in corpus:
            notes.append(f"Step {index}: expected text {value!r} was not found in the test case or the analysed screens; checks visibility only.")
            step = step.model_copy(update={"action": "expect_visible", "value": None})
        steps.append(step)
    if not steps:
        return None
    return MobileScript(test_case_id=case.test_case_id, title=script.title or case.title, notes=" ".join(notes), steps=steps)
