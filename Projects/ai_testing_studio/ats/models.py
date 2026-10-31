"""Domain models shared by services, agents, storage and the UI (pydantic v2)."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ----------------------------------------------------------------------------------------
# Enumerations
# ----------------------------------------------------------------------------------------
class Coverage(str, Enum):
    BASIC = "BASIC"
    INTERMEDIATE = "INTERMEDIATE"
    ADVANCED = "ADVANCED"
    CUSTOM = "CUSTOM"


class Status(str, Enum):
    """Result statuses. HEALED and INCONCLUSIVE are never merged into PASS."""

    PASS = "PASS"
    FAIL = "FAIL"
    HEALED = "HEALED"
    SKIPPED = "SKIPPED"
    INCONCLUSIVE = "INCONCLUSIVE"


class FailureCategory(str, Enum):
    APPLICATION_DEFECT = "LIKELY APPLICATION DEFECT"
    AUTOMATION_ISSUE = "LIKELY AUTOMATION ISSUE"
    LOCATOR_DRIFT = "LOCATOR DRIFT"
    TEST_DATA = "TEST DATA ISSUE"
    ENVIRONMENT = "ENVIRONMENT ISSUE"
    TIMEOUT = "TIMEOUT/SYNCHRONIZATION"
    ASSERTION = "ASSERTION FAILURE"
    UNKNOWN = "UNKNOWN"


HEALABLE_CATEGORIES = {FailureCategory.LOCATOR_DRIFT, FailureCategory.AUTOMATION_ISSUE}

STAGES = ["Setup", "Discover", "Scenarios", "Test Cases", "Automation", "GitHub", "Execute", "Analyze", "Report"]

COVERAGE_GUIDE: dict[str, str] = {
    "BASIC": (
        "Important user-visible functionality and critical happy paths: page load, main navigation, important "
        "buttons, basic forms, required fields and the primary workflows."
    ),
    "INTERMEDIATE": (
        "Everything in BASIC plus broader positive and negative coverage: validation, boundary cases, navigation, "
        "common components, form behaviour, error states and functional coverage."
    ),
    "ADVANCED": (
        "Comprehensive analysis of what is discoverable: positive, negative, functional, regression candidates, "
        "boundary testing, form validation, input combinations, navigation, error handling, component interactions, "
        "authentication/authorization behaviour when accessible, accessibility-oriented checks, responsive behaviour, "
        "API/network observations, cross-browser candidates and edge cases."
    ),
    "CUSTOM": "Only the testing categories selected by the user.",
}

CUSTOM_CATEGORIES = [
    "Positive",
    "Negative",
    "Functional",
    "Regression",
    "Boundary",
    "Validation",
    "UI",
    "Navigation",
    "Accessibility",
    "Responsive",
    "Error Handling",
    "Integration",
    "Authentication",
]

TEST_TYPES = [
    "Positive",
    "Negative",
    "Functional",
    "Regression",
    "Boundary",
    "Validation",
    "UI",
    "Accessibility",
    "Navigation",
    "Integration",
    "Responsive",
    "Error Handling",
    "Authentication",
]
PRIORITIES = ["Critical", "High", "Medium", "Low"]
SUITABILITY = ["High", "Medium", "Low", "Manual only"]


def _title_match(value: Any, allowed: list[str], default: str) -> str:
    text = str(value or "").strip().lower().replace("_", " ").replace("-", " ")
    for item in allowed:
        if item.lower() == text:
            return item
    for item in allowed:
        if item.lower() in text:
            return item
    return default


def _priority(value: Any) -> str:
    text = str(value or "").strip().lower()
    mapping = {"p0": "Critical", "p1": "High", "p2": "Medium", "p3": "Low", "blocker": "Critical", "major": "High", "minor": "Low"}
    return mapping.get(text) or _title_match(text, PRIORITIES, "Medium")


def _as_list(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        parts = [p.strip(" -•\t") for p in re.split(r"\r?\n|;\s*(?=\S)", value) if p.strip(" -•\t")]
        return parts
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return [str(value)]


class _Model(BaseModel):
    """Tolerant base: unknown keys are ignored and whitespace is trimmed (model output is rarely perfect)."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


