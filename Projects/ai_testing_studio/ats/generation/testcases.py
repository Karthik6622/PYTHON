"""Test case generation from APPROVED scenarios, review operations and AI change requests."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ats.ai.agents import TestCaseAgent
from ats.discovery.service import build_digest
from ats.errors import GenerationError
from ats.generation.common import apply_changeset, next_id, norm_title, valid_id
from ats.generation.scenarios import _application
from ats.models import Scenario, TestCase
from ats.repository import Project, Repository
from ats.security import mask

EventCallback = Callable[[str, str], None]
BATCH_SIZE = 5


class TestCaseService:
    __test__ = False

    def __init__(self, repo: Repository, agent: TestCaseAgent | None = None) -> None:
        self.repo = repo
        self.agent = agent or TestCaseAgent(repository=repo)

    def _elements_for(self, project_id: str, discovery: Any, scenarios: list[Scenario]) -> list[dict[str, Any]]:
        page_keys = {p.final_url or p.url: p.page_key for p in discovery.pages}
        wanted = {page_keys.get(s.page) for s in scenarios if s.page in page_keys}
        specs = [s for s in self.repo.list_locators(project_id) if not wanted or s.page_key in wanted]
        return [{"key": s.element_key, "page": s.page_key, "role": s.role or s.tag, "name": s.name, "intent": s.intent} for s in specs][:150]

    # ------------------------------------------------------------------ generation
    def generate(self, project: Project, requirements: str = "", on_event: EventCallback | None = None, progress: Callable[[str], None] | None = None) -> list[TestCase]:
        approved = self.repo.list_scenarios(project.id, status="approved")
        if not approved:
            raise GenerationError("Approve at least one scenario before generating test cases.")
        discovery = self.repo.latest_successful_discovery(project.id)
        if discovery is None:
            raise GenerationError("Run website discovery first.")
        collected: list[TestCase] = []
        taken: set[str] = set()
        known_scenarios = {s.scenario_id for s in approved}
        for start in range(0, len(approved), BATCH_SIZE):
            batch = approved[start : start + BATCH_SIZE]
            if progress:
                progress(f"Generating test cases for scenarios {start + 1}-{start + len(batch)} of {len(approved)}")
            payload = {
                "scenarios": [s.model_dump() for s in batch], "application": _application(project, discovery),
                "discovery": build_digest(discovery, max_items=25), "elements": self._elements_for(project.id, discovery, batch),
                "user_requirements": requirements or project.test_data_notes, "existing_test_case_ids": sorted(taken),
            }  # fmt: skip
            raw = self.agent.generate(payload, project_id=project.id, on_event=on_event)
            collected.extend(self._clean(raw, known_scenarios, taken, collected))
        if not collected:
            raise GenerationError("The model did not return usable test cases. Try again.")
        self.repo.save_test_cases(project.id, collected, replace=True)
        self.repo.audit(project.id, "agent:test_case", "testcases.generated", "test_case", {"count": len(collected), "scenarios": len(approved)})
        return collected

    @staticmethod
    def _clean(items: list[TestCase], scenario_ids: set[str], taken: set[str], already: list[TestCase]) -> list[TestCase]:
        seen = {(t.scenario_id, norm_title(t.title)) for t in already}
        out: list[TestCase] = []
        for item in items:
            if item.scenario_id not in scenario_ids or not item.title or not item.steps:
                continue
            key = (item.scenario_id, norm_title(item.title))
            if key in seen:
                continue
            seen.add(key)
            tid = item.test_case_id if valid_id(item.test_case_id, "TC", taken) else next_id("TC", item.module, taken)
            taken.add(tid)
            data = {k: mask(v) for k, v in item.test_data.items()}
            out.append(item.model_copy(update={"test_case_id": tid, "status": "draft", "source": "ai", "test_data": data}))
        return out

    # ------------------------------------------------------------------ AI change requests
    def modify(self, project: Project, instruction: str, scope: list[str] | None = None, on_event: EventCallback | None = None) -> dict[str, Any]:
        if not instruction.strip():
            raise GenerationError("Describe the change you want.")
        current = self.repo.list_test_cases(project.id)
        discovery = self.repo.latest_successful_discovery(project.id)
        approved_ids = [s.scenario_id for s in self.repo.list_scenarios(project.id, status="approved")]
        payload = {
            "instruction": instruction, "test_cases": [t.model_dump() for t in current if not scope or t.test_case_id in scope],
            "scope": scope or [], "approved_scenario_ids": approved_ids, "discovery": build_digest(discovery, 20) if discovery else [],
        }  # fmt: skip
        change = self.agent.modify(payload, project_id=project.id, on_event=on_event)
        change.add = [a for a in change.add if a.get("scenario_id") in approved_ids]
        updated, summary = apply_changeset(current, change, TestCase, "test_case_id", "TC", scope)
        self.repo.save_test_cases(project.id, updated, replace=True)
        self.repo.audit(project.id, "agent:test_case", "testcases.modified", "test_case", {k: v for k, v in summary.items() if k != "explanation"} | {"instruction": instruction[:200]})
        return summary

    # ------------------------------------------------------------------ manual review operations
    def approve(self, project_id: str, ids: list[str]) -> None:
        self.repo.set_test_case_status(project_id, ids, "approved")
        self.repo.audit(project_id, "user", "testcases.approved", "test_case", {"ids": ids})

    def approve_all(self, project_id: str) -> int:
        ids = [t.test_case_id for t in self.repo.list_test_cases(project_id)]
        self.approve(project_id, ids)
        return len(ids)

    def delete(self, project_id: str, ids: list[str]) -> None:
        self.repo.delete_test_cases(project_id, ids)
        self.repo.audit(project_id, "user", "testcases.deleted", "test_case", {"ids": ids})

    def edit(self, project_id: str, test_case: TestCase) -> None:
        self.repo.save_test_cases(project_id, [test_case.model_copy(update={"status": "draft", "source": "manual"})])
        self.repo.audit(project_id, "user", "testcase.edited", "test_case", {"id": test_case.test_case_id})

    def add_manual(self, project_id: str, **fields: Any) -> TestCase:
        existing = {t.test_case_id for t in self.repo.list_test_cases(project_id)}
        module = fields.get("module") or "General"
        case = TestCase.model_validate({**fields, "module": module, "test_case_id": next_id("TC", module, existing), "source": "manual", "status": "draft"})
        self.repo.save_test_cases(project_id, [case])
        self.repo.audit(project_id, "user", "testcase.added", "test_case", {"id": case.test_case_id})
        return case
