"""Scenario generation, review operations (approve / edit / delete / regenerate / add) and AI change requests."""

from __future__ import annotations

import difflib
from collections.abc import Callable
from typing import Any

from ats.ai.agents import ApiScenarioAgent, MobileScenarioAgent, ScenarioAgent
from ats.api import design as api_design
from ats.api.models import endpoint_digest as api_endpoint_digest
from ats.discovery.facts import facts_digest
from ats.discovery.service import build_digest
from ats.errors import GenerationError
from ats.generation.common import apply_changeset, next_id, norm_title, valid_id
from ats.mobile import design as mobile_design
from ats.models import COVERAGE_GUIDE, TEST_TYPES, Scenario
from ats.progress import report
from ats.repository import Project, Repository

EventCallback = Callable[[str, str], None]


def resolve_page(page: str, known: set[str], names: dict[str, str] | None = None) -> str:
    """The page_key a model-written page reference means: exact key, a url, or the name / heading of a view. Unknown stays as written."""
    if not page or page in known:
        return page
    names = names or {}
    lowered = page.strip().lower()
    if lowered in names:
        return names[lowered]
    tail = page.rstrip("/")
    matches = [p for p in known if tail and (p.rstrip("/").endswith(tail) or tail.endswith(p.rstrip("/")))]
    if matches:
        return matches[0]
    close = difflib.get_close_matches(lowered, list(names), n=1, cutoff=0.8)
    return names[close[0]] if close else page


def page_names(discovery: Any) -> dict[str, str]:
    """``{lower-cased view name / heading / page key: page_key}`` for resolving references written by a model."""
    names: dict[str, str] = {}
    for p in discovery.pages:
        for label in (p.page_key, p.view_name, p.title, *[h.split(": ", 1)[-1] for h in p.headings[:2]]):
            if label and label.strip().lower() not in names:
                names[label.strip().lower()] = p.page_key
    return names


def _application(project: Project, discovery: Any) -> dict[str, Any]:
    app = {
        "name": project.name, "url": project.url, "environment": project.environment, "description": project.description,
        "summary": discovery.summary, "modules": discovery.analysis.get("modules", []), "workflows": discovery.analysis.get("workflows", []),
    }  # fmt: skip
    if project.auth.mode in ("env_credentials", "login_workflow"):
        # The exact placeholders for the configured test account, so every test case refers to the same variables.
        app["test_account"] = {"username": f"{{{{env:{project.auth.username_env}}}}}", "password": f"{{{{env:{project.auth.password_env}}}}}"}
    return app


