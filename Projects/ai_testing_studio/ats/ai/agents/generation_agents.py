"""Scenario Agent, Test Case Agent and Script Generation Agent."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ats.ai.base import Agent, EventCallback
from ats.models import AutomationPlan, ChangeSet, Scenario, TestCase, _Model


class ScenarioList(_Model):
    scenarios: list[Scenario] = Field(default_factory=list)


class TestCaseList(_Model):
    __test__ = False

    test_cases: list[TestCase] = Field(default_factory=list)


class ScenarioInput(BaseModel):
    coverage: str
    coverage_guide: str
    custom_categories: list[str] = Field(default_factory=list)
    application: dict[str, Any]
    user_requirements: str = ""
    discovery: list[dict[str, Any]] = Field(default_factory=list)
    allowed_test_types: list[str] = Field(default_factory=list)


class ScenarioChangeInput(BaseModel):
    instruction: str
    scenarios: list[dict[str, Any]]
    scope: list[str] = Field(default_factory=list)
    application: dict[str, Any] = Field(default_factory=dict)
    discovery: list[dict[str, Any]] = Field(default_factory=list)


class ScenarioAgent(Agent):
    name = "scenario"
    thinking = False

    def generate(self, payload: dict[str, Any], project_id: str = "", on_event: EventCallback | None = None) -> list[Scenario]:
        return self.invoke(
            "scenario.generate", payload, ScenarioList, input_model=ScenarioInput, project_id=project_id, on_event=on_event
        ).scenarios

    def modify(self, payload: dict[str, Any], project_id: str = "", on_event: EventCallback | None = None) -> ChangeSet:
        return self.invoke(
            "scenario.modify", payload, ChangeSet, input_model=ScenarioChangeInput, project_id=project_id, on_event=on_event
        )


class TestCaseInput(BaseModel):
    __test__ = False

    scenarios: list[dict[str, Any]]
    application: dict[str, Any]
    discovery: list[dict[str, Any]] = Field(default_factory=list)
    elements: list[dict[str, Any]] = Field(default_factory=list)
    user_requirements: str = ""
    existing_test_case_ids: list[str] = Field(default_factory=list)


class TestCaseChangeInput(BaseModel):
    __test__ = False

    instruction: str
    test_cases: list[dict[str, Any]]
    scope: list[str] = Field(default_factory=list)
    approved_scenario_ids: list[str] = Field(default_factory=list)
    discovery: list[dict[str, Any]] = Field(default_factory=list)


class TestCaseAgent(Agent):
    __test__ = False
    name = "test_case"
    thinking = False

    def generate(self, payload: dict[str, Any], project_id: str = "", on_event: EventCallback | None = None) -> list[TestCase]:
        return self.invoke(
            "testcase.generate", payload, TestCaseList, input_model=TestCaseInput, project_id=project_id, on_event=on_event
        ).test_cases

    def modify(self, payload: dict[str, Any], project_id: str = "", on_event: EventCallback | None = None) -> ChangeSet:
        return self.invoke(
            "testcase.modify", payload, ChangeSet, input_model=TestCaseChangeInput, project_id=project_id, on_event=on_event
        )


class ScriptPlanInput(BaseModel):
    base_url: str
    test_cases: list[dict[str, Any]]
    elements: list[dict[str, Any]]
    page_digest: list[dict[str, Any]] = Field(default_factory=list)
    allowed_actions: list[str] = Field(default_factory=list)


class FixedFile(_Model):
    content: str
    explanation: str = ""


class ScriptFixInput(BaseModel):
    path: str
    framework: str
    content: str
    instruction: str
    error_text: str = ""
    element_keys: list[str] = Field(default_factory=list)


class ScriptGenerationAgent(Agent):
    name = "script_generation"
    thinking = False
    temperature = 0.2

    def plan(self, payload: dict[str, Any], project_id: str = "", on_event: EventCallback | None = None) -> AutomationPlan:
        return self.invoke(
            "script.plan", payload, AutomationPlan, input_model=ScriptPlanInput, project_id=project_id, on_event=on_event
        )

    def fix(self, payload: dict[str, Any], project_id: str = "") -> FixedFile:
        return self.invoke("script.fix", payload, FixedFile, input_model=ScriptFixInput, project_id=project_id)
