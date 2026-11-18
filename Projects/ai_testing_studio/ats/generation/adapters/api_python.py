"""API tests: Python + pytest + httpx project renderer. Fully deterministic - the test cases already contain the structured requests."""

from __future__ import annotations

import json
import re
import textwrap
from pathlib import Path
from pprint import pformat
from typing import Any

from ats.generation.adapters.common import (
    GITIGNORE,
    FrameworkAdapter,
    RenderContext,
    case_function_name,
    comment_safe,
    module_slug,
    py_str,
)
from ats.models import ApiRequest

RUNTIME_DIR = Path(__file__).with_name("runtime_api")
API_PY = (RUNTIME_DIR / "api.py").read_text(encoding="utf-8")
MAIL_PY = (RUNTIME_DIR / "mail.py").read_text(encoding="utf-8")
CONFTEST_PY = (RUNTIME_DIR / "conftest.py").read_text(encoding="utf-8")
CONFIG_FILE = "config/api.json"
TESTS_DIR = "tests/api"  # one folder per channel, each with its own conftest.py

PYTEST_INI = """[pytest]
testpaths = tests
addopts = -p no:cacheprovider --junitxml=reports/junit.xml
junit_family = xunit2
markers =
    tc(id): the test case identifier this test implements
"""
REQUIREMENTS = "pytest>=8.0\nhttpx>=0.27\njsonschema>=4.0\n"
AUTH_RE = re.compile(r"""'auth':\s*'([^']+)'""")


def request_spec(request: ApiRequest) -> dict[str, Any]:
    """The dictionary a generated test passes to ``api.send``: only the parts that are used, expectations included."""
    expect = request.expect.model_dump(by_alias=True, exclude_none=True)
    expect = {k: v for k, v in expect.items() if v not in ({}, [], None)}
    spec: dict[str, Any] = {"method": request.method, "path": request.path}
    for key in ("path_params", "query", "headers"):
        if getattr(request, key):
            spec[key] = getattr(request, key)
    if request.body is not None:
        spec["body"] = request.body
    if request.auth:
        spec["auth"] = request.auth
    if request.save:
        spec["save"] = request.save
    spec["expect"] = expect
    return spec


def mail_config(descriptors: dict[str, dict[str, Any]]) -> dict[str, dict[str, str]]:
    """Environment-variable NAMES of the saved mail connections (smtp / imap) for utils/mail.py."""
    result: dict[str, dict[str, str]] = {}
    for descriptor in descriptors.values():
        if descriptor.get("type") in ("smtp", "imap") and descriptor.get("vars"):
            result[descriptor["type"]] = dict(descriptor["vars"])
    return result


