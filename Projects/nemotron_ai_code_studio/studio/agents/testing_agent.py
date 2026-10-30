"""Testing agent: validates the agent's edits by running the linter and the test suite through the normal (approved) tool path."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from ..tools import devtools
from ..tools.registry import ToolContext, ToolOutcome

RunTool = Callable[[ToolContext, str, str, dict[str, Any]], Awaitable[ToolOutcome]]


@dataclass
class ValidationReport:
    passed: bool | None  # None: nothing could be run
    steps: list[dict[str, Any]] = field(default_factory=list)
    failure_output: str = ""

    def public(self) -> dict[str, Any]:
        return {"passed": self.passed, "steps": self.steps}


class TestingAgent:
    __test__ = False  # not a pytest class

    async def validate(self, ctx: ToolContext, run_tool: RunTool) -> ValidationReport:
        report = ValidationReport(passed=None)
        failures: list[str] = []
        ran_anything = False

        lint = await run_tool(ctx, "validate-lint", "run_linter", {})
        lint_failed = lint.ok and _failed(lint.content)
        report.steps.append({"name": "Lint / syntax check", "status": _status(lint, lint_failed)})
        ran_anything |= lint.ok
        if lint_failed:
            failures.append(lint.content)

        try:
            devtools.detect_test_command(ctx.repo)
            has_tests = True
        except devtools.ToolSetupError:
            has_tests = False
        if has_tests:
            tests = await run_tool(ctx, "validate-tests", "run_tests", {})
            test_failed = tests.ok and _failed(tests.content)
            report.steps.append({"name": "Tests", "status": _status(tests, test_failed)})
            ran_anything |= tests.ok
            if test_failed:
                failures.append(tests.content)
        else:
            report.steps.append({"name": "Tests", "status": "skipped (no test runner detected)"})

        report.failure_output = "\n\n".join(failures)
        report.passed = None if not ran_anything else not failures
        return report


def _failed(content: str) -> bool:
    lines = content.splitlines()
    status = lines[1] if len(lines) > 1 else ""
    if "timed out" in status or "cancelled" in status:
        return True
    if "exit code" in status:
        if "no tests ran" in content.lower() or "no tests collected" in content.lower():
            return False
        return "exit code 0" not in status
    return "SyntaxError" in content


def _status(outcome: ToolOutcome, failed: bool) -> str:
    if not outcome.ok:
        return "skipped (" + outcome.summary + ")" if outcome.summary else "skipped"
    return "failed" if failed else "passed"