# ----------------------------------------------------------------------------------------
# Locators
# ----------------------------------------------------------------------------------------
SelectorKind = Literal["testid", "role", "label", "placeholder", "text", "id", "name", "css", "xpath"]


class Selector(_Model):
    """One way to identify an element. For ``role`` selectors ``value`` is the role and ``name`` the accessible name."""

    kind: SelectorKind
    value: str
    name: str | None = None
    exact: bool = False

    def display(self) -> str:
        if self.kind == "role":
            suffix = f", {{ name: {self.name!r} }}" if self.name else ""
            return f"getByRole({self.value!r}{suffix})"
        calls = {
            "testid": "getByTestId",
            "label": "getByLabel",
            "placeholder": "getByPlaceholder",
            "text": "getByText",
        }
        if self.kind in calls:
            return f"{calls[self.kind]}({self.value!r})"
        if self.kind == "id":
            return f"#{self.value}"
        if self.kind == "name":
            return f'[name="{self.value}"]'
        return self.value

    def identity(self) -> tuple[str, str, str]:
        return (self.kind, self.value, self.name or "")


class LocatorSpec(_Model):
    element_key: str
    page_key: str = ""
    page_url: str = ""
    component: str = ""
    intent: str = ""
    tag: str = ""
    role: str = ""
    name: str = ""
    preferred: Selector
    alternatives: list[Selector] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
    stability: float = 0.5

    def all_selectors(self) -> list[Selector]:
        return [self.preferred, *self.alternatives]


# ----------------------------------------------------------------------------------------
# Discovery
# ----------------------------------------------------------------------------------------
class DiscoveryLimits(_Model):
    max_pages: int = Field(default=8, ge=1, le=50)
    max_depth: int = Field(default=2, ge=0, le=5)
    allowed_domains: list[str] = Field(default_factory=list)
    excluded_paths: list[str] = Field(default_factory=list)
    include_screenshots: bool = True
    ignore_https_errors: bool = False

    @field_validator("allowed_domains", "excluded_paths", mode="before")
    @classmethod
    def _split(cls, value: Any) -> list[str]:
        return _as_list(value)


class AuthConfig(_Model):
    """Authentication settings. Secrets are referenced by environment-variable NAME, never stored."""

    mode: Literal["none", "storage_state", "env_credentials", "login_workflow", "manual_capture"] = "none"
    storage_state_file: str = ""  # file name inside the secure folder
    username_env: str = "TEST_APP_USERNAME"
    password_env: str = "TEST_APP_PASSWORD"
    login_url: str = ""
    username_selector: str = ""
    password_selector: str = ""
    submit_selector: str = ""
    success_url_contains: str = ""


class PageSnapshot(_Model):
    page_key: str = ""
    url: str
    final_url: str = ""
    title: str = ""
    status: int | None = None
    depth: int = 0
    headings: list[str] = Field(default_factory=list)
    elements: list[dict[str, Any]] = Field(default_factory=list)
    forms: list[dict[str, Any]] = Field(default_factory=list)
    tables: list[dict[str, Any]] = Field(default_factory=list)
    navigation: list[dict[str, Any]] = Field(default_factory=list)
    components: dict[str, int] = Field(default_factory=dict)
    aria_snapshot: str = ""
    screenshot: str = ""
    console_errors: list[str] = Field(default_factory=list)
    network: list[dict[str, Any]] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    requires_auth: bool = False