class ScenarioService:
    def __init__(self, repo: Repository, agent: ScenarioAgent | None = None, api_agent: ApiScenarioAgent | None = None, connections: Any = None, mobile_agent: MobileScenarioAgent | None = None) -> None:
        self.repo = repo
        self.agent = agent or ScenarioAgent(repository=repo)
        self._api_agent = api_agent
        self._mobile_agent = mobile_agent
        self.connections = connections  # supplies the saved connection NAMES for API scenario design

    @property
    def api_agent(self) -> ApiScenarioAgent:
        if self._api_agent is None:
            self._api_agent = ApiScenarioAgent(repository=self.repo)
        return self._api_agent

    @property
    def mobile_agent(self) -> MobileScenarioAgent:
        if self._mobile_agent is None:
            self._mobile_agent = MobileScenarioAgent(repository=self.repo)
        return self._mobile_agent

    def _other_ids(self, project_id: str, layer: str) -> set[str]:
        """Ids used by the other layer of the project: new ids must not collide with them (one id space per project)."""
        return {s.scenario_id for s in self.repo.list_scenarios(project_id) if s.layer != layer}

    # ------------------------------------------------------------------ generation
    def generate(self, project: Project, requirements: str = "", on_event: EventCallback | None = None, progress: Any = None, layer: str = "ui") -> list[Scenario]:
        """Generate scenarios for the latest discovery (UI) or the imported endpoints (API). Replaces that layer's scenarios (they must be reviewed again)."""
        if layer == "api":
            return self._generate_api(project, requirements, on_event, progress)
        if layer == "mobile":
            return self._generate_mobile(project, requirements, on_event, progress)
        discovery = self.repo.latest_successful_discovery(project.id)
        if discovery is None:
            raise GenerationError("Run website discovery before generating scenarios.")
        allowed = project.custom_categories if project.coverage == "CUSTOM" and project.custom_categories else TEST_TYPES
        payload = {
            "coverage": project.coverage, "coverage_guide": COVERAGE_GUIDE.get(project.coverage, ""),
            "custom_categories": project.custom_categories if project.coverage == "CUSTOM" else [],
            "application": _application(project, discovery), "user_requirements": requirements or project.test_data_notes,
            "discovery": facts_digest(discovery, max_controls=25), "allowed_test_types": allowed,
        }  # fmt: skip
        report(progress, "Designing enterprise-level scenarios for every discovered view", 0.05, 0.9)
        raw = self.agent.generate(payload, project_id=project.id, on_event=on_event)
        report(progress, "Checking and saving the scenarios", 0.95)
        known = {p.page_key for p in discovery.pages} | {p.final_url or p.url for p in discovery.pages}
        scenarios = self._clean(raw, known, allowed if project.coverage == "CUSTOM" else None, self._other_ids(project.id, "ui"), page_names(discovery))
        if not scenarios:
            raise GenerationError("The model did not return usable scenarios. Add requirements or try again.")
        self.repo.save_scenarios(project.id, scenarios, replace=True, layer="ui")
        self.repo.audit(project.id, "agent:scenario", "scenarios.generated", "scenario", {"count": len(scenarios), "coverage": project.coverage})
        return scenarios

    def _generate_api(self, project: Project, requirements: str, on_event: EventCallback | None, progress: Any) -> list[Scenario]:
        endpoints = self.repo.list_api_endpoints(project.id)
        if not endpoints:
            raise GenerationError("Import an API definition (or add endpoints) on the API page before generating API scenarios.")
        names = self.connections.names(project.id) if self.connections is not None else []
        allowed = api_design.allowed_types(project)
        chunks = api_design.endpoint_chunks(endpoints)
        taken = self._other_ids(project.id, "api")
        collected: list[Scenario] = []
        for number, chunk in enumerate(chunks):
            report(
                progress, f"Designing API scenarios for {len(chunk)} endpoint(s) ({number + 1} of {len(chunks)})",
                0.03 + 0.9 * number / len(chunks), 0.03 + 0.9 * (number + 1) / len(chunks),
            )
            payload = api_design.scenario_payload(project, chunk, names, requirements, allowed)
            raw = self.api_agent.generate(payload, project_id=project.id, on_event=on_event)
            collected += api_design.clean_scenarios(raw, endpoints, taken, allowed if project.coverage == "CUSTOM" else None, collected)
        report(progress, "Saving the API scenarios", 0.96)
        if not collected:
            raise GenerationError("The model did not return usable API scenarios. Add requirements or try again.")
        self.repo.save_scenarios(project.id, collected, replace=True, layer="api")
        self.repo.audit(project.id, "agent:api_scenario", "scenarios.generated", "scenario", {"count": len(collected), "layer": "api", "endpoints": len(endpoints)})
        return collected

    def _generate_mobile(self, project: Project, requirements: str, on_event: EventCallback | None, progress: Any) -> list[Scenario]:
        analysis = self.repo.get_mobile_analysis(project.id)
        if analysis is None:
            raise GenerationError("Analyze the app on the Mobile page before generating mobile scenarios.")
        allowed = mobile_design.allowed_types(project)
        payload = mobile_design.scenario_payload(project, self.repo.get_mobile_config(project.id), analysis, requirements, allowed)
        report(progress, "Designing enterprise-level mobile scenarios for every analysed screen", 0.05, 0.9)
        raw = self.mobile_agent.generate(payload, project_id=project.id, on_event=on_event)
        report(progress, "Checking and saving the mobile scenarios", 0.95)
        scenarios = mobile_design.clean_scenarios(raw, {s.screen_key for s in analysis.screens}, self._other_ids(project.id, "mobile"), allowed if project.coverage == "CUSTOM" else None, [])
        if not scenarios:
            raise GenerationError("The model did not return usable mobile scenarios. Add requirements or try again.")
        self.repo.save_scenarios(project.id, scenarios, replace=True, layer="mobile")
        self.repo.audit(project.id, "agent:mobile_scenario", "scenarios.generated", "scenario", {"count": len(scenarios), "layer": "mobile", "screens": len(analysis.screens)})
        return scenarios

    @staticmethod
    def _clean(items: list[Scenario], known_pages: set[str], allowed_types: list[str] | None, reserved: set[str] | None = None, names: dict[str, str] | None = None) -> list[Scenario]:
        taken: set[str] = set(reserved or ())
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
            page = resolve_page(item.page, known_pages, names)
            cleaned.append(item.model_copy(update={"scenario_id": sid, "status": "draft", "source": "ai", "page": page, "layer": "ui"}))
        return cleaned

    # ------------------------------------------------------------------ AI change requests
    def modify(self, project: Project, instruction: str, scope: list[str] | None = None, on_event: EventCallback | None = None, progress: Any = None, layer: str = "ui") -> dict[str, Any]:
        """'Tell AI what you want to change': only the affected scenarios are touched."""
        if not instruction.strip():
            raise GenerationError("Describe the change you want.")
        current = self.repo.list_scenarios(project.id, layer=layer)
        if layer == "api":
            return self._modify_api(project, instruction, current, scope, on_event, progress)
        if layer == "mobile":
            return self._modify_mobile(project, instruction, current, scope, on_event, progress)
        discovery = self.repo.latest_successful_discovery(project.id)
        scoped = [s for s in current if not scope or s.scenario_id in scope]
        payload = {
            "instruction": instruction, "scenarios": [s.model_dump() for s in (scoped if scope else current)], "scope": scope or [],
            "application": _application(project, discovery) if discovery else {},
            "discovery": build_digest(discovery, max_items=20) if discovery else [],
        }  # fmt: skip
        report(progress, "Applying your change request", 0.05, 0.9)
        change = self.agent.modify(payload, project_id=project.id, on_event=on_event)
        updated, summary = apply_changeset(current, change, Scenario, "scenario_id", "SC", scope, reserved=self._other_ids(project.id, "ui"))
        self.repo.save_scenarios(project.id, updated, replace=True, layer="ui")
        self.repo.audit(project.id, "agent:scenario", "scenarios.modified", "scenario", {k: v for k, v in summary.items() if k != "explanation"} | {"instruction": instruction[:200]})
        return summary

    def _modify_api(self, project: Project, instruction: str, current: list[Scenario], scope: list[str] | None, on_event: EventCallback | None, progress: Any) -> dict[str, Any]:
        endpoints = self.repo.list_api_endpoints(project.id)
        names = self.connections.names(project.id) if self.connections is not None else []
        scoped = [s for s in current if not scope or s.scenario_id in scope]
        payload = {
            "instruction": instruction, "scenarios": [s.model_dump() for s in scoped], "scope": scope or [],
            "endpoints": api_endpoint_digest(endpoints, 30), "connections": names,
        }  # fmt: skip
        report(progress, "Applying your change request", 0.05, 0.9)
        change = self.api_agent.modify(payload, project_id=project.id, on_event=on_event)
        updated, summary = apply_changeset(current, change, Scenario, "scenario_id", "SC", scope, reserved=self._other_ids(project.id, "api"), new_id=api_design.next_api_id)
        updated = [s.model_copy(update={"layer": "api"}) for s in updated]
        self.repo.save_scenarios(project.id, updated, replace=True, layer="api")
        self.repo.audit(project.id, "agent:api_scenario", "scenarios.modified", "scenario", {k: v for k, v in summary.items() if k != "explanation"} | {"instruction": instruction[:200], "layer": "api"})
        return summary

    def _modify_mobile(self, project: Project, instruction: str, current: list[Scenario], scope: list[str] | None, on_event: EventCallback | None, progress: Any) -> dict[str, Any]:
        analysis = self.repo.get_mobile_analysis(project.id)
        scoped = [s for s in current if not scope or s.scenario_id in scope]
        payload = {
            "instruction": instruction, "scenarios": [s.model_dump() for s in scoped], "scope": scope or [],
            "screens": mobile_design.screens_digest(analysis, {s.page for s in scoped}) if analysis else [],
        }  # fmt: skip
        report(progress, "Applying your change request", 0.05, 0.9)
        change = self.mobile_agent.modify(payload, project_id=project.id, on_event=on_event)
        updated, summary = apply_changeset(current, change, Scenario, "scenario_id", "SC", scope, reserved=self._other_ids(project.id, "mobile"), new_id=mobile_design.next_mobile_id)
        updated = [s.model_copy(update={"layer": "mobile"}) for s in updated]
        self.repo.save_scenarios(project.id, updated, replace=True, layer="mobile")
        self.repo.audit(project.id, "agent:mobile_scenario", "scenarios.modified", "scenario", {k: v for k, v in summary.items() if k != "explanation"} | {"instruction": instruction[:200], "layer": "mobile"})
        return summary

    # ------------------------------------------------------------------ manual review operations
    def approve(self, project_id: str, ids: list[str]) -> None:
        self.repo.set_scenario_status(project_id, ids, "approved")
        self.repo.audit(project_id, "user", "scenarios.approved", "scenario", {"ids": ids})

    def approve_all(self, project_id: str, layer: str | None = None) -> int:
        ids = [s.scenario_id for s in self.repo.list_scenarios(project_id, layer=layer)]
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

    def add_manual(self, project: Project, layer: str = "ui", **fields: Any) -> Scenario:
        existing = {s.scenario_id for s in self.repo.list_scenarios(project.id)}
        module = fields.get("module") or "General"
        new_id = {"api": api_design.next_api_id, "mobile": mobile_design.next_mobile_id}.get(layer, next_id)("SC", module, existing)
        scenario = Scenario.model_validate({**fields, "module": module, "scenario_id": new_id, "source": "manual", "status": "draft", "layer": layer})
        self.repo.save_scenarios(project.id, [scenario])
        self.repo.audit(project.id, "user", "scenario.added", "scenario", {"id": scenario.scenario_id})
        return scenario

