"""Report Agent and GitHub Agent."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ats.ai.base import Agent
from ats.models import DefectNarrative, _Model


class ExecutiveSummary(_Model):
    summary: str = ""
    highlights: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class SummaryInput(BaseModel):
    execution: dict[str, Any]
    totals: dict[str, int]
    failures: list[dict[str, Any]] = Field(default_factory=list)
    healings: list[dict[str, Any]] = Field(default_factory=list)


class DefectInput(BaseModel):
    test_case: dict[str, Any]
    environment: dict[str, Any]
    reproduction_steps: list[str]
    error_message: str
    analysis: dict[str, Any] = Field(default_factory=dict)
    console_evidence: list[str] = Field(default_factory=list)


class ReportAgent(Agent):
    name = "report"
    thinking = False
    temperature = 0.3

    def summarize(self, payload: dict[str, Any], project_id: str = "") -> ExecutiveSummary:
        return self.invoke("report.summary", payload, ExecutiveSummary, input_model=SummaryInput, project_id=project_id)

    def defect(self, payload: dict[str, Any], project_id: str = "") -> DefectNarrative:
        return self.invoke("report.defect", payload, DefectNarrative, input_model=DefectInput, project_id=project_id)


class GitText(_Model):
    branch_name: str = ""
    commit_title: str = ""
    commit_body: str = ""
    pr_title: str = ""
    pr_body: str = ""


class GitTextInput(BaseModel):
    kind: str
    project_name: str
    framework: str
    test_cases: list[dict[str, Any]] = Field(default_factory=list)
    changes: list[dict[str, Any]] = Field(default_factory=list)


class GitHubAgent(Agent):
    name = "github"
    thinking = False
    temperature = 0.3

    def describe(self, payload: dict[str, Any], project_id: str = "") -> GitText:
        return self.invoke("github.text", payload, GitText, input_model=GitTextInput, project_id=project_id)
