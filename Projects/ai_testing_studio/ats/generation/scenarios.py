"""Scenario generation, review operations (approve / edit / delete / regenerate / add) and AI change requests."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ats.ai.agents import ScenarioAgent
from ats.discovery.service import build_digest
from ats.errors import GenerationError
from ats.generation.common import apply_changeset, next_id, norm_title, valid_id
from ats.models import COVERAGE_GUIDE, TEST_TYPES, Scenario
from ats.repository import Project, Repository

EventCallback = Callable[[str, str], None]


def _application(project: Project, discovery: Any) -> dict[str, Any]:
    return {
        "name": project.name, "url": project.url, "environment": project.environment, "description": project.description,
        "summary": discovery.summary, "modules": discovery.analysis.get("modules", []), "workflows": discovery.analysis.get("workflows", []),
    }  # fmt: skip


class ScenarioService:
    def __init__(self, repo: Repository, agent: ScenarioAgent | None = None) -> None:
        self.repo = repo
        self.agent = agent or ScenarioAgent(repository=repo)

    # ------------------------------------------------------------------ generation
    def generate(self, project: Project, requirements: str = "", on_event: EventCallback | None = None) -> list[Scenario]:
        """Generate scenarios for the latest discovery. Replaces existing scenarios (they must be reviewed again)."""
        discovery = self.repo.latest_successful_discovery(project.id)
        if discovery is None:
            raise GenerationError("Run website discovery before generating scenarios.")
        allowed = project.custom_categories if project.coverage == "CUSTOM" and project.custom_categories else TEST_TYPES
        payload = {
            "coverage": project.coverage, "coverage_guide": COVERAGE_GUIDE.get(project.coverage, ""),
            "custom_categories": project.custom_categories if project.coverage == "CUSTOM" else [],
            "application": _application(project, discovery), "user_requirements": requirements or project.test_data_notes,
            "discovery": build_digest(discovery, max_items=30), "allowed_test_types": allowed,
        }  # fmt: skip
        raw = self.agent.generate(payload, project_id=project.id, on_event=on_event)
        scenarios = self._clean(raw, {p.final_url or p.url for p in discovery.pages}, allowed if project.coverage == "CUSTOM" else None)
        if not scenarios:
            raise GenerationError("The model did not return usable scenarios. Add requirements or try again.")
        self.repo.save_scenarios(project.id, scenarios, replace=True)
        self.repo.audit(project.id, "agent:scenario", "scenarios.generated", "scenario", {"count": len(scenarios), "coverage": project.coverage})
        return scenarios

    @staticmethod
    def _clean(items: list[Scenario], known_pages: set[str], allowed_types: list[str] | None) -> list[Scenario]:
        taken: set[str] = set()
        seen: set[tuple[str, str]] = set()
        cleaned: list[Scenario] = []
        for item in items:
            key = (norm_title(item.module), norm_title(item.title))
            if not item.title or key in seen:
                continue
            if allowed_types is not None and item.test_type not in allowed_types:
                continue
            seen.add(key)
            sid = item.scenario_id if valid_id(item.scenario_id, "SC", taken) else next_id("SC", item.module, taken)
            taken.add(sid)
            page = item.page
            if page and page not in known_pages:
                matches = [p for p in known_pages if page.rstrip("/") and (p.rstrip("/").endswith(page.rstrip("/")) or page.rstrip("/").endswith(p.rstrip("/")))]
                page = matches[0] if matches else page
            cleaned.append(item.model_copy(update={"scenario_id": sid, "status": "draft", "source": "ai", "page": page}))
        return cleaned

    # ------------------------------------------------------------------ AI change requests
    def modify(self, project: Project, instruction: str, scope: list[str] | None = None, on_event: EventCallback | None = None) -> dict[str, Any]:
        """'Tell AI what you want to change': only the affected scenarios are touched."""
        if not instruction.strip():
            raise GenerationError("Describe the change you want.")
        current = self.repo.list_scenarios(project.id)
        discovery = self.repo.latest_successful_discovery(project.id)
        scoped = [s for s in current if not scope or s.scenario_id in scope]
        payload = {
            "instruction": instruction, "scenarios": [s.model_dump() for s in (scoped if scope else current)], "scope": scope or [],
            "application": _application(project, discovery) if discovery else {},
            "discovery": build_digest(discovery, max_items=20) if discovery else [],
        }  # fmt: skip
        change = self.agent.modify(payload, project_id=project.id, on_event=on_event)
        updated, summary = apply_changeset(current, change, Scenario, "scenario_id", "SC", scope)
        self.repo.save_scenarios(project.id, updated, replace=True)
        self.repo.audit(project.id, "agent:scenario", "scenarios.modified", "scenario", {k: v for k, v in summary.items() if k != "explanation"} | {"instruction": instruction[:200]})
        return summary

    # ------------------------------------------------------------------ manual review operations
    def approve(self, project_id: str, ids: list[str]) -> None:
        self.repo.set_scenario_status(project_id, ids, "approved")
        self.repo.audit(project_id, "user", "scenarios.approved", "scenario", {"ids": ids})

    def approve_all(self, project_id: str) -> int:
        ids = [s.scenario_id for s in self.repo.list_scenarios(project_id)]
        self.approve(project_id, ids)
        return len(ids)

    def unapprove(self, project_id: str, ids: list[str]) -> None:
        self.repo.set_scenario_status(project_id, ids, "draft")

    def delete(self, project_id: str, ids: list[str]) -> int:
        """Delete scenarios and their dependent test cases (traceability would otherwise be broken)."""
        dependent = [t.test_case_id for t in self.repo.list_test_cases(project_id) if t.scenario_id in ids]
        self.repo.delete_test_cases(project_id, dependent)
        self.repo.delete_scenarios(project_id, ids)
        self.repo.audit(project_id, "user", "scenarios.deleted", "scenario", {"ids": ids, "test_cases_removed": len(dependent)})
        return len(dependent)

    def edit(self, project_id: str, scenario: Scenario) -> None:
        """Save a manual edit. Edited scenarios must be approved again."""
        self.repo.save_scenarios(project_id, [scenario.model_copy(update={"status": "draft", "source": "manual"})])
        self.repo.audit(project_id, "user", "scenario.edited", "scenario", {"id": scenario.scenario_id})

    def add_manual(self, project: Project, **fields: Any) -> Scenario:
        existing = {s.scenario_id for s in self.repo.list_scenarios(project.id)}
        module = fields.get("module") or "General"
        scenario = Scenario.model_validate({**fields, "module": module, "scenario_id": next_id("SC", module, existing), "source": "manual", "status": "draft"})
        self.repo.save_scenarios(project.id, [scenario])
        self.repo.audit(project.id, "user", "scenario.added", "scenario", {"id": scenario.scenario_id})
        return scenario