class DiscoveryResult(_Model):
    start_url: str
    pages: list[PageSnapshot] = Field(default_factory=list)
    skipped: list[dict[str, str]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary: str = ""  # AI generated understanding of the application
    analysis: dict[str, Any] = Field(default_factory=dict)  # modules / workflows from the Web Discovery Agent


# ----------------------------------------------------------------------------------------
# Scenarios and test cases
# ----------------------------------------------------------------------------------------
class Scenario(_Model):
    scenario_id: str = ""
    title: str
    module: str = "General"
    page: str = ""
    description: str = ""
    preconditions: list[str] = Field(default_factory=list)
    test_type: str = "Functional"
    priority: str = "Medium"
    expected_outcome: str = ""
    automation_suitability: str = "High"
    status: str = "draft"
    source: str = "ai"

    @field_validator("preconditions", mode="before")
    @classmethod
    def _pre(cls, value: Any) -> list[str]:
        return _as_list(value)

    @field_validator("test_type", mode="before")
    @classmethod
    def _type(cls, value: Any) -> str:
        return _title_match(value, TEST_TYPES, "Functional")

    @field_validator("priority", mode="before")
    @classmethod
    def _prio(cls, value: Any) -> str:
        return _priority(value)

    @field_validator("automation_suitability", mode="before")
    @classmethod
    def _suit(cls, value: Any) -> str:
        return _title_match(value, SUITABILITY, "Medium")


class TestCase(_Model):
    __test__ = False  # not a pytest class

    test_case_id: str = ""
    scenario_id: str = ""
    module: str = "General"
    title: str
    description: str = ""
    preconditions: list[str] = Field(default_factory=list)
    test_data: dict[str, str] = Field(default_factory=dict)
    steps: list[str] = Field(default_factory=list)
    expected_result: str = ""
    test_type: str = "Functional"
    priority: str = "Medium"
    automation_candidate: bool = True
    related_page: str = ""
    component: str = ""
    tags: list[str] = Field(default_factory=list)
    status: str = "draft"
    source: str = "ai"

    @field_validator("preconditions", "steps", "tags", mode="before")
    @classmethod
    def _lists(cls, value: Any) -> list[str]:
        return _as_list(value)

    @field_validator("test_data", mode="before")
    @classmethod
    def _data(cls, value: Any) -> dict[str, str]:
        if not value:
            return {}
        if isinstance(value, dict):
            return {str(k): str(v) for k, v in value.items()}
        if isinstance(value, list):
            result: dict[str, str] = {}
            for index, item in enumerate(value, 1):
                if isinstance(item, dict) and "name" in item:
                    result[str(item["name"])] = str(item.get("value", ""))
                elif isinstance(item, dict):
                    result.update({str(k): str(v) for k, v in item.items()})
                else:
                    text = str(item)
                    key, sep, rest = text.partition(":")
                    result[key.strip() if sep else f"data_{index}"] = rest.strip() if sep else text
            return result
        return {"data": str(value)}

    @field_validator("test_type", mode="before")
    @classmethod
    def _type(cls, value: Any) -> str:
        return _title_match(value, TEST_TYPES, "Functional")

    @field_validator("priority", mode="before")
    @classmethod
    def _prio(cls, value: Any) -> str:
        return _priority(value)

    @field_validator("automation_candidate", mode="before")
    @classmethod
    def _bool(cls, value: Any) -> bool:
        if isinstance(value, str):
            return value.strip().lower() in {"true", "yes", "y", "1"}
        return bool(value) if value is not None else True


# ----------------------------------------------------------------------------------------
# Automation plan (framework independent)
# ----------------------------------------------------------------------------------------
STEP_ACTIONS = [
    "goto",
    "click",
    "dblclick",
    "fill",
    "clear",
    "select",
    "check",
    "uncheck",
    "press",
    "hover",
    "expect_visible",
    "expect_hidden",
    "expect_text",
    "expect_value",
    "expect_enabled",
    "expect_disabled",
    "expect_url_contains",
    "expect_title_contains",
]
ELEMENT_ACTIONS = set(STEP_ACTIONS) - {"goto", "expect_url_contains", "expect_title_contains"}
VALUE_ACTIONS = {"goto", "fill", "select", "press", "expect_text", "expect_value", "expect_url_contains", "expect_title_contains"}


class AutomationStep(_Model):
    action: str
    element: str | None = None
    value: str | None = None
    description: str = ""

    @field_validator("action", mode="before")
    @classmethod
    def _action(cls, value: Any) -> str:
        text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
        if text not in STEP_ACTIONS:
            raise ValueError(f"unsupported action '{value}'")
        return text

    @field_validator("value", mode="before")
    @classmethod
    def _value(cls, value: Any) -> str | None:
        return None if value is None else str(value)


class TestScript(_Model):
    __test__ = False

    test_case_id: str
    title: str = ""
    notes: str = ""
    steps: list[AutomationStep] = Field(default_factory=list)


class AutomationPlan(_Model):
    scripts: list[TestScript] = Field(default_factory=list)


# ----------------------------------------------------------------------------------------
# Analysis
# ----------------------------------------------------------------------------------------
class FailureAnalysis(_Model):
    category: FailureCategory = FailureCategory.UNKNOWN
    confidence: float = Field(default=0.3, ge=0.0, le=1.0)
    summary: str = ""
    reasoning: str = ""
    evidence_used: list[str] = Field(default_factory=list)
    insufficient_evidence: bool = False
    automation_fixable: bool = False
    recommended_action: str = ""

    @field_validator("category", mode="before")
    @classmethod
    def _category(cls, value: Any) -> FailureCategory:
        text = re.sub(r"[^A-Z]", "", str(value or "").upper())
        for item in FailureCategory:
            if re.sub(r"[^A-Z]", "", item.value) == text:
                return item
        for item in FailureCategory:
            if re.sub(r"[^A-Z]", "", item.value).startswith(text[:10]) and text:
                return item
        return FailureCategory.UNKNOWN

    @field_validator("evidence_used", mode="before")
    @classmethod
    def _ev(cls, value: Any) -> list[str]:
        return _as_list(value)

    @field_validator("confidence", mode="before")
    @classmethod
    def _conf(cls, value: Any) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.3
        return min(max(number / 100 if number > 1 else number, 0.0), 1.0)


class ProposedSelector(_Model):
    selector: Selector
    confidence: float = 0.5
    reason: str = ""

    @field_validator("confidence", mode="before")
    @classmethod
    def _conf(cls, value: Any) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.5
        return min(max(number / 100 if number > 1 else number, 0.0), 1.0)


class HealingProposal(_Model):
    element_key: str = ""
    intended_action: str = ""
    behavior_changed: bool = False
    explanation: str = ""
    proposals: list[ProposedSelector] = Field(default_factory=list)


class DefectNarrative(_Model):
    title: str
    description: str = ""
    severity: str = "Medium"
    priority: str = "Medium"
    actual_result: str = ""

    @field_validator("severity", "priority", mode="before")
    @classmethod
    def _sev(cls, value: Any) -> str:
        return _priority(value)


class ChangeSet(_Model):
    """Targeted changes to scenarios / test cases requested through natural language."""

    add: list[dict[str, Any]] = Field(default_factory=list)
    update: list[dict[str, Any]] = Field(default_factory=list)
    delete: list[str] = Field(default_factory=list)
    explanation: str = ""

    @field_validator("delete", mode="before")
    @classmethod
    def _delete(cls, value: Any) -> list[str]:
        return _as_list(value)


# ----------------------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------------------
def slugify(text: str, fallback: str = "item", sep: str = "_") -> str:
    slug = re.sub(r"[^a-z0-9]+", sep, (text or "").lower()).strip(sep)
    return slug or fallback


def normalize_id(value: str) -> str:
    """Upper-case alphanumerics only. Used to match test names in runner output with test case IDs."""
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())
