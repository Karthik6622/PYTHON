"""Playwright + Python (pytest) project renderer."""

from __future__ import annotations

from ats.generation.adapters.common import (
    ENV_EXAMPLE,
    ENV_PLACEHOLDER,
    GITIGNORE,
    FrameworkAdapter,
    RenderContext,
    attr_of,
    case_function_name,
    comment_safe,
    locators_json,
    module_slug,
    pascal,
    py_ident,
    py_str,
    readme,
    step_text,
)
from ats.models import AutomationStep

LOCATORS_PY = '''"""Resolve element keys from config/locators.json into Playwright locators.

There is deliberately no silent fallback: a stale locator must fail loudly so it can be analysed (and healed with approval).
"""

from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import Locator, Page

LOCATORS_FILE = Path(__file__).resolve().parent.parent / "config" / "locators.json"


def load_locators() -> dict:
    return json.loads(LOCATORS_FILE.read_text(encoding="utf-8"))


def resolve(page: Page, selector: dict) -> Locator:
    kind, value = selector["kind"], selector["value"]
    name, exact = selector.get("name"), bool(selector.get("exact", False))
    if kind == "testid":
        return page.get_by_test_id(value)
    if kind == "role":
        return page.get_by_role(value, name=name, exact=exact) if name else page.get_by_role(value)
    if kind == "label":
        return page.get_by_label(value, exact=exact)
    if kind == "placeholder":
        return page.get_by_placeholder(value, exact=exact)
    if kind == "text":
        return page.get_by_text(value, exact=exact)
    if kind == "id":
        return page.locator('[id="' + value.replace('"', '\\\\"') + '"]')
    if kind == "name":
        return page.locator('[name="' + value.replace('"', '\\\\"') + '"]')
    if kind == "xpath":
        return page.locator("xpath=" + value)
    return page.locator(value)
'''

APP_PY = '''"""Test session helper: element lookup, step recording and failure evidence."""

from __future__ import annotations

import json
import os
import re
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import Page

from pages import Pages
from utils.locators import load_locators, resolve

ROOT = Path(__file__).resolve().parent.parent
ENV_PATTERN = re.compile(r"\\{\\{env:([A-Za-z_][A-Za-z0-9_]*)\\}\\}")


class App:
    def __init__(self, page: Page, base_url: str, test_case_id: str) -> None:
        self.page = page
        self.base_url = base_url.rstrip("/") + "/"
        self.test_case_id = test_case_id
        self.locators = load_locators()
        self.steps: list[dict] = []
        self.console: list[str] = []
        self.failure: dict = {}
        self.pages = Pages(self)
        page.on("console", lambda m: self.console.append(f"{m.type}: {m.text[:300]}") if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: self.console.append(f"pageerror: {str(e)[:300]}"))

    def val(self, text: str) -> str:
        """Substitute {{env:NAME}} placeholders from the environment (values never appear in code or reports)."""

        def lookup(match: re.Match) -> str:
            name = match.group(1)
            if name not in os.environ:
                raise AssertionError(f"Environment variable {name} is not set")
            return os.environ[name]

        return ENV_PATTERN.sub(lookup, text)

    def locator(self, key: str):
        spec = self.locators.get(key)
        if spec is None:
            raise AssertionError(f"Unknown element key: {key}")
        return resolve(self.page, spec["preferred"])

    def goto(self, target: str) -> None:
        url = target if re.match(r"^https?://", target) else urljoin(self.base_url, target.lstrip("/"))
        self.page.goto(url, wait_until="domcontentloaded")

    @contextmanager
    def step(self, description: str, action: str = "", element: str = ""):
        record = {"index": len(self.steps) + 1, "description": description, "action": action, "element": element, "status": "running"}
        self.steps.append(record)
        try:
            yield
        except Exception as exc:
            record["status"] = "failed"
            record["error"] = str(exc)[:1500]
            self.failure = {"step": record["index"], "action": action, "element": element, "error": record["error"]}
            raise
        else:
            record["status"] = "passed"

    def finish(self, failed: bool) -> None:
        folder = ROOT / "reports" / "evidence" / self.test_case_id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "steps.json").write_text(json.dumps(self.steps, indent=2), encoding="utf-8")
        if not failed:
            return
        info = {"test_case_id": self.test_case_id, "console": self.console[-20:], **self.failure}
        try:
            info["url"] = self.page.url
            info["title"] = self.page.title()
            (folder / "dom.html").write_text(self.page.content()[:500_000], encoding="utf-8")
            self.page.screenshot(path=str(folder / "screenshot.png"))
        except Exception as exc:  # the page may already be closed; evidence is best effort
            info["evidence_error"] = str(exc)[:200]
        (folder / "failure.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
'''

