"""Mobile Scenario Agent, Mobile Test Case Agent and Mobile Script Agent: design and plan Android tests from the analysed screens."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ats.ai.base import Agent, EventCallback
from ats.mobile.models import MobilePlan
from ats.models import ChangeSet, Scenario, TestCase, _Model


class MobileScenarioList(_Model):
    scenarios: list[Scenario] = Field(min_length=1)  # an empty answer is never useful: failing validation makes the agent ask again


class MobileTestCaseList(_Model):
    __test__ = False

    test_cases: list[TestCase] = Field(min_length=1)


class MobileScenarioInput(BaseModel):
    application: dict[str, Any]
    coverage: str = "BASIC"
    coverage_guide: str = ""
    allowed_test_types: list[str] = Field(default_factory=list)
    screens: list[dict[str, Any]]
    user_requirements: str = ""


class MobileScenarioChangeInput(BaseModel):
    instruction: str
    scenarios: list[dict[str, Any]]
    scope: list[str] = Field(default_factory=list)
    screens: list[dict[str, Any]] = Field(default_factory=list)


class MobileTestCaseInput(BaseModel):
    __test__ = False

    scenarios: list[dict[str, Any]]
    screens: list[dict[str, Any]]
    application: dict[str, Any] = Field(default_factory=dict)
    user_requirements: str = ""
    existing_test_case_ids: list[str] = Field(default_factory=list)


class MobileTestCaseChangeInput(BaseModel):
    __test__ = False

    instruction: str
    test_cases: list[dict[str, Any]]
    scope: list[str] = Field(default_factory=list)
    approved_scenario_ids: list[str] = Field(default_factory=list)
    screens: list[dict[str, Any]] = Field(default_factory=list)


class MobileScriptInput(BaseModel):
    application: dict[str, Any] = Field(default_factory=dict)
    test_cases: list[dict[str, Any]]
    elements: list[dict[str, Any]]
    allowed_actions: list[str] = Field(default_factory=list)


class MobileScenarioAgent(Agent):
    name = "mobile_scenario"
    thinking = True  # journeys, risks and coverage are planned before the scenarios are written

    def generate(self, payload: dict[str, Any], project_id: str = "", on_event: EventCallback | None = None) -> list[Scenario]:
        return self.invoke("mobile.scenarios", payload, MobileScenarioList, input_model=MobileScenarioInput, project_id=project_id, on_event=on_event).scenarios

    def modify(self, payload: dict[str, Any], project_id: str = "", on_event: EventCallback | None = None) -> ChangeSet:
        return self.invoke("mobile.scenarios.modify", payload, ChangeSet, input_model=MobileScenarioChangeInput, project_id=project_id, on_event=on_event)


class MobileTestCaseAgent(Agent):
    __test__ = False
    name = "mobile_test_case"
    thinking = True

    def generate(self, payload: dict[str, Any], project_id: str = "", on_event: EventCallback | None = None) -> list[TestCase]:
        return self.invoke("mobile.testcases", payload, MobileTestCaseList, input_model=MobileTestCaseInput, project_id=project_id, on_event=on_event).test_cases

    def modify(self, payload: dict[str, Any], project_id: str = "", on_event: EventCallback | None = None) -> ChangeSet:
        return self.invoke("mobile.testcases.modify", payload, ChangeSet, input_model=MobileTestCaseChangeInput, project_id=project_id, on_event=on_event)


class MobileScriptAgent(Agent):
    name = "mobile_script"
    thinking = False
    temperature = 0.2

    def plan(self, payload: dict[str, Any], project_id: str = "", on_event: EventCallback | None = None) -> MobilePlan:
        return self.invoke("mobile.script.plan", payload, MobilePlan, input_model=MobileScriptInput, project_id=project_id, on_event=on_event)
