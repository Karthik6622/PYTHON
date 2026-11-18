"""Mobile tests: Python + pytest + Appium (Android, UiAutomator2) project renderer. Deterministic: the validated scripts are turned into code, nothing is guessed.

Layout (merged into a multi-channel repository by the GitHub integration)::

    tests/mobile/conftest.py, test_<module>.py     one function per test case, ``with mobile.step(...)`` per step
    screens/mobile/<screen>.py                     screen objects (AppiumBy locators, best first)
    drivers/appium_driver.py, mobile_session.py    session, local Appium server, step recorder and evidence
    mobile_config/android.json                     non-secret capabilities (no APK path, no device id, no credentials)
"""

from __future__ import annotations

import json
from pathlib import Path

from ats.generation.adapters.common import (
    ENV_PLACEHOLDER,
    GITIGNORE,
    FrameworkAdapter,
    RenderContext,
    attr_of,
    case_function_name,
    comment_safe,
    module_slug,
    pascal,
    py_ident,
    py_str,
)
from ats.mobile.models import APPIUM_BY_CONSTANT, MobileElement, MobileScreen, MobileStep

RUNTIME_DIR = Path(__file__).with_name("runtime_mobile")
APPIUM_DRIVER_PY = (RUNTIME_DIR / "appium_driver.py").read_text(encoding="utf-8")
MOBILE_SESSION_PY = (RUNTIME_DIR / "mobile_session.py").read_text(encoding="utf-8")
BASE_SCREEN_PY = (RUNTIME_DIR / "base_screen.py").read_text(encoding="utf-8")
CONFTEST_PY = (RUNTIME_DIR / "conftest.py").read_text(encoding="utf-8")
CONFIG_FILE = "mobile_config/android.json"

PYTEST_INI = """[pytest]
testpaths = tests
pythonpath = .
addopts = -p no:cacheprovider --junitxml=reports/junit.xml
junit_family = xunit2
markers =
    tc(id): the test case identifier this test implements
"""
REQUIREMENTS = "pytest>=8.0\nAppium-Python-Client>=4.0\n"
MOBILE_GITIGNORE = GITIGNORE + "*.apk\n*.aab\nappium*.log\n*.log\nlogcat*.txt\nscreenshots/\n"
ENV_EXAMPLE = """# What to test (one of APP_PATH or APP_PACKAGE is required)
APP_PATH=
APP_PACKAGE=
APP_ACTIVITY=
# Device: leave empty to use the only connected emulator/device
ANDROID_SERIAL=
# Leave empty to let the tests start (and stop) a local Appium server
APPIUM_SERVER_URL=
# Credentials used by tests (never commit real values)
MOBILE_TEST_USERNAME=
MOBILE_TEST_PASSWORD=
"""


def screen_class(screen_key: str) -> str:
    name = pascal(screen_key)
    return name if name.endswith("Screen") else f"{name}Screen"


def screen_var(screen_key: str) -> str:
    ident = py_ident(screen_key, "screen")
    var = ident if ident.endswith("_screen") else f"{ident}_screen"
    return var if var not in {"mobile", "pytest"} else f"{var}_view"


def locator_pairs(element: MobileElement) -> list[tuple[str, str]]:
    return [(APPIUM_BY_CONSTANT[s.strategy], s.value) for s in element.selectors]


def _val(text: str) -> str:
    return f"mobile.val({py_str(text)})" if ENV_PLACEHOLDER.search(text) else py_str(text)


def env_names(files: dict[str, str]) -> list[str]:
    return sorted({m.group(1) for content in files.values() for m in ENV_PLACEHOLDER.finditer(content)})