CONFTEST_PY = '''import os
import re
from pathlib import Path

import pytest

from utils.app import App

DEFAULT_BASE_URL = {base_url}


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {**browser_context_args, "ignore_https_errors": os.environ.get("IGNORE_HTTPS_ERRORS") == "1"}


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    setattr(item, "rep_" + call.when, outcome.get_result())


@pytest.fixture
def app(page, request):
    marker = request.node.get_closest_marker("tc")
    test_case_id = marker.args[0] if marker else re.sub(r"\\W+", "_", request.node.name)
    session = App(page, os.environ.get("BASE_URL") or DEFAULT_BASE_URL, test_case_id)
    yield session
    report = getattr(request.node, "rep_call", None)
    session.finish(failed=bool(report and report.failed))
'''

BASE_PAGE_PY = '''from __future__ import annotations

from playwright.sync_api import Locator


class BasePage:
    path = "/"

    def __init__(self, app) -> None:
        self.app = app

    def locator(self, key: str) -> Locator:
        return self.app.locator(key)

    def open(self) -> None:
        self.app.goto(self.path)
'''

PYTEST_INI = """[pytest]
testpaths = tests
addopts = -p no:cacheprovider --junitxml=reports/junit.xml --screenshot=only-on-failure --tracing=retain-on-failure --video=retain-on-failure --output=reports/artifacts
junit_family = xunit2
markers =
    tc(id): the test case identifier this test implements
"""


def _val(text: str) -> str:
    return f"app.val({py_str(text)})" if ENV_PLACEHOLDER.search(text) else py_str(text)


