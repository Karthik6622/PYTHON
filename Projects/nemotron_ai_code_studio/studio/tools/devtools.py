"""Developer-tool helpers shared by the agent tools and the REST API: detect and run tests, linters and formatters."""

from __future__ import annotations

import ast
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from ..services.repository_service import ActiveRepository
from ..services.terminal_service import CommandResult

SOURCE_SUFFIXES = {
    "python": {".py"},
    "js": {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".css", ".scss", ".json", ".html", ".md"},
}


class ToolSetupError(Exception):
    """No suitable runner is configured in the repository."""


def _read(root: Path, name: str) -> str:
    try:
        return (root / name).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _package_scripts(root: Path) -> dict[str, str]:
    try:
        data = json.loads(_read(root, "package.json") or "{}")
    except ValueError:
        return {}
    scripts = data.get("scripts") if isinstance(data, dict) else {}
    return scripts if isinstance(scripts, dict) else {}


def python_executable(root: Path) -> str:
    """The repository's own virtualenv when it has one, otherwise the python on PATH, otherwise this backend's python."""
    for candidate in (root / ".venv" / "Scripts" / "python.exe", root / "venv" / "Scripts" / "python.exe",
                      root / ".venv" / "bin" / "python", root / "venv" / "bin" / "python"):
        if candidate.is_file():
            return f'"{candidate}"'
    found = shutil.which("python") or shutil.which("python3") or sys.executable
    return f'"{found}"' if " " in found else found


def _quote_path(path: str) -> str:
    if not path:
        return ""
    if any(ch in path for ch in '"&|;<>`$\n'):
        raise ToolSetupError("The path contains characters that are not allowed in a command.")
    return f' "{path}"' if " " in path else f" {path}"


def detect_test_command(repo: ActiveRepository, path: str = "") -> str:
    root = repo.path
    scripts = _package_scripts(root)
    py_tests = (
        any((root / name).exists() for name in ("pytest.ini", "conftest.py", "tox.ini"))
        or "[tool.pytest" in _read(root, "pyproject.toml")
        or any(p.endswith(".py") and (Path(p).name.startswith("test_") or Path(p).name.endswith("_test.py")) for p in repo.index.files)
    )
    js_tests = bool(scripts.get("test"))
    if py_tests and js_tests:
        languages = list(repo.index.language_counts())
        py_tests = bool(languages) and languages[0] == "python"
        js_tests = not py_tests
    if py_tests:
        return f"{python_executable(root)} -m pytest -q -x --maxfail=5{_quote_path(path)}"
    if js_tests:
        return "npm test --silent" + (f" --{_quote_path(path)}" if path else "")
    if (root / "go.mod").exists():
        return "go test ./..."
    if (root / "Cargo.toml").exists():
        return "cargo test"
    raise ToolSetupError("No test runner was detected (looked for pytest, an npm test script, go test and cargo test). Pass a command explicitly.")


def detect_lint_command(repo: ActiveRepository, path: str = "") -> str | None:
    """None means no linter is configured; the caller falls back to the built-in Python syntax check."""
    root = repo.path
    scripts = _package_scripts(root)
    pyproject = _read(root, "pyproject.toml")
    if (root / "ruff.toml").exists() or (root / ".ruff.toml").exists() or "[tool.ruff" in pyproject:
        return f"{python_executable(root)} -m ruff check{_quote_path(path) or ' .'}"
    if (root / ".flake8").exists() or "flake8" in _read(root, "setup.cfg") or "flake8" in _read(root, "tox.ini"):
        return f"{python_executable(root)} -m flake8{_quote_path(path)}"
    if scripts.get("lint"):
        return "npm run lint --silent"
    return None


def detect_format_command(repo: ActiveRepository, path: str = "") -> tuple[str, str]:
    """Returns (command, language group) so the caller knows which files may change."""
    root = repo.path
    scripts = _package_scripts(root)
    pyproject = _read(root, "pyproject.toml")
    if "[tool.ruff" in pyproject or (root / "ruff.toml").exists():
        return f"{python_executable(root)} -m ruff format{_quote_path(path) or ' .'}", "python"
    if "[tool.black" in pyproject:
        return f"{python_executable(root)} -m black{_quote_path(path) or ' .'}", "python"
    if scripts.get("format"):
        return "npm run format --silent", "js"
    if any((root / name).exists() for name in (".prettierrc", ".prettierrc.json", "prettier.config.js")):
        return f"npx prettier --write{_quote_path(path) or ' .'}", "js"
    raise ToolSetupError("No formatter was detected (looked for ruff, black, an npm format script and prettier). Pass a command explicitly.")


def files_in_scope(repo: ActiveRepository, path: str, group: str) -> list[str]:
    suffixes = SOURCE_SUFFIXES.get(group, set())
    prefix = path.strip("/")
    return [p for p in repo.index.files if (not suffixes or Path(p).suffix.lower() in suffixes) and (not prefix or p == prefix or p.startswith(prefix + "/"))]


def syntax_check(repo: ActiveRepository, path: str = "") -> CommandResult:
    """Built-in fallback linter: reports Python files that do not parse."""
    prefix = path.strip("/")
    problems: list[str] = []
    checked = 0
    for relative in repo.index.files:
        if not relative.endswith(".py") or (prefix and not (relative == prefix or relative.startswith(prefix + "/"))):
            continue
        checked += 1
        try:
            ast.parse((repo.path / relative).read_text(encoding="utf-8", errors="replace"), filename=relative)
        except SyntaxError as exc:
            problems.append(f"{relative}:{exc.lineno or 1}: SyntaxError: {exc.msg}")
        except (OSError, ValueError) as exc:
            problems.append(f"{relative}: could not be checked ({exc.__class__.__name__})")
    text = "\n".join(problems) if problems else f"No syntax errors found in {checked} Python file(s). (No linter is configured in this repository.)"
    return CommandResult("built-in syntax check", 1 if problems else 0, text)


def parse_problems(output: str) -> list[dict[str, Any]]:
    """Turn path:line[:col]: message lines from linters, compilers and test runners into a Problems list."""
    import re

    found: list[dict[str, Any]] = []
    pattern = re.compile(r"^\s*(?P<path>[\w./\\\-]+\.\w+):(?P<line>\d+)(?::(?P<col>\d+))?:?\s*(?P<msg>.+)$")
    for line in output.splitlines():
        match = pattern.match(line)
        if match and len(found) < 200:
            found.append({
                "path": match.group("path").replace("\\", "/"), "line": int(match.group("line")),
                "column": int(match.group("col") or 1), "message": match.group("msg").strip()[:300],
            })
    return found