def connection_descriptors(descriptors: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Descriptors the runtime can authenticate with (api_key, bearer, basic, oauth2)."""
    return {name: d for name, d in descriptors.items() if d.get("type") in {"api_key", "bearer", "basic", "oauth2"}}


def api_config_json(base_url: str, descriptors: dict[str, dict[str, Any]], endpoints: list[dict[str, Any]]) -> str:
    config = {
        "base_url": base_url, "timeout": 30, "connections": connection_descriptors(descriptors), "mail": mail_config(descriptors), "endpoints": endpoints,
    }  # fmt: skip
    return json.dumps(config, indent=2, ensure_ascii=False) + "\n"


def env_names(descriptors: dict[str, dict[str, Any]]) -> list[str]:
    names: set[str] = set()
    for descriptor in descriptors.values():
        for key, value in descriptor.items():
            if (key == "env" or key.endswith("_env")) and value:
                names.add(str(value))
        names.update(str(v) for v in (descriptor.get("vars") or {}).values())
    return sorted(names)


def with_connections(files: dict[str, str], descriptors: dict[str, dict[str, Any]], base_url: str = "") -> dict[str, str]:
    """The project files with the CURRENT connection descriptors (and base URL) in config/api.json.

    Connections are saved independently of generation, so a run always starts from the descriptors as they are now."""
    try:
        config = json.loads(files.get(CONFIG_FILE, "{}"))
    except ValueError:
        config = {}
    config["connections"] = connection_descriptors(descriptors)
    config["mail"] = mail_config(descriptors)
    if base_url:
        config["base_url"] = base_url
    return {**files, CONFIG_FILE: json.dumps(config, indent=2, ensure_ascii=False) + "\n"}


def api_requirements(files: dict[str, str], descriptors: dict[str, dict[str, Any]]) -> tuple[list[str], list[str]]:
    """``(variables the tests need, connection names used by tests that are not saved)``."""
    used = {name for rel, text in files.items() if rel.startswith("tests/") for name in AUTH_RE.findall(text)}
    missing = sorted(name for name in used if name not in connection_descriptors(descriptors))
    needed = env_names({name: d for name, d in descriptors.items() if name in used})
    return needed, missing


class ApiPythonAdapter(FrameworkAdapter):
    key = "api_python"

    def render(self, ctx: RenderContext) -> dict[str, str]:
        files: dict[str, str] = {}
        for module_key, items in ctx.modules().items():
            files[f"{TESTS_DIR}/test_{module_slug(module_key)}.py"] = self._tests(module_key, items)
        descriptors = ctx.api_config.get("connections", {})
        files["tests/__init__.py"] = ""
        files[f"{TESTS_DIR}/__init__.py"] = ""
        files["utils/__init__.py"] = ""
        files["utils/api.py"] = API_PY
        files["utils/mail.py"] = MAIL_PY
        files[f"{TESTS_DIR}/conftest.py"] = CONFTEST_PY
        files["pytest.ini"] = PYTEST_INI
        files["requirements.txt"] = REQUIREMENTS
        files[CONFIG_FILE] = api_config_json(ctx.base_url, descriptors, ctx.api_config.get("endpoints", []))
        files["README.md"] = self._readme(ctx)
        files[".gitignore"] = GITIGNORE
        files[".env.example"] = self._env_example(ctx, descriptors)
        return files

    def run_hint(self) -> str:
        return "pytest"

    # ------------------------------------------------------------------
    @staticmethod
    def _tests(module: str, items: list) -> str:  # type: ignore[no-untyped-def]
        lines = [f'"""API tests for module: {comment_safe(module)} (generated by AI Autonomous Testing Studio)."""', "", "import pytest", ""]
        for item in items:
            tc = item.test_case
            requests = tc.api.requests if tc.api else []
            lines += [
                "",
                f"@pytest.mark.tc({py_str(tc.test_case_id)})",
                f"def {case_function_name(tc.test_case_id, tc.title)}(api):",
                f'    """{tc.test_case_id}: {comment_safe(tc.title)}',
                "",
                f"    Scenario: {tc.scenario_id}",
                f"    Endpoint: {comment_safe(tc.related_page)}",
                f"    Expected: {comment_safe(tc.expected_result, 240)}",
                '    """',
            ]
            for request in requests:
                name = request.name.strip() or f"{request.method} {request.path}"
                lines.append(f"    with api.step({py_str(name)}, method={py_str(request.method)}, path={py_str(request.path)}):")
                spec = textwrap.indent(pformat(request_spec(request), width=110, sort_dicts=False), " " * 12)
                lines += ["        api.send(", spec, "        )"]
            if not requests:
                lines.append("    pytest.skip('This test case has no API requests')")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _env_example(ctx: RenderContext, descriptors: dict[str, dict[str, Any]]) -> str:
        lines = ["# Address of the API under test (API_BASE_URL wins over BASE_URL)", f"API_BASE_URL={ctx.base_url}", ""]
        names = env_names(descriptors)
        if names:
            lines.append("# Values of the saved connections (never commit real values)")
            lines += [f"{name}=" for name in names]
        return "\n".join(lines) + "\n"

    @staticmethod
    def _readme(ctx: RenderContext) -> str:
        rows = "\n".join(f"| {i.test_case.scenario_id} | {i.test_case.test_case_id} | {i.test_case.related_page} | {i.test_case.title} |" for i in ctx.cases)
        return f"""# {ctx.project.name} - API tests

Generated by **AI Autonomous Testing Studio** (Python + pytest + httpx).

* API under test: `{ctx.base_url}` (override with `API_BASE_URL`, or `BASE_URL`)
* Requests, expectations and saved values of every test live in `tests/api/test_*.py`; the HTTP/assert engine is `utils/api.py`.
* `config/api.json` lists the endpoints and how each saved connection authenticates. It contains variable NAMES only - the values
  are read from environment variables at run time and are masked in all evidence.
* Values written as `{{{{env:NAME}}}}` come from environment variables; `{{{{var.name}}}}` is a value saved from an earlier response.
* `utils/mail.py` has optional helpers (`send_mail`, `wait_for_mail`, `extract_code`) for verification-mail flows.

## Setup

```
pip install -r requirements.txt
```

## Run

```
pytest
```

Results: `reports/junit.xml`. Evidence per test case (steps, every request/response with secrets masked, failure details) is written to
`reports/evidence/<TEST_CASE_ID>/`.

## Traceability

| Scenario | Test case | Endpoint | Title |
| --- | --- | --- | --- |
{rows}
"""
