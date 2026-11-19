from __future__ import annotations

from utils.element import Element


class BasePage:
    path = "/"

    def __init__(self, app) -> None:
        self.app = app

    def element(self, key: str) -> Element:
        return Element(self.app, key)

    def open(self) -> None:
        self.app.goto(self.path)
