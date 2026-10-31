"""Selenium + Python (pytest) project renderer."""

from __future__ import annotations

from urllib.parse import urlparse

from ats.generation.adapters.common import RenderContext, attr_of, comment_safe, pascal, py_str, readme
from ats.generation.adapters.playwright_python import PlaywrightPythonAdapter, _val
from ats.models import AutomationStep

LOCATORS_PY = '''"""Resolve element keys from config/locators.json into Selenium (By, value) pairs.

The ``resolved`` entry is computed by the studio from the framework-neutral selector. There is no silent fallback.
"""

from __future__ import annotations

import json
from pathlib import Path

from selenium.webdriver.common.by import By

LOCATORS_FILE = Path(__file__).resolve().parent.parent / "config" / "locators.json"
BY = {"css": By.CSS_SELECTOR, "xpath": By.XPATH}


def load_locators() -> dict:
    return json.loads(LOCATORS_FILE.read_text(encoding="utf-8"))


def by_for(spec: dict) -> tuple[str, str]:
    resolved = spec["resolved"]
    return BY[resolved["by"]], resolved["value"]
'''

ELEMENT_PY = '''"""Element wrapper with explicit waits. Mirrors the Playwright page-object API so tests read the same."""

from __future__ import annotations

import re

from selenium.webdriver import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait


def to_key(name: str):
    if len(name) == 1:
        return name
    constant = re.sub(r"(?<!^)(?=[A-Z])", "_", name).upper()
    return getattr(Keys, constant, name)


class Element:
    def __init__(self, app, key: str) -> None:
        self.app = app
        self.key = key

    def _wait(self, condition, message: str):
        return WebDriverWait(self.app.driver, self.app.timeout).until(condition, message)

    def _by(self):
        return self.app.by(self.key)

    def find(self):
        return self._wait(EC.presence_of_element_located(self._by()), f"Element not found: {self.key} {self._by()}")

    def _interactable(self):
        return self._wait(EC.element_to_be_clickable(self._by()), f"Element not clickable: {self.key} {self._by()}")

    def click(self) -> None:
        self._interactable().click()

    def dblclick(self) -> None:
        ActionChains(self.app.driver).double_click(self._interactable()).perform()

    def fill(self, text: str) -> None:
        element = self._interactable()
        element.clear()
        element.send_keys(text)

    def clear(self) -> None:
        self._interactable().clear()

    def select_option(self, label: str) -> None:
        Select(self._interactable()).select_by_visible_text(label)

    def check(self) -> None:
        element = self._interactable()
        if not element.is_selected():
            element.click()

    def uncheck(self) -> None:
        element = self._interactable()
        if element.is_selected():
            element.click()

    def press(self, key: str) -> None:
        self.find().send_keys(to_key(key))

    def hover(self) -> None:
        ActionChains(self.app.driver).move_to_element(self.find()).perform()

    def expect_visible(self) -> None:
        self._wait(EC.visibility_of_element_located(self._by()), f"Element not visible: {self.key}")

    def expect_hidden(self) -> None:
        self._wait(EC.invisibility_of_element_located(self._by()), f"Element still visible: {self.key}")

    def expect_text(self, text: str) -> None:
        self._wait(lambda d: text in (self.find().text or ""), f"Text {text!r} not found in {self.key}")

    def expect_value(self, text: str) -> None:
        self._wait(lambda d: (self.find().get_attribute("value") or "") == text, f"Value of {self.key} is not {text!r}")

    def expect_enabled(self) -> None:
        self._wait(lambda d: self.find().is_enabled(), f"{self.key} is not enabled")

    def expect_disabled(self) -> None:
        self._wait(lambda d: not self.find().is_enabled(), f"{self.key} is not disabled")
'''

