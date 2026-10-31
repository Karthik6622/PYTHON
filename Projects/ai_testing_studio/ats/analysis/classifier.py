"""Rule-based failure pre-classification. The AI agent sees this as a hint; it never replaces the evidence."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from ats.models import FailureCategory

ENV_PATTERNS = re.compile(
    r"net::ERR_(NAME_NOT_RESOLVED|CONNECTION_REFUSED|CONNECTION_RESET|INTERNET_DISCONNECTED|CERT|SSL|TIMED_OUT|ADDRESS_UNREACHABLE)|"
    r"ECONNREFUSED|ENOTFOUND|getaddrinfo|Name or service not known|ERR_SSL|SSL: CERTIFICATE|Max retries exceeded|"
    r"NS_ERROR_(CONNECTION_REFUSED|UNKNOWN_HOST)|Connection refused|unable to connect|Could not reach host",
    re.I,
)
NOT_FOUND = re.compile(r"Element not found|NoSuchElement|no such element|waiting for (get_by|locator|xpath|css|\[)|strict mode violation|Unable to locate element", re.I)
NOT_INTERACTABLE = re.compile(r"not clickable|intercepts pointer events|element is not (visible|enabled|stable|attached)|ElementClickIntercepted|ElementNotInteractable|not interactable|Element not visible", re.I)
MISMATCH = re.compile(r"unexpected value|Actual value|not found in|is not '|does not contain|Expected|expected .* to|Value of .* is not|still visible|is not (enabled|disabled)", re.I)
SERVER_ERROR = re.compile(r"status of 5\d\d|\b5\d\d \(|Internal Server Error|Bad Gateway|Service Unavailable", re.I)
MISSING_ENV = re.compile(r"Environment variable (\w+) is not set", re.I)


@dataclass
class RuleHint:
    category: str
    confidence: float
    reason: str
    locator_suspect: bool = False
    element_key: str = ""
    action: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify(error_text: str, action: str, element_key: str, element_in_dom: bool | None, console: list[str] | None = None) -> RuleHint:
    """``element_in_dom``: True/False when the failing page's DOM could be checked, ``None`` when it could not."""
    text = error_text or ""
    base = {"action": action, "element_key": element_key}
    missing = MISSING_ENV.search(text)
    if missing:
        return RuleHint(FailureCategory.TEST_DATA.value, 0.95, f"Environment variable {missing.group(1)} is not set for this run.", **base)
    if "Unknown element key" in text:
        return RuleHint(FailureCategory.AUTOMATION_ISSUE.value, 0.95, "The script references an element key that is not in the locator file.", locator_suspect=False, **base)
    if ENV_PATTERNS.search(text):
        return RuleHint(FailureCategory.ENVIRONMENT.value, 0.9, "A network, DNS, TLS or connection error occurred while reaching the application.", **base)
    is_assertion = action.startswith("expect_")
    not_found = bool(NOT_FOUND.search(text))
    if not_found or element_in_dom is False:
        if element_in_dom is False:
            return RuleHint(
                FailureCategory.LOCATOR_DRIFT.value, 0.75 if not is_assertion else 0.6,
                "The element's locator matches nothing in the DOM captured at the failure point.", locator_suspect=True, **base,
            )  # fmt: skip
        if element_in_dom is None:
            return RuleHint(FailureCategory.LOCATOR_DRIFT.value, 0.5, "The runner could not find the element; the failing DOM could not be checked.", locator_suspect=True, **base)
    if NOT_INTERACTABLE.search(text):
        return RuleHint(FailureCategory.TIMEOUT.value, 0.6, "The element exists but could not be interacted with in time (hidden, disabled, covered or still animating).", **base)
    if is_assertion:
        confidence = 0.8 if MISMATCH.search(text) else 0.6
        if SERVER_ERROR.search("\n".join(console or [])):
            return RuleHint(FailureCategory.APPLICATION_DEFECT.value, 0.65, "An assertion failed and the console shows a server error response.", **base)
        return RuleHint(FailureCategory.ASSERTION.value, confidence, "The element was present but the observed value did not match the expectation.", **base)
    if re.search(r"Timeout|timed out|TimeoutException", text, re.I):
        return RuleHint(FailureCategory.TIMEOUT.value, 0.5, "A wait timed out without a clearer cause in the evidence.", **base)
    if SERVER_ERROR.search("\n".join(console or [])):
        return RuleHint(FailureCategory.APPLICATION_DEFECT.value, 0.5, "The console shows server error responses.", **base)
    return RuleHint(FailureCategory.UNKNOWN.value, 0.3, "No rule matched the evidence.", **base)