class PlaywrightPythonAdapter(FrameworkAdapter):
    key = "playwright_python"
    test_imports = ("import re", "", "import pytest", "from playwright.sync_api import expect")
    selenium = False

    def runtime_files(self, ctx: RenderContext) -> dict[str, str]:
        return {
            "utils/locators.py": LOCATORS_PY,
            "utils/app.py": APP_PY,
            "conftest.py": CONFTEST_PY.replace("{base_url}", py_str(ctx.base_url)),
            "pytest.ini": PYTEST_INI,
            "pages/base_page.py": BASE_PAGE_PY,
            "requirements.txt": f"pytest>=8.0\npytest-playwright>=0.5\nplaywright=={ctx.playwright_version}\n",
        }

    def readme_text(self, ctx: RenderContext) -> str:
        return readme(
            ctx, "Playwright + Python",
            "pip install -r requirements.txt\nplaywright install chromium firefox webkit",
            f"pytest --browser {ctx.browser if ctx.browser in ('chromium', 'firefox', 'webkit') else 'chromium'}",
        )  # fmt: skip

    def render(self, ctx: RenderContext) -> dict[str, str]:
        files: dict[str, str] = {}
        used: dict[str, list[str]] = {}
        for item in ctx.cases:
            for step in item.script.steps:
                if step.element:
                    spec = ctx.locators[step.element]
                    used.setdefault(spec.page_key, [])
                    if step.element not in used[spec.page_key]:
                        used[spec.page_key].append(step.element)

        def ref(key: str) -> str:
            return f"app.pages.{py_ident(ctx.locators[key].page_key, 'page')}.{attr_of(key)}"

        for module_key, items in ctx.modules().items():
            files[f"tests/test_{module_slug(module_key)}.py"] = self._tests(module_key, items, ref)
        for page_key, keys in used.items():
            files[f"pages/{py_ident(page_key, 'page')}_page.py"] = self._page(ctx, page_key, keys)
        files["pages/__init__.py"] = self._pages_init(used)
        files["utils/__init__.py"] = ""
        files["tests/__init__.py"] = ""
        files.update(self.runtime_files(ctx))
        files["config/locators.json"] = locators_json(ctx, selenium=self.selenium)
        files["README.md"] = self.readme_text(ctx)
        files[".gitignore"] = GITIGNORE
        files[".env.example"] = ENV_EXAMPLE
        return files

    # ------------------------------------------------------------------
    def _tests(self, module: str, items: list, ref) -> str:  # type: ignore[no-untyped-def]
        lines = [f'"""Automated tests for module: {comment_safe(module)} (generated by AI Autonomous Testing Studio)."""', "", *self.test_imports, ""]
        for item in items:
            tc, script = item.test_case, item.script
            lines += [
                "",
                f"@pytest.mark.tc({py_str(tc.test_case_id)})",
                f"def {case_function_name(tc.test_case_id, tc.title)}(app):",
                f'    """{tc.test_case_id}: {comment_safe(tc.title)}',
                "",
                f"    Scenario: {tc.scenario_id}",
                f"    Expected: {comment_safe(tc.expected_result, 240)}",
            ]
            if script.notes:
                lines.append(f"    Note: {comment_safe(script.notes, 240)}")
            lines.append('    """')
            for step in script.steps:
                lines.append(f"    with app.step({py_str(step_text(step, tc))}, action={py_str(step.action)}, element={py_str(step.element or '')}):")
                lines.append(f"        {self._statement(step, ref)}")
            if not script.steps:
                lines.append("    pytest.skip('No automatable steps')")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _statement(step: AutomationStep, ref) -> str:  # type: ignore[no-untyped-def]
        loc = ref(step.element) if step.element else ""
        v = _val(step.value or "")
        mapping = {
            "goto": f"app.goto({v})",
            "click": f"{loc}.click()",
            "dblclick": f"{loc}.dblclick()",
            "fill": f"{loc}.fill({v})",
            "clear": f"{loc}.clear()",
            "select": f"{loc}.select_option(label={v})",
            "check": f"{loc}.check()",
            "uncheck": f"{loc}.uncheck()",
            "press": f"{loc}.press({v})",
            "hover": f"{loc}.hover()",
            "expect_visible": f"expect({loc}).to_be_visible()",
            "expect_hidden": f"expect({loc}).to_be_hidden()",
            "expect_text": f"expect({loc}).to_contain_text({v})",
            "expect_value": f"expect({loc}).to_have_value({v})",
            "expect_enabled": f"expect({loc}).to_be_enabled()",
            "expect_disabled": f"expect({loc}).to_be_disabled()",
            "expect_url_contains": f"expect(app.page).to_have_url(re.compile(re.escape({v})))",
            "expect_title_contains": f"expect(app.page).to_have_title(re.compile(re.escape({v})))",
        }
        return mapping[step.action]

    @staticmethod
    def _page(ctx: RenderContext, page_key: str, keys: list[str]) -> str:
        url = next((ctx.locators[k].page_url for k in keys if ctx.locators[k].page_url), "/")
        from urllib.parse import urlparse

        path = urlparse(url).path or "/"
        if urlparse(url).query:
            path += "?" + urlparse(url).query
        lines = [
            "from __future__ import annotations", "", "from playwright.sync_api import Locator", "", "from pages.base_page import BasePage", "", "",
            f"class {pascal(page_key)}Page(BasePage):",
            f'    """Page object for {comment_safe(path)}"""', "", f"    path = {py_str(path)}",
        ]  # fmt: skip
        for key in keys:
            spec = ctx.locators[key]
            lines += [
                "", "    @property", f"    def {attr_of(key)}(self) -> Locator:",
                f'        """{comment_safe(spec.intent or spec.name or spec.role or key, 80)}"""', f"        return self.locator({py_str(key)})",
            ]  # fmt: skip
        return "\n".join(lines) + "\n"

    @staticmethod
    def _pages_init(used: dict[str, list[str]]) -> str:
        lines = ["from __future__ import annotations", ""]
        for page_key in used:
            lines.append(f"from pages.{py_ident(page_key, 'page')}_page import {pascal(page_key)}Page")
        lines += ["", "", "class Pages:", "    def __init__(self, app) -> None:"]
        lines += [f"        self.{py_ident(k, 'page')} = {pascal(k)}Page(app)" for k in used] or ["        pass"]
        return "\n".join(lines) + "\n"
