"""Web Discovery Agent and Locator Intelligence Agent."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

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


AUTH_KIND_ALIASES = {
    "password": "ui_account", "username_password": "ui_account", "login": "ui_account", "account": "ui_account", "apikey": "api_key",
    "key": "api_key", "token": "bearer", "access_token": "bearer", "basic_auth": "basic", "oauth": "oauth2", "client_credentials": "oauth2",
}  # fmt: skip


class AuthRequirement(_Model):
    kind: Literal["ui_account", "basic", "bearer", "api_key", "oauth2", "custom"]
    where: str = ""
    evidence: str = ""
    confidence: Literal["high", "medium", "low"] = "medium"

    @field_validator("kind", mode="before")
    @classmethod
    def _kind(cls, value: Any) -> str:
        text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
        known = {"ui_account", "basic", "bearer", "api_key", "oauth2", "custom"}
        return AUTH_KIND_ALIASES.get(text, text if text in known else "custom")

    @field_validator("confidence", mode="before")
    @classmethod
    def _confidence(cls, value: Any) -> str:
        text = str(value or "").strip().lower()
        return text if text in {"high", "medium", "low"} else "medium"


class AuthRequirementCheck(_Model):
    requires_authentication: bool = False
    summary: str = ""
    requirements: list[AuthRequirement] = Field(default_factory=list)

    @field_validator("requirements", mode="before")
    @classmethod
    def _items(cls, value: Any) -> list[Any]:
        return [item for item in value if isinstance(item, (dict, AuthRequirement))] if isinstance(value, list) else []


class AuthCheckInput(BaseModel):
    start_url: str
    description: str = ""
    pages: list[dict[str, Any]] = Field(default_factory=list)
    signals: list[dict[str, Any]] = Field(default_factory=list)


class AuthRequirementAgent(Agent):
    """Decides whether the application needs sign-in details (connections) for its tests, from the discovered pages and signals."""

    name = "auth_requirements"
    thinking = False

    def check(
        self,
        start_url: str,
        description: str,
        digest: list[dict[str, Any]],
        signals: list[dict[str, Any]],
        project_id: str = "",
        on_event: EventCallback | None = None,
    ) -> AuthRequirementCheck:
        payload = {"start_url": start_url, "description": description, "pages": digest, "signals": signals}
        return self.invoke("auth.requirements", payload, AuthRequirementCheck, input_model=AuthCheckInput, project_id=project_id, on_event=on_event)


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
    model_role = "fast"

    def enrich(self, elements: list[dict[str, Any]], project_id: str = "") -> LocatorEnrichment:
        return self.invoke("locator", {"elements": elements}, LocatorEnrichment, input_model=LocatorInput, project_id=project_id)
