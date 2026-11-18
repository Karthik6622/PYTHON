"""Base class of the screen objects and the element wrapper: every wait is explicit (WebDriverWait), every locator is tried in ranked order."""

from __future__ import annotations

import os

from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait

FIND_TIMEOUT = float(os.environ.get("FIND_TIMEOUT", "20"))  # seconds an element may take to appear
POLL = 0.4


class Element:
    """One element of a screen. ``locators`` are ``(AppiumBy strategy, value)`` pairs, best first; the first that matches is used."""

    def __init__(self, mobile, key: str, locators: list[tuple[str, str]]) -> None:  # noqa: ANN001
        self.mobile = mobile
        self.key = key
        self.locators = locators

    @property
    def driver(self):  # noqa: ANN201
        return self.mobile.driver

    def _describe(self) -> str:
        return "; ".join(f"{by}={value!r}" for by, value in self.locators)

    def _matches(self, driver=None):  # noqa: ANN001, ANN202
        driver = driver or self.driver
        for by, value in self.locators:
            try:
                found = driver.find_elements(by, value)
            except Exception:  # noqa: BLE001 - a locator that cannot be evaluated is simply not a match
                continue
            if found:
                return found[0]
        return False

    def find(self, timeout: float | None = None):  # noqa: ANN201
        """The live element, waiting until one locator matches. Raises NoSuchElementException with the locators that were tried."""
        wait = WebDriverWait(self.driver, FIND_TIMEOUT if timeout is None else timeout, poll_frequency=POLL)
        try:
            return wait.until(self._matches)
        except TimeoutException:
            raise NoSuchElementException(f"Element '{self.key}' was not found within {FIND_TIMEOUT if timeout is None else timeout:g}s (NoSuchElement). Tried: {self._describe()}") from None

    def _retry(self, action):  # noqa: ANN001, ANN202
        try:
            return action(self.find())
        except StaleElementReferenceException:
            return action(self.find())

    # ------------------------------------------------------------------ actions
    def tap(self) -> None:
        self._retry(lambda el: el.click())

    def long_press(self, millis: int = 1200) -> None:
        self._retry(lambda el: self.driver.execute_script("mobile: longClickGesture", {"elementId": el.id, "duration": millis}))

    def type(self, text: str) -> None:
        def enter(el) -> None:  # noqa: ANN001
            el.click()
            el.clear()
            el.send_keys(text)

        self._retry(enter)

    def clear(self) -> None:
        self._retry(lambda el: el.clear())

    # ------------------------------------------------------------------ reading
    def text(self) -> str:
        el = self.find()
        return (el.text or el.get_attribute("text") or el.get_attribute("content-desc") or "").strip()

    def is_displayed(self, timeout: float = 0.0) -> bool:
        try:
            return bool(self.find(timeout).is_displayed())
        except (NoSuchElementException, StaleElementReferenceException):
            return False

    # ------------------------------------------------------------------ expectations
    def should_be_visible(self) -> None:
        self.find()
        wait = WebDriverWait(self.driver, FIND_TIMEOUT, poll_frequency=POLL, ignored_exceptions=(StaleElementReferenceException, NoSuchElementException))
        try:
            wait.until(lambda _d: self._matches() and self._matches().is_displayed())
        except TimeoutException:
            raise AssertionError(f"Expected '{self.key}' to be visible, but it is not displayed") from None

    def should_be_hidden(self) -> None:
        wait = WebDriverWait(self.driver, FIND_TIMEOUT, poll_frequency=POLL, ignored_exceptions=(StaleElementReferenceException,))
        try:
            wait.until(lambda _d: not self._matches() or not self._matches().is_displayed())
        except TimeoutException:
            raise AssertionError(f"Expected '{self.key}' to be hidden, but it is still visible") from None

    def should_have_text(self, expected: str) -> None:
        seen = {"text": ""}

        def check(_driver) -> bool:  # noqa: ANN001
            el = self._matches()
            if not el:
                return False
            seen["text"] = (el.text or el.get_attribute("text") or el.get_attribute("content-desc") or "").strip()
            return expected in seen["text"]

        wait = WebDriverWait(self.driver, FIND_TIMEOUT, poll_frequency=POLL, ignored_exceptions=(StaleElementReferenceException,))
        try:
            wait.until(check)
        except TimeoutException:
            raise AssertionError(f"Expected '{self.key}' to contain the text {expected!r} but it was {seen['text']!r}") from None

    def should_be_enabled(self) -> None:
        self._expect_enabled(True)

    def should_be_disabled(self) -> None:
        self._expect_enabled(False)

    def _expect_enabled(self, enabled: bool) -> None:
        wait = WebDriverWait(self.driver, FIND_TIMEOUT, poll_frequency=POLL, ignored_exceptions=(StaleElementReferenceException,))
        try:
            wait.until(lambda _d: self._matches() and bool(self._matches().is_enabled()) == enabled)
        except TimeoutException:
            raise AssertionError(f"Expected '{self.key}' to be {'enabled' if enabled else 'disabled'}, but it is {'disabled' if enabled else 'enabled'}") from None


class BaseScreen:
    """A screen of the app. Subclasses declare their elements in ``__init__`` with ``self.element(key, [locators])``."""

    name = ""

    def __init__(self, mobile) -> None:  # noqa: ANN001
        self.mobile = mobile

    def element(self, key: str, locators: list[tuple[str, str]]) -> Element:
        return Element(self.mobile, key, locators)
