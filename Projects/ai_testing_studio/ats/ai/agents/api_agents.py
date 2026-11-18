"""API Scenario Agent and API Test Case Agent: design enterprise API tests from the imported endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ats.ai.base import Agent, EventCallback
from ats.models import ChangeSet, Scenario, TestCase, _Model


class ApiScenarioList(_Model):
    # An empty list is never a useful answer here; failing validation makes the agent ask the model again.
    scenarios: list[Scenario] = Field(min_length=1)


class ApiTestCaseList(_Model):
    __test__ = False

    test_cases: list[TestCase] = Field(min_length=1)


class ApiScenarioInput(BaseModel):
    application: dict[str, Any]
    base_url: str = ""
    coverage: str = "BASIC"
    coverage_guide: str = ""
    allowed_test_types: list[str] = Field(default_factory=list)
    endpoints: list[dict[str, Any]]
    connections: list[str] = Field(default_factory=list)  # NAMES only, never values
    user_requirements: str = ""


class ApiScenarioChangeInput(BaseModel):
    instruction: str
    scenarios: list[dict[str, Any]]
    scope: list[str] = Field(default_factory=list)
    endpoints: list[dict[str, Any]] = Field(default_factory=list)
    connections: list[str] = Field(default_factory=list)


class ApiTestCaseInput(BaseModel):
    __test__ = False

    scenarios: list[dict[str, Any]]
    endpoints: list[dict[str, Any]]
    connections: list[str] = Field(default_factory=list)
    base_url: str = ""
    user_requirements: str = ""
    existing_test_case_ids: list[str] = Field(default_factory=list)


class ApiTestCaseChangeInput(BaseModel):
    __test__ = False

    instruction: str
    test_cases: list[dict[str, Any]]
    scope: list[str] = Field(default_factory=list)
    approved_scenario_ids: list[str] = Field(default_factory=list)
    endpoints: list[dict[str, Any]] = Field(default_factory=list)
    connections: list[str] = Field(default_factory=list)


class ApiScenarioAgent(Agent):
    name = "api_scenario"
    thinking = True  # journeys, risks and coverage are planned before the scenarios are written

    def generate(self, payload: dict[str, Any], project_id: str = "", on_event: EventCallback | None = None) -> list[Scenario]:
        return self.invoke("api.scenarios", payload, ApiScenarioList, input_model=ApiScenarioInput, project_id=project_id, on_event=on_event).scenarios

    def modify(self, payload: dict[str, Any], project_id: str = "", on_event: EventCallback | None = None) -> ChangeSet:
        return self.invoke("api.scenarios.modify", payload, ChangeSet, input_model=ApiScenarioChangeInput, project_id=project_id, on_event=on_event)


class ApiTestCaseAgent(Agent):
    __test__ = False
    name = "api_test_case"
    thinking = True

    def generate(self, payload: dict[str, Any], project_id: str = "", on_event: EventCallback | None = None) -> list[TestCase]:
        return self.invoke("api.testcases", payload, ApiTestCaseList, input_model=ApiTestCaseInput, project_id=project_id, on_event=on_event).test_cases

    def modify(self, payload: dict[str, Any], project_id: str = "", on_event: EventCallback | None = None) -> ChangeSet:
        return self.invoke("api.testcases.modify", payload, ChangeSet, input_model=ApiTestCaseChangeInput, project_id=project_id, on_event=on_event)