APP_PY = '''"""Test session helper: waits, step recording and failure evidence."""

from __future__ import annotations

import json
import os
import re
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urljoin

from selenium.webdriver.support.ui import WebDriverWait

from pages import Pages
from utils.locators import by_for, load_locators

ROOT = Path(__file__).resolve().parent.parent
ENV_PATTERN = re.compile(r"\\{\\{env:([A-Za-z_][A-Za-z0-9_]*)\\}\\}")


class App:
    def __init__(self, driver, base_url: str, test_case_id: str) -> None:
        self.driver = driver
        self.base_url = base_url.rstrip("/") + "/"
        self.test_case_id = test_case_id
        self.timeout = float(os.environ.get("STEP_TIMEOUT", "10"))
        self.locators = load_locators()
        self.steps: list[dict] = []
        self.failure: dict = {}
        self.pages = Pages(self)

    def val(self, text: str) -> str:
        """Substitute {{env:NAME}} placeholders from the environment (values never appear in code or reports)."""

        def lookup(match: re.Match) -> str:
            name = match.group(1)
            if name not in os.environ:
                raise AssertionError(f"Environment variable {name} is not set")
            return os.environ[name]

        return ENV_PATTERN.sub(lookup, text)

    def by(self, key: str) -> tuple[str, str]:
        spec = self.locators.get(key)
        if spec is None:
            raise AssertionError(f"Unknown element key: {key}")
        return by_for(spec)

    def goto(self, target: str) -> None:
        url = target if re.match(r"^https?://", target) else urljoin(self.base_url, target.lstrip("/"))
        self.driver.get(url)

    def expect_url_contains(self, text: str) -> None:
        WebDriverWait(self.driver, self.timeout).until(lambda d: text in d.current_url, f"URL does not contain {text!r}")

    def expect_title_contains(self, text: str) -> None:
        WebDriverWait(self.driver, self.timeout).until(lambda d: text in d.title, f"Title does not contain {text!r}")

    @contextmanager
    def step(self, description: str, action: str = "", element: str = ""):
        record = {"index": len(self.steps) + 1, "description": description, "action": action, "element": element, "status": "running"}
        self.steps.append(record)
        try:
            yield
        except Exception as exc:
            record["status"] = "failed"
            record["error"] = (getattr(exc, "msg", None) or str(exc))[:1500]
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
        info = {"test_case_id": self.test_case_id, **self.failure}
        try:
            info["url"] = self.driver.current_url
            info["title"] = self.driver.title
            (folder / "dom.html").write_text(self.driver.page_source[:500_000], encoding="utf-8")
            self.driver.save_screenshot(str(folder / "screenshot.png"))
            try:
                info["console"] = [f"{e['level']}: {e['message'][:300]}" for e in self.driver.get_log("browser")][-20:]
            except Exception:
                info["console"] = []
        except Exception as exc:
            info["evidence_error"] = str(exc)[:200]
        (folder / "failure.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
'''

CONFTEST_PY = '''import os
import re

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.edge.service import Service as EdgeService

from utils.app import App

DEFAULT_BASE_URL = {base_url}
DEFAULT_BROWSER = {browser}


def build_driver(browser: str):
    headless = os.environ.get("HEADLESS", "1") != "0"
    insecure = os.environ.get("IGNORE_HTTPS_ERRORS") == "1"
    if browser == "firefox":
        options = webdriver.FirefoxOptions()
        if headless:
            options.add_argument("-headless")
        options.accept_insecure_certs = insecure
        return webdriver.Firefox(options=options)
    options = webdriver.EdgeOptions() if browser == "edge" else webdriver.ChromeOptions()
    for argument in ("--no-sandbox", "--disable-dev-shm-usage", "--window-size=1366,900"):
        options.add_argument(argument)
    if headless:
        options.add_argument("--headless=new")
    options.accept_insecure_certs = insecure
    options.set_capability("goog:loggingPrefs", {"browser": "ALL"})
    binary = os.environ.get("CHROME_BIN")
    if binary and browser != "edge":
        options.binary_location = binary
    driver_path = os.environ.get("CHROMEDRIVER")
    if browser == "edge":
        return webdriver.Edge(options=options, service=EdgeService(driver_path) if driver_path else None)
    return webdriver.Chrome(options=options, service=ChromeService(driver_path) if driver_path else None)


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    setattr(item, "rep_" + call.when, outcome.get_result())


@pytest.fixture
def app(request):
    browser = (os.environ.get("BROWSER") or DEFAULT_BROWSER).lower()
    driver = build_driver(browser)
    marker = request.node.get_closest_marker("tc")
    test_case_id = marker.args[0] if marker else re.sub(r"\\W+", "_", request.node.name)
    session = App(driver, os.environ.get("BASE_URL") or DEFAULT_BASE_URL, test_case_id)
    yield session
    report = getattr(request.node, "rep_call", None)
    try:
        session.finish(failed=bool(report and report.failed))
    finally:
        driver.quit()
'''

