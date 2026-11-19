"""Element wrapper with explicit waits. Mirrors the Playwright page-object API so tests read the same."""

from __future__ import annotations

import re

from selenium.webdriver import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait


def to_key(name: str):
    if len(name) == 1:
        return name
    constant = re.sub(r"(?<!^)(?=[A-Z])", "_", name).upper()
    return getattr(Keys, constant, name)


class Element:
    def __init__(self, app, key: str) -> None:
        self.app = app
        self.key = key

    def _wait(self, condition, message: str):
        return WebDriverWait(self.app.driver, self.app.timeout).until(condition, message)

    def _by(self):
        return self.app.by(self.key)

    def find(self):
        return self._wait(EC.presence_of_element_located(self._by()), f"Element not found: {self.key} {self._by()}")

    def _interactable(self):
        return self._wait(EC.element_to_be_clickable(self._by()), f"Element not clickable: {self.key} {self._by()}")

    def click(self) -> None:
        self._interactable().click()

    def dblclick(self) -> None:
        ActionChains(self.app.driver).double_click(self._interactable()).perform()

    def fill(self, text: str) -> None:
        element = self._interactable()
        element.clear()
        element.send_keys(text)

    def clear(self) -> None:
        self._interactable().clear()

    def select_option(self, label: str) -> None:
        Select(self._interactable()).select_by_visible_text(label)

    def check(self) -> None:
        element = self._interactable()
        if not element.is_selected():
            element.click()

    def uncheck(self) -> None:
        element = self._interactable()
        if element.is_selected():
            element.click()

    def press(self, key: str) -> None:
        self.find().send_keys(to_key(key))

    def hover(self) -> None:
        ActionChains(self.app.driver).move_to_element(self.find()).perform()

    def expect_visible(self) -> None:
        self._wait(EC.visibility_of_element_located(self._by()), f"Element not visible: {self.key}")

    def expect_hidden(self) -> None:
        self._wait(EC.invisibility_of_element_located(self._by()), f"Element still visible: {self.key}")

    def expect_text(self, text: str) -> None:
        self._wait(lambda d: text in (self.find().text or ""), f"Text {text!r} not found in {self.key}")

    def expect_value(self, text: str) -> None:
        self._wait(lambda d: (self.find().get_attribute("value") or "") == text, f"Value of {self.key} is not {text!r}")

    def expect_enabled(self) -> None:
        self._wait(lambda d: self.find().is_enabled(), f"{self.key} is not enabled")

    def expect_disabled(self) -> None:
        self._wait(lambda d: not self.find().is_enabled(), f"{self.key} is not disabled")
