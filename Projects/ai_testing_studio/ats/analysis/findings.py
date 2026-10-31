"""Value objects shared by the analysis, healing and defect modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ats.analysis.classifier import RuleHint
from ats.models import FailureAnalysis, LocatorSpec


@dataclass
class Finding:
    """Everything known about one failed test case, gathered from its evidence."""

    test_case_id: str
    result: dict[str, Any]
    failure: dict[str, Any]
    element_key: str
    action: str
    error: str
    html: str
    old_spec: LocatorSpec | None
    check: dict[str, Any]
    candidates: list[dict[str, Any]]
    hint: RuleHint
    analysis: FailureAnalysis = field(default_factory=FailureAnalysis)
    ai_used: bool = False
    notes: list[str] = field(default_factory=list)
    healing: dict[str, Any] = field(default_factory=dict)
    origin: Finding | None = None  # set on follow-up findings discovered while rerunning a healed test
    @property
    def url(self) -> str:
        return str(self.failure.get("url") or "")

    @property
    def category(self) -> str:
        return self.analysis.category.value

    def to_dict(self) -> dict[str, Any]:
        """The analysis document stored with the result (no DOM, no secrets)."""
        data = self.analysis.model_dump(mode="json")
        data.update(
            {
                "element_key": self.element_key, "action": self.action, "page_url": self.url, "rule_hint": self.hint.as_dict(),
                "locator_check": self.check, "candidates": self.candidates[:5], "ai_used": self.ai_used, "notes": self.notes,
                "healing": self.healing,
            }
        )  # fmt: skip
        return data
