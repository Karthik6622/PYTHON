from __future__ import annotations

from playwright.sync_api import Locator


class BasePage:
    path = "/"

    def __init__(self, app) -> None:
        self.app = app

    def locator(self, key: str) -> Locator:
        return self.app.locator(key)

    def open(self) -> None:
        self.app.goto(self.path)
