"""Resolve element keys from config/locators.json into Selenium (By, value) pairs.

The ``resolved`` entry is computed by the studio from the framework-neutral selector. There is no silent fallback.
"""

from __future__ import annotations

import json
from pathlib import Path

from selenium.webdriver.common.by import By

LOCATORS_FILE = Path(__file__).resolve().parent.parent / "config" / "locators.json"
BY = {"css": By.CSS_SELECTOR, "xpath": By.XPATH}


def load_locators() -> dict:
    return json.loads(LOCATORS_FILE.read_text(encoding="utf-8"))


def by_for(spec: dict) -> tuple[str, str]:
    resolved = spec["resolved"]
    return BY[resolved["by"]], resolved["value"]
