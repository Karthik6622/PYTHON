"""Locator patching: the only change the healing engine is allowed to make to generated tests."""

from __future__ import annotations

import difflib
import json
from typing import Any

from ats.locators.selenium_map import to_selenium
from ats.models import Selector

LOCATOR_FILE = "config/locators.json"
MAX_ALTERNATIVES = 5


class PatchError(ValueError):
    pass


def patch_locators(files: dict[str, str], element_key: str, new: Selector, selenium: bool) -> tuple[dict[str, str], dict[str, Any], dict[str, Any]]:
    """Return (new files, old entry, new entry). The previous preferred selector is kept as an alternative; nothing else changes."""
    try:
        data = json.loads(files[LOCATOR_FILE])
    except (KeyError, ValueError) as exc:
        raise PatchError("The locator file is missing or invalid.") from exc
    if element_key not in data:
        raise PatchError(f"Element '{element_key}' is not in the locator file.")
    old_entry = json.loads(json.dumps(data[element_key]))
    entry = data[element_key]
    previous = Selector.model_validate(entry["preferred"])
    if previous.identity() == new.identity():
        raise PatchError("The proposed selector is the same as the current one.")
    alternatives = [previous] + [Selector.model_validate(a) for a in entry.get("alternatives", [])]
    seen = {new.identity()}
    kept = [s for s in alternatives if not (s.identity() in seen or seen.add(s.identity()))]
    entry["preferred"] = new.model_dump(exclude_none=True)
    entry["alternatives"] = [s.model_dump(exclude_none=True) for s in kept[:MAX_ALTERNATIVES]]
    if selenium:
        entry["resolved"] = to_selenium(new)
    patched = dict(files)
    patched[LOCATOR_FILE] = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    return patched, old_entry, json.loads(json.dumps(entry))


def entry_diff(element_key: str, old_entry: dict[str, Any], new_entry: dict[str, Any]) -> str:
    """Unified diff of one locator entry (for the approval screen and pull request text)."""
    before = json.dumps({element_key: old_entry}, indent=2, ensure_ascii=False).splitlines()
    after = json.dumps({element_key: new_entry}, indent=2, ensure_ascii=False).splitlines()
    return "\n".join(difflib.unified_diff(before, after, LOCATOR_FILE, LOCATOR_FILE, lineterm="", n=2))
