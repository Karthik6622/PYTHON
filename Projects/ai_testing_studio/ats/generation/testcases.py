"""Test case generation from APPROVED scenarios, review operations and AI change requests."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ats.ai.agents import ApiTestCaseAgent, MobileTestCaseAgent, TestCaseAgent
from ats.api import design as api_design
from ats.api.models import endpoint_digest as api_endpoint_digest
from ats.discovery.facts import facts_digest
from ats.discovery.service import build_digest
from ats.errors import GenerationError, ModelResponseError
from ats.generation.common import apply_changeset, next_id, norm_title, valid_id
from ats.generation.grounding import ground_cases
from ats.generation.scenarios import _application, page_names, resolve_page
from ats.logging_setup import get_logger
from ats.mobile import design as mobile_design
from ats.models import Scenario, TestCase
from ats.progress import report
from ats.repository import Project, Repository
from ats.security import mask

LOGGER = get_logger("generation.testcases")
EventCallback = Callable[[str, str], None]
BATCH_SIZE = 3  # scenarios per model request: small enough that the answer (several detailed test cases each) is never cut off
PARALLEL_REQUESTS = 3
API_BATCH_SIZE = 4
MOBILE_BATCH_SIZE = 4


class TestCaseService:
    __test__ = False

    def __init__(self, repo: Repository, agent: TestCaseAgent | None = None, api_agent: ApiTestCaseAgent | None = None, connections: Any = None, mobile_agent: MobileTestCaseAgent | None = None) -> None:
        self.repo = repo
        self.agent = agent or TestCaseAgent(repository=repo)
        self._api_agent = api_agent
        self._mobile_agent = mobile_agent
        self.connections = connections  # supplies the saved connection NAMES for API test design
        self.last_skipped: dict[str, list[str]] = {}  # project id -> scenarios the last generation could not design

    @property
    def api_agent(self) -> ApiTestCaseAgent:
        if self._api_agent is None:
            self._api_agent = ApiTestCaseAgent(repository=self.repo)
        return self._api_agent

    @property
    def mobile_agent(self) -> MobileTestCaseAgent:
        if self._mobile_agent is None:
            self._mobile_agent = MobileTestCaseAgent(repository=self.repo)
        return self._mobile_agent

    def _other_ids(self, project_id: str, layer: str) -> set[str]:
        """Ids used by the other layer of the project: new ids must not collide with them (one id space per project)."""
        return {t.test_case_id for t in self.repo.list_test_cases(project_id) if t.layer != layer}

    def _elements_for(self, project_id: str, discovery: Any, scenarios: list[Scenario]) -> list[dict[str, Any]]:
        wanted = self._views_of(scenarios, discovery)
        specs = [s for s in self.repo.list_locators(project_id) if not wanted or s.page_key in wanted]
        return [{"key": s.element_key, "page": s.page_key, "role": s.role or s.tag, "name": s.name, "intent": s.intent} for s in specs][:150]

    @staticmethod
    def _views_of(scenarios: list[Scenario], discovery: Any) -> set[str]:
        """The views a batch of scenarios is about (empty = no scenario names a known view: describe all of them)."""
        names = page_names(discovery)
        known = {p.page_key for p in discovery.pages}
        return {v for v in (resolve_page(s.page, known, names) for s in scenarios) if v in known}

    # ------------------------------------------------------------------ generation
    def generate(
        self, project: Project, requirements: str = "", on_event: EventCallback | None = None, progress: Callable[[str], None] | None = None, layer: str = "ui"
    ) -> list[TestCase]:
        if layer == "api":
            return self._generate_api(project, requirements, on_event, progress)
        if layer == "mobile":
            return self._generate_mobile(project, requirements, on_event, progress)
        approved = self.repo.list_scenarios(project.id, status="approved", layer="ui")
        if not approved:
            raise GenerationError("Approve at least one scenario before generating test cases.")
        discovery = self.repo.latest_successful_discovery(project.id)
        if discovery is None:
            raise GenerationError("Run website discovery first.")
        taken: set[str] = self._other_ids(project.id, "ui")
        known_scenarios = {s.scenario_id for s in approved}
        batches = [approved[i : i + BATCH_SIZE] for i in range(0, len(approved), BATCH_SIZE)]
        designed: dict[int, list[TestCase]] = {}
        skipped: list[str] = []
        done = 0

        def design(batch: list[Scenario]) -> list[TestCase]:
            """Ask for a batch; an answer that is cut off or unusable is asked for again in halves, down to one scenario."""
            payload = {
                "scenarios": [s.model_dump() for s in batch], "application": _application(project, discovery),
                "discovery": facts_digest(discovery, only=self._views_of(batch, discovery), max_controls=40),
                "elements": self._elements_for(project.id, discovery, batch),
                "user_requirements": requirements or project.test_data_notes, "existing_test_case_ids": sorted(taken),
            }  # fmt: skip
            try:
                cases, partial = self.agent.design(payload, project_id=project.id, on_event=on_event)
            except ModelResponseError as exc:
                if len(batch) == 1:
                    LOGGER.warning("No test cases for %s: %s", batch[0].scenario_id, exc.user_message)
                    skipped.append(batch[0].scenario_id)
                    return []
                half = len(batch) // 2
                return design(batch[:half]) + design(batch[half:])
            if partial and cases and len(batch) > 1:  # the answer stopped inside its last scenario: that one is asked for again
                last = cases[-1].scenario_id
                cases = [c for c in cases if c.scenario_id != last]
            covered = {c.scenario_id for c in cases}
            missing = [s for s in batch if s.scenario_id not in covered]
            if not missing:
                return cases
            if len(batch) == 1:
                skipped.append(batch[0].scenario_id)
                return cases
            for scenario in missing:  # what the answer left out (or lost when it was cut off) is asked for on its own
                cases += design([scenario])
            return cases

        def run(index: int) -> None:
            nonlocal done
            designed[index] = design(batches[index])
            done += 1
            report(progress, f"Designed test cases for {min(done * BATCH_SIZE, len(approved))} of {len(approved)} scenarios", 0.02 + 0.93 * done / len(batches))

        report(progress, f"Designing test cases for {len(approved)} scenarios ({len(batches)} request(s), {PARALLEL_REQUESTS} at a time)", 0.02)
        with ThreadPoolExecutor(max_workers=PARALLEL_REQUESTS) as pool:  # independent model calls
            list(pool.map(run, range(len(batches))))
        collected: list[TestCase] = []
        for index in range(len(batches)):  # ids are assigned in scenario order, whatever order the answers came back in
            collected.extend(self._clean(designed.get(index, []), known_scenarios, taken, collected))
        collected, grounding = ground_cases(collected, approved, discovery, {s.element_key: s for s in self.repo.list_locators(project.id)})
        LOGGER.info("Grounded %s test cases: %s text(s) corrected, %s unverified, %s without a view", len(collected), grounding.corrected, grounding.unverified, grounding.unresolved_view)
        self.last_skipped[project.id] = sorted(set(skipped))
        report(progress, "Saving the test cases", 0.97)
        if not collected:
            raise GenerationError("The model did not return usable test cases. Try again.")
        self.repo.save_test_cases(project.id, collected, replace=True, layer="ui")
        self.repo.audit(project.id, "agent:test_case", "testcases.generated", "test_case", {"count": len(collected), "scenarios": len(approved), "skipped": sorted(set(skipped))})
        return collected

    def _generate_api(self, project: Project, requirements: str, on_event: EventCallback | None, progress: Any) -> list[TestCase]:
        approved = self.repo.list_scenarios(project.id, status="approved", layer="api")
        if not approved:
            raise GenerationError("Approve at least one API scenario before generating API test cases.")
        endpoints = self.repo.list_api_endpoints(project.id)
        if not endpoints:
            raise GenerationError("There are no API endpoints. Import a definition on the API page first.")
        names = self.connections.names(project.id) if self.connections is not None else []
        collected: list[TestCase] = []
        rejected: list[str] = []
        taken = self._other_ids(project.id, "api")
        known = {s.scenario_id for s in approved}
        batches = -(-len(approved) // API_BATCH_SIZE)
        for number, start in enumerate(range(0, len(approved), API_BATCH_SIZE)):
            batch = approved[start : start + API_BATCH_SIZE]
            report(
                progress, f"Designing API test cases for scenarios {start + 1}-{start + len(batch)} of {len(approved)}",
                0.02 + 0.93 * number / batches, 0.02 + 0.93 * (number + 1) / batches,
            )
            payload = api_design.testcase_payload(project, batch, api_design.endpoints_for(batch, endpoints), names, requirements, taken)
            raw = self.api_agent.generate(payload, project_id=project.id, on_event=on_event)
            collected += api_design.clean_testcases(raw, known, taken, collected, endpoints, names, rejected)
        report(progress, "Saving the API test cases", 0.97)
        if not collected:
            raise GenerationError("The model did not return usable API test cases" + (f" ({rejected[0]})" if rejected else "") + ". Try again.")
        self.repo.save_test_cases(project.id, collected, replace=True, layer="api")
        self.repo.audit(project.id, "agent:api_test_case", "testcases.generated", "test_case", {"count": len(collected), "scenarios": len(approved), "layer": "api", "rejected": len(rejected)})
        return collected

    def _generate_mobile(self, project: Project, requirements: str, on_event: EventCallback | None, progress: Any) -> list[TestCase]:
        approved = self.repo.list_scenarios(project.id, status="approved", layer="mobile")
        if not approved:
            raise GenerationError("Approve at least one mobile scenario before generating mobile test cases.")
        analysis = self.repo.get_mobile_analysis(project.id)
        if analysis is None:
            raise GenerationError("Analyze the app on the Mobile page first.")
        config = self.repo.get_mobile_config(project.id)
        collected: list[TestCase] = []
        taken = self._other_ids(project.id, "mobile")
        known = {s.scenario_id for s in approved}
        batches = -(-len(approved) // MOBILE_BATCH_SIZE)
        for number, start in enumerate(range(0, len(approved), MOBILE_BATCH_SIZE)):
            batch = approved[start : start + MOBILE_BATCH_SIZE]
            report(
                progress, f"Designing mobile test cases for scenarios {start + 1}-{start + len(batch)} of {len(approved)}",
                0.02 + 0.93 * number / batches, 0.02 + 0.93 * (number + 1) / batches,
            )
            payload = mobile_design.testcase_payload(project, config, analysis, batch, requirements, taken)
            raw = self.mobile_agent.generate(payload, project_id=project.id, on_event=on_event)
            collected += mobile_design.clean_testcases(raw, known, taken, collected)
        report(progress, "Saving the mobile test cases", 0.97)
        if not collected:
            raise GenerationError("The model did not return usable mobile test cases. Try again.")
        self.repo.save_test_cases(project.id, collected, replace=True, layer="mobile")
        self.repo.audit(project.id, "agent:mobile_test_case", "testcases.generated", "test_case", {"count": len(collected), "scenarios": len(approved), "layer": "mobile"})
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
            out.append(item.model_copy(update={"test_case_id": tid, "status": "draft", "source": "ai", "test_data": data, "layer": "ui", "api": None}))
        return out

    # ------------------------------------------------------------------ AI change requests
    def modify(self, project: Project, instruction: str, scope: list[str] | None = None, on_event: EventCallback | None = None, progress: Any = None, layer: str = "ui") -> dict[str, Any]:
        if not instruction.strip():
            raise GenerationError("Describe the change you want.")
        current = self.repo.list_test_cases(project.id, layer=layer)
        approved_ids = [s.scenario_id for s in self.repo.list_scenarios(project.id, status="approved", layer=layer)]
        if layer == "api":
            return self._modify_api(project, instruction, current, scope, approved_ids, on_event, progress)
        if layer == "mobile":
            return self._modify_mobile(project, instruction, current, scope, approved_ids, on_event, progress)
        discovery = self.repo.latest_successful_discovery(project.id)
        payload = {
            "instruction": instruction, "test_cases": [t.model_dump() for t in current if not scope or t.test_case_id in scope],
            "scope": scope or [], "approved_scenario_ids": approved_ids, "discovery": build_digest(discovery, 20) if discovery else [],
        }  # fmt: skip
        report(progress, "Applying your change request", 0.05, 0.9)
        change = self.agent.modify(payload, project_id=project.id, on_event=on_event)
        change.add = [a for a in change.add if a.get("scenario_id") in approved_ids]
        updated, summary = apply_changeset(current, change, TestCase, "test_case_id", "TC", scope, reserved=self._other_ids(project.id, "ui"))
        self.repo.save_test_cases(project.id, updated, replace=True, layer="ui")
        self.repo.audit(project.id, "agent:test_case", "testcases.modified", "test_case", {k: v for k, v in summary.items() if k != "explanation"} | {"instruction": instruction[:200]})
        return summary

    def _modify_api(self, project: Project, instruction: str, current: list[TestCase], scope: list[str] | None, approved_ids: list[str], on_event: EventCallback | None, progress: Any) -> dict[str, Any]:
        endpoints = self.repo.list_api_endpoints(project.id)
        names = self.connections.names(project.id) if self.connections is not None else []
        payload = {
            "instruction": instruction, "test_cases": [t.model_dump(by_alias=True) for t in current if not scope or t.test_case_id in scope], "scope": scope or [],
            "approved_scenario_ids": approved_ids, "endpoints": api_endpoint_digest(endpoints, 30), "connections": names,
        }  # fmt: skip
        report(progress, "Applying your change request", 0.05, 0.9)
        change = self.api_agent.modify(payload, project_id=project.id, on_event=on_event)
        change.add = [{**a, "layer": "api"} for a in change.add if a.get("scenario_id") in approved_ids]
        change.update = [{**u, "layer": "api"} for u in change.update]
        updated, summary = apply_changeset(current, change, TestCase, "test_case_id", "TC", scope, reserved=self._other_ids(project.id, "api"), new_id=api_design.next_api_id)
        before = {t.test_case_id: t for t in current}
        final: list[TestCase] = []
        for case in updated:
            changed = case.test_case_id in summary["added"] or case.test_case_id in summary["updated"]
            if changed:
                checked, reason = api_design.validate_requests(case, endpoints, names)
                if checked is None:  # an invalid edit is refused: keep the previous version, drop a refused new case
                    summary["skipped"].append(f"{case.test_case_id}: {reason}")
                    for key in ("added", "updated"):
                        summary[key] = [i for i in summary[key] if i != case.test_case_id]
                    if case.test_case_id in before:
                        final.append(before[case.test_case_id])
                    continue
                case = checked
            final.append(case.model_copy(update={"layer": "api"}))
        self.repo.save_test_cases(project.id, final, replace=True, layer="api")
        self.repo.audit(project.id, "agent:api_test_case", "testcases.modified", "test_case", {k: v for k, v in summary.items() if k != "explanation"} | {"instruction": instruction[:200], "layer": "api"})
        return summary

    def _modify_mobile(self, project: Project, instruction: str, current: list[TestCase], scope: list[str] | None, approved_ids: list[str], on_event: EventCallback | None, progress: Any) -> dict[str, Any]:
        analysis = self.repo.get_mobile_analysis(project.id)
        chosen = [t for t in current if not scope or t.test_case_id in scope]
        payload = {
            "instruction": instruction, "test_cases": [t.model_dump() for t in chosen], "scope": scope or [], "approved_scenario_ids": approved_ids,
            "screens": mobile_design.screens_digest(analysis, {t.related_page for t in chosen}) if analysis else [],
        }  # fmt: skip
        report(progress, "Applying your change request", 0.05, 0.9)
        change = self.mobile_agent.modify(payload, project_id=project.id, on_event=on_event)
        change.add = [{**a, "layer": "mobile"} for a in change.add if a.get("scenario_id") in approved_ids]
        change.update = [{**u, "layer": "mobile"} for u in change.update]
        updated, summary = apply_changeset(current, change, TestCase, "test_case_id", "TC", scope, reserved=self._other_ids(project.id, "mobile"), new_id=mobile_design.next_mobile_id)
        changed = set(summary["added"]) | set(summary["updated"])
        final = [
            c.model_copy(update={"layer": "mobile", "test_data": mobile_design.guard_credentials(c.test_data, mobile_design.is_negative(c))}) if c.test_case_id in changed else c.model_copy(update={"layer": "mobile"})
            for c in updated
        ]  # fmt: skip
        self.repo.save_test_cases(project.id, final, replace=True, layer="mobile")
        self.repo.audit(project.id, "agent:mobile_test_case", "testcases.modified", "test_case", {k: v for k, v in summary.items() if k != "explanation"} | {"instruction": instruction[:200], "layer": "mobile"})
        return summary

    # ------------------------------------------------------------------ manual review operations
    def approve(self, project_id: str, ids: list[str]) -> None:
        self.repo.set_test_case_status(project_id, ids, "approved")
        self.repo.audit(project_id, "user", "testcases.approved", "test_case", {"ids": ids})

    def approve_all(self, project_id: str, layer: str | None = None) -> int:
        ids = [t.test_case_id for t in self.repo.list_test_cases(project_id, layer=layer)]
        self.approve(project_id, ids)
        return len(ids)

    def delete(self, project_id: str, ids: list[str]) -> None:
        self.repo.delete_test_cases(project_id, ids)
        self.repo.audit(project_id, "user", "testcases.deleted", "test_case", {"ids": ids})

    def edit(self, project_id: str, test_case: TestCase) -> None:
        self.repo.save_test_cases(project_id, [test_case.model_copy(update={"status": "draft", "source": "manual"})])
        self.repo.audit(project_id, "user", "testcase.edited", "test_case", {"id": test_case.test_case_id})

    def add_manual(self, project_id: str, layer: str = "ui", **fields: Any) -> TestCase:
        existing = {t.test_case_id for t in self.repo.list_test_cases(project_id)}
        module = fields.get("module") or "General"
        new_id = {"api": api_design.next_api_id, "mobile": mobile_design.next_mobile_id}.get(layer, next_id)("TC", module, existing)
        case = TestCase.model_validate({**fields, "module": module, "test_case_id": new_id, "source": "manual", "status": "draft", "layer": layer})
        self.repo.save_test_cases(project_id, [case])
        self.repo.audit(project_id, "user", "testcase.added", "test_case", {"id": case.test_case_id})
        return case