class AppiumPythonAdapter(FrameworkAdapter):
    key = "appium_python"

    def render(self, ctx: RenderContext) -> dict[str, str]:
        mobile = ctx.mobile
        screens = {s.screen_key: s for s in (MobileScreen.model_validate(x) for x in mobile.get("screens", []))}
        index = {e.key: (s, e) for s in screens.values() for e in s.elements}
        used: dict[str, list[str]] = {}  # screen key -> element keys used by tests, in first-use order
        for item in ctx.cases:
            for step in item.script.steps:
                if getattr(step, "element", None) and step.element in index:
                    keys = used.setdefault(index[step.element][0].screen_key, [])
                    if step.element not in keys:
                        keys.append(step.element)
        files: dict[str, str] = {}
        for module_key, items in ctx.modules().items():
            files[f"tests/mobile/test_{module_slug(module_key)}.py"] = self._tests(module_key, items, index)
        for screen_key, keys in used.items():
            files[f"screens/mobile/{py_ident(screen_key, 'screen')}.py"] = self._screen(screens[screen_key], [index[k][1] for k in keys])
        for package in ("tests", "tests/mobile", "screens", "screens/mobile", "drivers"):
            files[f"{package}/__init__.py"] = ""
        files["tests/mobile/conftest.py"] = CONFTEST_PY
        files["drivers/appium_driver.py"] = APPIUM_DRIVER_PY
        files["drivers/mobile_session.py"] = MOBILE_SESSION_PY
        files["screens/mobile/base_screen.py"] = BASE_SCREEN_PY
        files[CONFIG_FILE] = json.dumps(mobile.get("capabilities") or {}, indent=2, ensure_ascii=False) + "\n"
        files["pytest.ini"] = PYTEST_INI
        files["requirements.txt"] = REQUIREMENTS
        files[".gitignore"] = MOBILE_GITIGNORE
        files[".env.example"] = ENV_EXAMPLE
        files["README.md"] = self._readme(ctx, mobile, env_names({p: c for p, c in files.items() if p.startswith("tests/")}))
        return files

    def run_hint(self) -> str:
        return "pytest"

    # ------------------------------------------------------------------
    @staticmethod
    def _screen(screen: MobileScreen, elements: list[MobileElement]) -> str:
        lines = [
            f'"""Screen object: {comment_safe(screen.title or screen.screen_key)} (generated by RK Testing Studio)."""',
            "",
            "from appium.webdriver.common.appiumby import AppiumBy",
            "",
            "from screens.mobile.base_screen import BaseScreen",
            "",
            "",
            f"class {screen_class(screen.screen_key)}(BaseScreen):",
            f"    name = {py_str(screen.title or screen.screen_key)}",
            "",
            "    def __init__(self, mobile) -> None:",
            "        super().__init__(mobile)",
        ]
        for element in elements:
            pairs = ", ".join(f"(AppiumBy.{const}, {py_str(value)})" for const, value in locator_pairs(element))
            lines.append(f"        self.{attr_of(element.key)} = self.element({py_str(element.key)}, [{pairs}])")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _call(step: MobileStep, index: dict) -> str:  # type: ignore[type-arg]
        """The line of code that performs one step."""
        action, value = step.action, step.value or ""
        if step.element and step.element in index:
            screen, _ = index[step.element]
            target = f"{screen_var(screen.screen_key)}.{attr_of(step.element)}"
            calls = {
                "tap": f"{target}.tap()", "long_press": f"{target}.long_press()", "type": f"{target}.type({_val(value)})", "clear": f"{target}.clear()",
                "expect_visible": f"{target}.should_be_visible()", "expect_hidden": f"{target}.should_be_hidden()",
                "expect_text": f"{target}.should_have_text({_val(value)})", "expect_enabled": f"{target}.should_be_enabled()",
                "expect_disabled": f"{target}.should_be_disabled()",
            }  # fmt: skip
            return calls[action]
        device = {
            "launch_app": "mobile.relaunch()", "back": "mobile.back()", "hide_keyboard": "mobile.hide_keyboard()", "swipe": f"mobile.swipe({py_str(value)})",
            "rotate": f"mobile.rotate({py_str(value)})", "accept_alert": "mobile.accept_alert()", "dismiss_alert": "mobile.dismiss_alert()",
            "wait": f"mobile.wait({float(value or 1):g})",
        }  # fmt: skip
        return device[action]

    def _tests(self, module: str, items: list, index: dict) -> str:  # type: ignore[no-untyped-def, type-arg]
        screens_used: dict[str, MobileScreen] = {}
        for item in items:
            for step in item.script.steps:
                if step.element and step.element in index:
                    screen = index[step.element][0]
                    screens_used[screen.screen_key] = screen
        lines = [f'"""Mobile tests for module: {comment_safe(module)} (generated by RK Testing Studio)."""', "", "import pytest", ""]
        for key in sorted(screens_used):
            lines.append(f"from screens.mobile.{py_ident(key, 'screen')} import {screen_class(key)}")
        for item in items:
            tc = item.test_case
            used = []
            for step in item.script.steps:
                if step.element and step.element in index and index[step.element][0].screen_key not in used:
                    used.append(index[step.element][0].screen_key)
            lines += [
                "",
                "",
                f"@pytest.mark.tc({py_str(tc.test_case_id)})",
                f"def {case_function_name(tc.test_case_id, tc.title)}(mobile):",
                f'    """{tc.test_case_id}: {comment_safe(tc.title)}',
                "",
                f"    Scenario: {tc.scenario_id}",
                f"    Screen: {comment_safe(tc.related_page)}",
                f"    Expected: {comment_safe(tc.expected_result, 240)}",
                '    """',
            ]
            lines += [f"    {screen_var(key)} = {screen_class(key)}(mobile)" for key in used]
            for step in item.script.steps:
                text = step.description.strip() or f"{step.action} {step.element or step.value or ''}".strip()
                lines.append(f"    with mobile.step({py_str(text)}, action={py_str(step.action)}, element={py_str(step.element or '')}):")
                lines.append(f"        {self._call(step, index)}")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _readme(ctx: RenderContext, mobile: dict, variables: list[str]) -> str:  # type: ignore[type-arg]
        rows = "\n".join(f"| {i.test_case.scenario_id} | {i.test_case.test_case_id} | {i.test_case.related_page} | {i.test_case.title} |" for i in ctx.cases)
        package = mobile.get("package") or "the application"
        extra = "\n".join(f"* `{name}` - a value used by the tests (never commit real values)" for name in variables) or "* (none)"
        return f"""# {ctx.project.name} - mobile tests (Android)

Generated by **RK Testing Studio** (Python + pytest + Appium, UiAutomator2). Application under test: `{package}`.

## Layout

* `tests/mobile/test_*.py` - one test function per test case; each step is recorded with `mobile.step(...)`.
* `screens/mobile/*.py` - screen objects with the element locators (`AppiumBy`: accessibility id, then resource id, then UiAutomator, XPath last).
* `drivers/appium_driver.py` - capabilities, local Appium server and driver. `drivers/mobile_session.py` - step recorder and failure evidence.
* `mobile_config/android.json` - non-secret Appium capabilities (no APK path, no device id, no credentials).

## Requirements

* Python 3.10+, Android SDK (`adb`, `ANDROID_HOME`), Node.js, Appium 2 (`npm i -g appium`) and its UiAutomator2 driver
  (`appium driver install uiautomator2`), and a running emulator or a device with USB debugging enabled.

```
pip install -r requirements.txt
```

## Run

Set what to test (see `.env.example`) and run:

```
set APP_PATH=C:\\path\\to\\app.apk   (or APP_PACKAGE=com.example.app for an installed app)
pytest
```

* `ANDROID_SERIAL` - the device to use (needed when several are connected).
* `APPIUM_SERVER_URL` - an Appium server you already run; when empty the tests start and stop a local one themselves.
* Values written as `{{{{env:NAME}}}}` in the tests come from environment variables:
{extra}

Results: `reports/junit.xml`. Evidence per test case is written to `reports/evidence/<TEST_CASE_ID>/` (steps, and on failure a screenshot, the
page source, the Appium error, the device and the logcat tail).

## Traceability

| Scenario | Test case | Screen | Title |
| --- | --- | --- | --- |
{rows}
"""
