"""Failure Analysis Agent and Self-Healing Agent."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ats.ai.base import Agent
from ats.models import FailureAnalysis, HealingProposal


class FailureInput(BaseModel):
    test_case: dict[str, Any]
    executed_steps: list[dict[str, Any]] = Field(default_factory=list)
    script_excerpt: str = ""
    error: dict[str, Any]
    logs: dict[str, Any] = Field(default_factory=dict)
    dom_excerpt: str = ""
    previous_locator: dict[str, Any] = Field(default_factory=dict)
    locator_candidates: list[dict[str, Any]] = Field(default_factory=list)
    rule_based_hint: dict[str, Any] = Field(default_factory=dict)


class FailureAnalysisAgent(Agent):
    name = "failure_analysis"
    thinking = True
    temperature = 0.2

    def analyze(self, payload: dict[str, Any], project_id: str = "", screenshot: bytes | None = None) -> FailureAnalysis:
        return self.invoke(
            "failure", payload, FailureAnalysis, input_model=FailureInput, project_id=project_id,
            images=[screenshot] if screenshot else None,
        )


class HealingInput(BaseModel):
    element_key: str
    intended_action: str = ""
    element_intent: str = ""
    old_locator: dict[str, Any]
    error: str = ""
    page_url: str = ""
    dom_excerpt: str = ""
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    previous_attempts: list[dict[str, Any]] = Field(default_factory=list)


class SelfHealingAgent(Agent):
    name = "self_healing"
    thinking = True
    temperature = 0.1

    def propose(self, payload: dict[str, Any], project_id: str = "", screenshot: bytes | None = None) -> HealingProposal:
        return self.invoke(
            "healing", payload, HealingProposal, input_model=HealingInput, project_id=project_id,
            images=[screenshot] if screenshot else None,
        )
