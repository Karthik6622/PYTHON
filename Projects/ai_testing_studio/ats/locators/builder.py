"""Builds the locator repository from discovered elements: ranked stable strategies, alternatives and evidence."""

from __future__ import annotations

import re
from typing import Any

from ats.models import DiscoveryResult, LocatorSpec, PageSnapshot, Selector

_HASHED_CLASS = re.compile(r"(?:^|[-_])(?:[a-f0-9]{5,}|[A-Za-z]{1,3}\d{3,})$|^css-|^sc-|^jsx-|^_")
_DYNAMIC_ID = re.compile(r"(?:\d{4,}|[0-9a-f]{8}-[0-9a-f]{4}|^:r[0-9a-z]+:|^ember\d+|^react-|^radix-|^headlessui-)", re.I)
_TEXT_ROLES = {"button", "link", "tab", "menuitem", "heading", "checkbox", "radio", "switch", "option"}
_INPUT_ROLES = {"textbox", "searchbox", "combobox", "spinbutton"}


def _clean(text: str, limit: int = 60) -> str:
    return re.sub(r"\s+", " ", text or "").strip()[:limit]


def element_key(page_key: str, element: dict[str, Any], used: set[str]) -> str:
    """Stable human-readable key such as ``login.email_textbox`` (unique per project)."""
    base = (
        element.get("name")
        or element.get("label")
        or element.get("placeholder")
        or element.get("text")
        or element.get("testid")
        or element.get("id")
        or element.get("name_attr")
        or element.get("tag")
        or "element"
    )
    role = element.get("role") or element.get("tag") or "element"
    slug = re.sub(r"[^a-z0-9]+", "_", _clean(base, 40).lower()).strip("_") or "element"
    key = f"{page_key}.{slug}_{role}"[:90]
    candidate, n = key, 2
    while candidate in used:
        candidate = f"{key}_{n}"
        n += 1
    used.add(candidate)
    return candidate


def build_selectors(el: dict[str, Any]) -> tuple[list[Selector], float]:
    """Return selectors ordered best-first plus a stability score (0..1) for the preferred one."""
    out: list[Selector] = []
    counts = el.get("counts", {})
    name = _clean(el.get("name", ""))
    role = el.get("role", "")
    if el.get("testid") and counts.get("testid", 0) == 1:
        if el.get("testid_attr", "data-testid") == "data-testid":
            out.append(Selector(kind="testid", value=el["testid"]))
        else:
            out.append(Selector(kind="css", value=f'[{el["testid_attr"]}="{el["testid"]}"]'))
    if role and name and (role in _TEXT_ROLES or role in _INPUT_ROLES):
        out.append(Selector(kind="role", value=role, name=name, exact=len(name) < 25))
    if el.get("label") and el.get("tag") in {"input", "select", "textarea"}:
        out.append(Selector(kind="label", value=_clean(el["label"], 80), exact=False))
    if el.get("placeholder"):
        out.append(Selector(kind="placeholder", value=el["placeholder"]))
    if el.get("id") and counts.get("id", 0) == 1 and not _DYNAMIC_ID.search(el["id"]):
        out.append(Selector(kind="id", value=el["id"]))
    if el.get("name_attr") and counts.get("name_attr", 0) == 1:
        out.append(Selector(kind="name", value=el["name_attr"]))
    if role in _TEXT_ROLES and not name and el.get("text"):
        out.append(Selector(kind="text", value=_clean(el["text"], 50)))
    if el.get("css"):
        out.append(Selector(kind="css", value=el["css"]))
    if el.get("xpath"):
        out.append(Selector(kind="xpath", value=el["xpath"]))
    # drop duplicates, keep order
    seen: set[tuple[str, str, str]] = set()
    unique = [s for s in out if not (s.identity() in seen or seen.add(s.identity()))]
    first = unique[0].kind if unique else "xpath"
    score = {"testid": 0.97, "role": 0.9, "label": 0.85, "placeholder": 0.7, "id": 0.8, "name": 0.72, "text": 0.6, "css": 0.45, "xpath": 0.3}[first]
    if first == "role" and not el.get("visible", True):
        score -= 0.1
    return unique, score


def _interesting(el: dict[str, Any]) -> bool:
    if not el.get("visible") and not el.get("testid"):
        return False
    if el.get("tag") == "a" and not (el.get("name") or el.get("text")):
        return False
    return True


def build_locators(result: DiscoveryResult) -> list[LocatorSpec]:
    specs: list[LocatorSpec] = []
    used: set[str] = set()
    for page in result.pages:
        specs.extend(_page_locators(page, used))
    return specs


def _page_locators(page: PageSnapshot, used: set[str]) -> list[LocatorSpec]:
    specs: list[LocatorSpec] = []
    for el in page.elements:
        if not _interesting(el):
            continue
        selectors, score = build_selectors(el)
        if not selectors:
            continue
        evidence = {
            "tag": el.get("tag"), "type": el.get("type"), "role": el.get("role"), "accessible_name": el.get("name"),
            "text": el.get("text"), "id": el.get("id"), "name_attr": el.get("name_attr"), "testid": el.get("testid"),
            "classes": [c for c in el.get("classes", []) if not _HASHED_CLASS.search(c)], "placeholder": el.get("placeholder"),
            "label": el.get("label"), "required": el.get("required"), "disabled": el.get("disabled"),
            "href": el.get("href"), "options": el.get("options"), "landmark": el.get("landmark"), "page_url": page.final_url or page.url,
            "uniqueness": el.get("counts", {}), "form": el.get("form"),
        }  # fmt: skip
        specs.append(
            LocatorSpec(
                element_key=element_key(page.page_key, el, used),
                page_key=page.page_key,
                page_url=page.final_url or page.url,
                component=el.get("landmark", ""),
                tag=el.get("tag", ""),
                role=el.get("role", ""),
                name=_clean(el.get("name", "")),
                preferred=selectors[0],
                alternatives=selectors[1:5],
                evidence={k: v for k, v in evidence.items() if v not in (None, "", [], {})},
                stability=round(score, 2),
            )
        )
    return specs
