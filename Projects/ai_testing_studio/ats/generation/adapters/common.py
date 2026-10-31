"""Shared rendering helpers for the framework adapters."""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ats.models import AutomationStep, LocatorSpec, Scenario, TestCase, TestScript, slugify
from ats.repository import Project

ENV_PLACEHOLDER = re.compile(r"\{\{env:([A-Za-z_][A-Za-z0-9_]*)\}\}")

FRAMEWORKS: dict[str, dict[str, str]] = {
    "playwright_python": {"label": "Playwright + Python (pytest)", "language": "python", "engine": "playwright"},
    "playwright_typescript": {"label": "Playwright + TypeScript", "language": "typescript", "engine": "playwright"},
    "playwright_javascript": {"label": "Playwright + JavaScript", "language": "javascript", "engine": "playwright"},
    "selenium_python": {"label": "Selenium + Python (pytest)", "language": "python", "engine": "selenium"},
    "selenium_java": {"label": "Selenium + Java (JUnit 5, Maven)", "language": "java", "engine": "selenium"},
}
BROWSERS: dict[str, str] = {"chromium": "Chromium", "chrome": "Google Chrome", "firefox": "Firefox", "edge": "Microsoft Edge", "webkit": "WebKit"}
BROWSER_SUPPORT: dict[str, set[str]] = {
    "playwright": {"chromium", "chrome", "firefox", "edge", "webkit"},
    "selenium": {"chromium", "chrome", "firefox", "edge"},
}


def browsers_for(framework: str) -> list[str]:
    engine = FRAMEWORKS[framework]["engine"]
    return [b for b in BROWSERS if b in BROWSER_SUPPORT[engine]]


@dataclass
class ScriptCase:
    """A test case with its validated automation script."""

    test_case: TestCase
    script: TestScript
    module_key: str = ""


@dataclass
class RenderContext:
    project: Project
    base_url: str
    browser: str
    scenarios: dict[str, Scenario]
    cases: list[ScriptCase]
    locators: dict[str, LocatorSpec]
    playwright_version: str = "1.49.0"
    pages: list[str] = field(default_factory=list)

    def modules(self) -> dict[str, list[ScriptCase]]:
        grouped: dict[str, list[ScriptCase]] = {}
        for item in self.cases:
            grouped.setdefault(item.module_key, []).append(item)
        return grouped

    def elements_by_page(self) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        for key, spec in sorted(self.locators.items()):
            result.setdefault(spec.page_key, []).append(key)
        return result


class FrameworkAdapter(ABC):
    key = ""

    @abstractmethod
    def render(self, ctx: RenderContext) -> dict[str, str]:
        """Return ``{relative path: file content}`` for a complete, runnable automation project."""

    def run_hint(self) -> str:
        return ""


# ----------------------------------------------------------------------------------------
# naming
# ----------------------------------------------------------------------------------------
def py_ident(text: str, prefix: str = "x") -> str:
    ident = slugify(text, prefix)
    if ident[0].isdigit():
        ident = f"{prefix}_{ident}"
    return ident


def pascal(text: str) -> str:
    parts = [p for p in re.split(r"[^A-Za-z0-9]+", text) if p]
    value = "".join(p[:1].upper() + p[1:] for p in parts) or "Item"
    return value if not value[0].isdigit() else f"P{value}"


def camel(text: str) -> str:
    value = pascal(text)
    return value[:1].lower() + value[1:]


def attr_of(element_key: str) -> str:
    """The element part of a key such as ``login.email_textbox`` as an identifier."""
    return py_ident(element_key.split(".", 1)[-1], "el")


def module_slug(module: str) -> str:
    return slugify(module, "general")


def case_function_name(tc_id: str, title: str) -> str:
    return f"test_{slugify(tc_id)}_{slugify(title)[:40].rstrip('_')}".rstrip("_")


# ----------------------------------------------------------------------------------------
# literals
# ----------------------------------------------------------------------------------------
def py_str(value: str) -> str:
    return repr(value)


def js_str(value: str) -> str:
    return json.dumps(value, ensure_ascii=False).replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def java_str(value: str) -> str:
    out = []
    for ch in value:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif ord(ch) < 32 or ord(ch) > 126:
            out.append(f"\\u{ord(ch):04x}" if ord(ch) <= 0xFFFF else "".join(f"\\u{u:04x}" for u in _surrogates(ord(ch))))
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def _surrogates(codepoint: int) -> tuple[int, int]:
    codepoint -= 0x10000
    return 0xD800 + (codepoint >> 10), 0xDC00 + (codepoint & 0x3FF)


def comment_safe(text: str, limit: int = 160) -> str:
    """Single-line text that cannot break out of a comment or docstring."""
    return re.sub(r"[\r\n\"'\\*/`]+", " ", text or "").strip()[:limit]


def step_text(step: AutomationStep, tc: TestCase) -> str:
    return step.description.strip() or f"{step.action} {step.element or step.value or ''}".strip()


# ----------------------------------------------------------------------------------------
# locators.json (single source of truth for element lookups; patched by the healing engine)
# ----------------------------------------------------------------------------------------
def locator_entry(spec: LocatorSpec, selenium: bool = False) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "page": spec.page_key, "intent": spec.intent, "role": spec.role, "name": spec.name,
        "preferred": spec.preferred.model_dump(exclude_none=True),
        "alternatives": [s.model_dump(exclude_none=True) for s in spec.alternatives],
    }  # fmt: skip
    if selenium:
        from ats.locators.selenium_map import to_selenium

        entry["resolved"] = to_selenium(spec.preferred)
    return entry


def locators_json(ctx: RenderContext, selenium: bool = False) -> str:
    used = {e for item in ctx.cases for step in item.script.steps if (e := step.element)}
    data = {key: locator_entry(spec, selenium) for key, spec in sorted(ctx.locators.items()) if key in used or not used}
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def readme(ctx: RenderContext, title: str, install: str, run: str) -> str:
    rows = "\n".join(
        f"| {i.test_case.scenario_id} | {i.test_case.test_case_id} | {i.test_case.title} |" for i in ctx.cases
    )
    return f"""# {ctx.project.name} - automated tests

Generated by **AI Autonomous Testing Studio** ({title}).

* Application under test: `{ctx.base_url}` (override with the `BASE_URL` environment variable)
* Browser: `{ctx.browser}` (override with the `BROWSER` environment variable)
* Element lookups live in `config/locators.json`. Tests never contain raw selectors.
* Secrets are never stored here. Values written as `{{{{env:NAME}}}}` are read from environment variables at run time.

## Setup

```
{install}
```

## Run

```
{run}
```

Results: `reports/junit.xml`. Evidence per test case (steps, DOM snapshot, screenshot) is written to `reports/evidence/<TEST_CASE_ID>/`.

## Traceability

| Scenario | Test case | Title |
| --- | --- | --- |
{rows}
"""


GITIGNORE = """__pycache__/
.pytest_cache/
node_modules/
target/
reports/
test-results/
playwright-report/
.env
.venv/
*.pyc
"""

ENV_EXAMPLE = """BASE_URL=
BROWSER=chromium
# Credentials used by tests (never commit real values)
TEST_APP_USERNAME=
TEST_APP_PASSWORD=
"""
