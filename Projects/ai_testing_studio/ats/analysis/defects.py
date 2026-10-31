"""Defect drafts for failures that automation healing cannot (and must not) fix."""

from __future__ import annotations

from typing import Any

from ats.ai.agents import ReportAgent
from ats.analysis.findings import Finding
from ats.errors import StudioError
from ats.execution.executor import ExecutionContext
from ats.logging_setup import get_logger
from ats.models import DefectNarrative, FailureCategory, TestCase
from ats.repository import Project, Repository
from ats.security import mask, mask_obj

LOGGER = get_logger("analysis.defects")
DEFECT_CATEGORIES = {FailureCategory.APPLICATION_DEFECT.value, FailureCategory.ASSERTION.value}


def reproduction_steps(case: TestCase | None, executed: list[dict[str, Any]]) -> list[str]:
    """Steps that were actually executed, in order. Falls back to the written test steps when the run left no step log."""
    steps = [str(s.get("description") or f"{s.get('action', '')} {s.get('element', '')}").strip() for s in executed if s.get("description") or s.get("action")]
    if steps:
        return steps
    return list(case.steps) if case else []


def defect_id(execution_id: str, test_case_id: str) -> str:
    return f"DEF-{execution_id.removeprefix('EX-').upper()[:6]}-{test_case_id.upper()}"


class DefectBuilder:
    def __init__(self, repo: Repository, agent: ReportAgent | None = None) -> None:
        self.repo = repo
        self.agent = agent or ReportAgent(repository=repo)

    def build(self, ctx: ExecutionContext, finding: Finding, execution: dict[str, Any] | None = None) -> dict[str, Any]:
        case = next((c for c in self.repo.list_test_cases(ctx.project.id) if c.test_case_id == finding.test_case_id), None)
        evidence = finding.result.get("evidence") or {}
        executed = evidence.get("steps") or []
        steps = reproduction_steps(case, executed)
        console = [mask(str(c))[:300] for c in finding.failure.get("console", [])][-10:]
        environment = {
            "environment": ctx.project.environment, "base_url": ctx.project.app_base_url, "browser": ctx.browser, "framework": ctx.framework,
            "branch": (execution or {}).get("branch", ""), "commit": (execution or {}).get("commit_sha", ""), "execution_id": ctx.execution_id,
            "page_url": finding.url,
        }  # fmt: skip
        payload = {
            "test_case": case.model_dump(include={"test_case_id", "title", "expected_result", "priority", "test_type", "description"}) if case else {"test_case_id": finding.test_case_id},
            "environment": environment, "reproduction_steps": steps, "error_message": finding.error,
            "analysis": {"category": finding.category, "summary": finding.analysis.summary, "reasoning": finding.analysis.reasoning, "confidence": finding.analysis.confidence},
            "console_evidence": console,
        }  # fmt: skip
        try:
            narrative = self.agent.defect(mask_obj(payload), ctx.project.id)
        except StudioError as exc:
            LOGGER.warning("Defect narrative by AI unavailable: %s", exc.user_message)
            narrative = DefectNarrative(
                title=f"{finding.test_case_id}: {case.title if case else finding.result.get('test_name', 'test failed')}",
                description=finding.analysis.summary or finding.hint.reason, severity=case.priority if case else "Medium", priority=case.priority if case else "Medium",
                actual_result=finding.error[:400],
            )  # fmt: skip
        data = {
            "defect_id": defect_id(ctx.execution_id, finding.test_case_id), "test_case_id": finding.test_case_id,
            "scenario_id": case.scenario_id if case else "", "title": narrative.title, "description": narrative.description,
            "steps_to_reproduce": steps, "expected_result": case.expected_result if case else "", "actual_result": narrative.actual_result or finding.error[:400],
            "severity": narrative.severity, "priority": narrative.priority, "environment": environment, "category": finding.category,
            "confidence": finding.analysis.confidence, "analysis_summary": finding.analysis.summary,
            "evidence": {"screenshot": evidence.get("screenshot", ""), "dom": evidence.get("dom", ""), "console": console, "error": finding.error[:600]},
            "status": "Draft",
        }  # fmt: skip
        return data

    def save(self, project: Project, ctx: ExecutionContext, finding: Finding, execution: dict[str, Any] | None = None) -> dict[str, Any]:
        data = self.build(ctx, finding, execution)
        self.repo.save_defect(project.id, ctx.execution_id, finding.test_case_id, data)
        self.repo.audit(project.id, "system", "defect.drafted", "defect", {"id": data["defect_id"], "test": finding.test_case_id})
        return data