PYTEST_INI = """[pytest]
testpaths = tests
addopts = -p no:cacheprovider --junitxml=reports/junit.xml
junit_family = xunit2
markers =
    tc(id): the test case identifier this test implements
"""

BASE_PAGE_PY = '''from __future__ import annotations

from utils.element import Element


class BasePage:
    path = "/"

    def __init__(self, app) -> None:
        self.app = app

    def element(self, key: str) -> Element:
        return Element(self.app, key)

    def open(self) -> None:
        self.app.goto(self.path)
'''


class SeleniumPythonAdapter(PlaywrightPythonAdapter):
    key = "selenium_python"
    test_imports = ("import pytest",)
    selenium = True

    def runtime_files(self, ctx: RenderContext) -> dict[str, str]:
        return {
            "utils/locators.py": LOCATORS_PY,
            "utils/element.py": ELEMENT_PY,
            "utils/app.py": APP_PY,
            "conftest.py": CONFTEST_PY.replace("{base_url}", py_str(ctx.base_url)).replace("{browser}", py_str(ctx.browser)),
            "pytest.ini": PYTEST_INI,
            "pages/base_page.py": BASE_PAGE_PY,
            "requirements.txt": "pytest>=8.0\nselenium>=4.20\n",
        }

    def readme_text(self, ctx: RenderContext) -> str:
        return readme(ctx, "Selenium + Python", "pip install -r requirements.txt", f"BROWSER={ctx.browser} pytest")

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
            "select": f"{loc}.select_option({v})",
            "check": f"{loc}.check()",
            "uncheck": f"{loc}.uncheck()",
            "press": f"{loc}.press({v})",
            "hover": f"{loc}.hover()",
            "expect_visible": f"{loc}.expect_visible()",
            "expect_hidden": f"{loc}.expect_hidden()",
            "expect_text": f"{loc}.expect_text({v})",
            "expect_value": f"{loc}.expect_value({v})",
            "expect_enabled": f"{loc}.expect_enabled()",
            "expect_disabled": f"{loc}.expect_disabled()",
            "expect_url_contains": f"app.expect_url_contains({v})",
            "expect_title_contains": f"app.expect_title_contains({v})",
        }
        return mapping[step.action]

    @staticmethod
    def _page(ctx: RenderContext, page_key: str, keys: list[str]) -> str:
        url = next((ctx.locators[k].page_url for k in keys if ctx.locators[k].page_url), "/")
        parsed = urlparse(url)
        path = (parsed.path or "/") + (f"?{parsed.query}" if parsed.query else "")
        lines = [
            "from __future__ import annotations", "", "from pages.base_page import BasePage", "from utils.element import Element", "", "",
            f"class {pascal(page_key)}Page(BasePage):", f'    """Page object for {comment_safe(path)}"""', "", f"    path = {py_str(path)}",
        ]  # fmt: skip
        for key in keys:
            spec = ctx.locators[key]
            lines += [
                "", "    @property", f"    def {attr_of(key)}(self) -> Element:",
                f'        """{comment_safe(spec.intent or spec.name or spec.role or key, 80)}"""', f"        return self.element({py_str(key)})",
            ]  # fmt: skip
        return "\n".join(lines) + "\n"
