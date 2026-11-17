"""Resolve element keys from config/locators.json into Playwright locators.

There is deliberately no silent fallback: a stale locator must fail loudly so it can be analysed (and healed with approval).
"""

from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import Locator, Page

LOCATORS_FILE = Path(__file__).resolve().parent.parent / "config" / "locators.json"


def load_locators() -> dict:
    return json.loads(LOCATORS_FILE.read_text(encoding="utf-8"))


def resolve(page: Page, selector: dict) -> Locator:
    kind, value = selector["kind"], selector["value"]
    name, exact = selector.get("name"), bool(selector.get("exact", False))
    if kind == "testid":
        return page.get_by_test_id(value)
    if kind == "role":
        return page.get_by_role(value, name=name, exact=exact) if name else page.get_by_role(value)
    if kind == "label":
        return page.get_by_label(value, exact=exact)
    if kind == "placeholder":
        return page.get_by_placeholder(value, exact=exact)
    if kind == "text":
        return page.get_by_text(value, exact=exact)
    if kind == "id":
        return page.locator('[id="' + value.replace('"', '\\"') + '"]')
    if kind == "name":
        return page.locator('[name="' + value.replace('"', '\\"') + '"]')
    if kind == "xpath":
        return page.locator("xpath=" + value)
    return page.locator(value)
