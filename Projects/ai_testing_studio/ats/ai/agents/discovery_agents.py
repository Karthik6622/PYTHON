"""Web Discovery Agent and Locator Intelligence Agent."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ats.ai.base import Agent, EventCallback
from ats.models import _Model


class DiscoveryInput(BaseModel):
    start_url: str
    description: str = ""
    pages: list[dict[str, Any]] = Field(default_factory=list)


class AppModule(_Model):
    name: str
    pages: list[str] = Field(default_factory=list)
    description: str = ""


class AppUnderstanding(_Model):
    summary: str = ""
    modules: list[AppModule] = Field(default_factory=list)
    workflows: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    requires_authentication: bool = False


class WebDiscoveryAgent(Agent):
    name = "web_discovery"
    thinking = False

    def analyze(
        self,
        start_url: str,
        description: str,
        digest: list[dict[str, Any]],
        screenshots: list[bytes] | None = None,
        project_id: str = "",
        on_event: EventCallback | None = None,
    ) -> AppUnderstanding:
        payload = {"start_url": start_url, "description": description, "pages": digest}
        return self.invoke(
            "discovery",
            payload,
            AppUnderstanding,
            input_model=DiscoveryInput,
            project_id=project_id,
            images=screenshots,
            on_event=on_event,
        )


class ElementIntent(_Model):
    element_key: str
    intent: str = ""
    fragile: bool = False
    note: str = ""


class LocatorEnrichment(_Model):
    elements: list[ElementIntent] = Field(default_factory=list)


class LocatorInput(BaseModel):
    elements: list[dict[str, Any]]


class LocatorIntelligenceAgent(Agent):
    name = "locator_intelligence"
    thinking = False

    def enrich(self, elements: list[dict[str, Any]], project_id: str = "") -> LocatorEnrichment:
        return self.invoke("locator", {"elements": elements}, LocatorEnrichment, input_model=LocatorInput, project_id=project_id)
