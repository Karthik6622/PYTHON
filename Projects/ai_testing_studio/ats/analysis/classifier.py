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
API_TIMEOUT = re.compile(r"timed out|ReadTimeout|ConnectTimeout|PoolTimeout", re.I)
API_CONNECTION = re.compile(r"connection error|ConnectError|RemoteProtocolError|NetworkError|Name or service not known|getaddrinfo|Connection refused", re.I)


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


# ----------------------------------------------------------------------------------------
# mobile (Appium) failures
# ----------------------------------------------------------------------------------------
MOBILE_SESSION = re.compile(
    r"SessionNotCreated|InvalidSessionId|NoSuchDriver|session (?:is )?(?:terminated|not found|does not exist|has (?:already )?ended)|UiAutomator2 server|instrumentation process|"
    r"device (?:offline|not found|unauthorized)|Could not find a connected Android device|no devices/emulators|ANDROID_HOME|INSTALL_FAILED|adb(?:\.exe)?\b.*(?:not found|failed|error)|"
    r"ECONNREFUSED|Connection refused|Max retries exceeded|Failed to establish a new connection|Appium is not available|Appium did not become ready|Appium stopped|"
    r"No application to test|Could not proxy command|socket hang up|RemoteDisconnected|Failed to connect to",
    re.I,
)
MOBILE_CRASH = re.compile(r"FATAL EXCEPTION|ANR in |has stopped|AndroidRuntime: .*Exception|Process .* (?:is not running|died)|app crashed", re.I)
MOBILE_STALE = re.compile(r"StaleElementReference|ElementNotInteractable|ElementClickIntercepted|not interactable|element is not (?:visible|enabled)", re.I)


def classify_mobile(error_text: str, action: str, element_key: str, element_in_screen: bool | None, logcat: list[str] | None = None) -> RuleHint:
    """Pre-classification of an Appium failure. ``element_in_screen``: True/False when the failing screen's page source could be checked
    against the element's recorded locators, ``None`` when it could not."""
    text = error_text or ""
    log = "\n".join(logcat or [])
    base = {"action": action, "element_key": element_key}
    missing = MISSING_ENV.search(text)
    if missing:
        return RuleHint(FailureCategory.TEST_DATA.value, 0.95, f"Environment variable {missing.group(1)} is not set for this run.", **base)
    if MOBILE_SESSION.search(text):
        return RuleHint(FailureCategory.ENVIRONMENT.value, 0.9, "The Appium session, the device or the Appium server failed (not the application).", **base)
    if MOBILE_CRASH.search(log) or MOBILE_CRASH.search(text):
        return RuleHint(FailureCategory.APPLICATION_DEFECT.value, 0.7, "The logcat (or the error) shows the app crashed or stopped responding.", **base)
    is_assertion = action.startswith("expect_") or "AssertionError" in text
    not_found = bool(NOT_FOUND.search(text))
    if not_found or element_in_screen is False:
        if element_in_screen is True:
            return RuleHint(FailureCategory.TIMEOUT.value, 0.5, "The element exists on the failing screen but was not found in time (off screen, covered or still loading).", **base)
        confidence = 0.75 if element_in_screen is False else 0.5
        return RuleHint(
            FailureCategory.LOCATOR_DRIFT.value, confidence - (0.15 if is_assertion else 0.0),
            "None of the element's locators matches the screen captured at the failure." if element_in_screen is False else "The element was not found; the failing screen could not be checked.",
            locator_suspect=True, **base,
        )  # fmt: skip
    if MOBILE_STALE.search(text):
        return RuleHint(FailureCategory.TIMEOUT.value, 0.6, "The element exists but could not be used in time (stale, covered, disabled or still animating).", **base)
    if is_assertion:
        return RuleHint(FailureCategory.ASSERTION.value, 0.8 if MISMATCH.search(text) else 0.6, "The element was present but the observed text or state did not match the expectation.", **base)
    if re.search(r"Timeout|timed out", text, re.I):
        return RuleHint(FailureCategory.TIMEOUT.value, 0.5, "A wait timed out without a clearer cause in the evidence.", **base)
    return RuleHint(FailureCategory.UNKNOWN.value, 0.3, "No rule matched the evidence.", **base)
