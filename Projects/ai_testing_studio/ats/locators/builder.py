"""Builds the locator repository from discovered elements: ranked stable strategies, alternatives and evidence."""

from __future__ import annotations

import re
from typing import Any

from ats.models import DiscoveryResult, LocatorSpec, PageSnapshot, Selector

_HASHED_CLASS = re.compile(r"(?:^|[-_])(?:[a-f0-9]{5,}|[A-Za-z]{1,3}\d{3,})$|^css-|^sc-|^jsx-|^_")
_DYNAMIC_ID = re.compile(r"(?:\d{4,}|[0-9a-f]{8}-[0-9a-f]{4}|^:r[0-9a-z]+:|^ember\d+|^react-|^radix-|^headlessui-)", re.I)
# Test ids that UI frameworks put on every widget of a kind (Streamlit: stBaseButton-primary on every primary button, stTextInput,
# stMarkdownContainer...; MUI, Chakra, Ant...). They say WHAT an element is, not WHICH one, so a test that relies on them clicks
# whatever widget of that kind is on screen, or times out when the view differs. They are never used as the preferred selector.
_FRAMEWORK_TESTID = re.compile(r"^(st[A-Z][\w-]*|portal|root|app|main|Mui[\w-]*|chakra-[\w-]+|ant-[\w-]+|mantine-[\w-]+)$")
_TEXT_ROLES = {"button", "link", "tab", "menuitem", "heading", "checkbox", "radio", "switch", "option"}
_INPUT_ROLES = {"textbox", "searchbox", "combobox", "spinbutton"}
_NAMED_GROUPS = {"radiogroup", "tablist", "listbox", "dialog", "navigation", "group", "region", "tabpanel", "slider"}  # containers a test may target by name
_INTERACTIVE_TAGS = {"a", "button", "input", "select", "textarea", "summary"}
# CSS paths that pass through an id generated at run time (React Aria, Radix, Headless UI, React useId, long numbers) change on every load.
_DYNAMIC_CSS = re.compile(r"#[^\s>]*?(react-|radix-|headlessui-|\\?:r[0-9a-z]+\\?:|\d{6,})", re.I)
SCORES = {"testid": 0.95, "role": 0.9, "label": 0.88, "placeholder": 0.75, "id": 0.8, "name": 0.72, "text": 0.65, "css": 0.4, "xpath": 0.3}


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


def generic_testid(testid: str, shared: set[str] | None = None) -> bool:
    """A framework widget marker, or a test id that more than one element of the application carries."""
    return bool(_FRAMEWORK_TESTID.match(testid or "")) or bool(shared and testid in shared)


def _text_of(el: dict[str, Any]) -> str:
    text = _clean(el.get("text", ""), 200)
    return text if 0 < len(text) <= 80 else ""


def build_selectors(el: dict[str, Any], shared_testids: set[str] | None = None) -> tuple[list[Selector], float]:
    """Return selectors ordered best-first plus a stability score (0..1) for the preferred one.

    Order: an application-specific test id, then what a person sees (role + accessible name, label, placeholder), then stable
    attributes (id, name), then visible text, and positional CSS / XPath last. ``shared_testids`` are test ids found on more than one
    element anywhere in the application; like framework widget markers they are only kept as a text-scoped alternative."""
    out: list[Selector] = []
    counts = el.get("counts", {})
    name = _clean(el.get("name", ""))
    role = el.get("role", "")
    testid = el.get("testid", "")
    attr_name = el.get("testid_attr", "data-testid")
    generic = bool(testid) and generic_testid(testid, shared_testids)
    if testid and counts.get("testid", 0) == 1 and not generic:
        out.append(Selector(kind="testid", value=testid) if attr_name == "data-testid" else Selector(kind="css", value=f'[{attr_name}="{testid}"]'))
    if role and name and (role in _TEXT_ROLES or role in _INPUT_ROLES or role in _NAMED_GROUPS):
        out.append(Selector(kind="role", value=role, name=name, exact=len(name) < 25))
    if el.get("label") and el.get("tag") in {"input", "select", "textarea"}:
        out.append(Selector(kind="label", value=_clean(el["label"], 80), exact=False))
    if el.get("placeholder"):
        out.append(Selector(kind="placeholder", value=el["placeholder"]))
    if el.get("id") and counts.get("id", 0) == 1 and not _DYNAMIC_ID.search(el["id"]):
        out.append(Selector(kind="id", value=el["id"]))
    if el.get("name_attr") and counts.get("name_attr", 0) == 1:
        out.append(Selector(kind="name", value=el["name_attr"]))
    text = _text_of(el)
    if text and (role in _TEXT_ROLES and not name or not role and el.get("tag") not in _INTERACTIVE_TAGS):
        out.append(Selector(kind="text", value=text, exact=True))  # a message, heading or label shown on the page
    if testid and generic and (name or text):  # the framework marker narrowed down by what the element says
        quoted = (name or text).replace('"', '\\"')[:60]
        out.append(Selector(kind="css", value=f'[{attr_name}="{testid}"]:has-text("{quoted}")'))
    if el.get("css") and not _DYNAMIC_CSS.search(el["css"]):
        out.append(Selector(kind="css", value=el["css"]))
    if el.get("xpath"):
        out.append(Selector(kind="xpath", value=el["xpath"]))
    # drop duplicates, keep order
    seen: set[tuple[str, str, str]] = set()
    unique = [s for s in out if not (s.identity() in seen or seen.add(s.identity()))]
    checks = {(c.get("kind"), c.get("value"), c.get("name") or ""): c.get("count") for c in el.get("checks", [])}
    ambiguous = False
    if checks:
        # The discovery worker counted how many elements each selector matches on the live page. Unique selectors win,
        # untested ones come next, selectors that match nothing or several elements go last (stable within each group).
        def rank(selector: Selector) -> int:
            count = checks.get(selector.identity())
            return 0 if count == 1 else 1 if count is None else 2

        unique.sort(key=rank)
        ambiguous = bool(unique) and checks.get(unique[0].identity()) != 1 and unique[0].identity() in checks
    first = unique[0].kind if unique else "xpath"
    score = SCORES[first]
    if first == "css" and unique and ":has-text(" in unique[0].value:
        score = 0.7
    if first == "role" and not el.get("visible", True):
        score -= 0.1
    if ambiguous:
        score -= 0.25  # nothing on the page identifies this element uniquely: flagged for review
    return unique, max(score, 0.05)


def fingerprint(el: dict[str, Any]) -> dict[str, str]:
    """What identifies the element to a person: used to find it again when every recorded selector has stopped working."""
    data = {
        "role": el.get("role", ""), "name": _clean(el.get("name", "")), "tag": el.get("tag", ""), "type": el.get("type", ""),
        "label": _clean(el.get("label", ""), 80), "placeholder": el.get("placeholder", ""), "text": _text_of(el),
    }  # fmt: skip
    return {k: v for k, v in data.items() if v}


def spec_fingerprint(spec: LocatorSpec) -> dict[str, str]:
    """The same fingerprint, rebuilt from a stored locator and its discovery evidence."""
    ev = spec.evidence or {}
    return fingerprint({
        "role": spec.role or ev.get("role", ""), "name": spec.name or ev.get("accessible_name", ""), "tag": spec.tag or ev.get("tag", ""),
        "type": ev.get("type", ""), "label": ev.get("label", ""), "placeholder": ev.get("placeholder", ""), "text": ev.get("text", ""),
    })  # fmt: skip


def _interesting(el: dict[str, Any], inside_controls: list[str], control_names: set[str] | None = None) -> bool:
    tag = el.get("tag", "")
    if not el.get("visible") and not (el.get("testid") and not generic_testid(el.get("testid", ""))):
        return False
    if tag == "a" and not (el.get("name") or el.get("text")):
        return False
    interactive = tag in _INTERACTIVE_TAGS or el.get("role") in _TEXT_ROLES | _INPUT_ROLES | _NAMED_GROUPS
    if interactive:
        return True
    text = _text_of(el)
    if not text and not el.get("name"):
        return False  # a layout wrapper (stHeader, portal, iframe anchors ...): nothing a test would read or use
    if control_names and text.lower() in control_names:
        return False  # the visible label of a radio, checkbox or button: tests use the control itself
    xpath = el.get("xpath", "")
    return not any(xpath.startswith(prefix + "/") for prefix in inside_controls)  # the label text inside a button is the button


def shared_testids(result: DiscoveryResult) -> set[str]:
    """Test ids carried by more than one element anywhere in the application (any view)."""
    seen: dict[str, int] = {}
    for page in result.pages:
        for el in page.elements:
            if el.get("testid"):
                seen[el["testid"]] = seen.get(el["testid"], 0) + max(int(el.get("counts", {}).get("testid", 1) or 1), 1)
    return {testid for testid, count in seen.items() if count > 1}


def build_locators(result: DiscoveryResult) -> list[LocatorSpec]:
    specs: list[LocatorSpec] = []
    used: set[str] = set()
    shared = shared_testids(result)
    for page in result.pages:
        specs.extend(_page_locators(page, used, shared))
    return specs


def _page_locators(page: PageSnapshot, used: set[str], shared: set[str] | None = None) -> list[LocatorSpec]:
    specs: list[LocatorSpec] = []
    controls = [el.get("xpath", "") for el in page.elements if el.get("xpath") and (el.get("tag") in _INTERACTIVE_TAGS or el.get("role") in _TEXT_ROLES | _INPUT_ROLES)]
    control_names = {_clean(el.get("name", "")).lower() for el in page.elements if el.get("role") in {"radio", "checkbox", "switch", "button", "tab", "option"} and el.get("name")}
    for el in page.elements:
        if not _interesting(el, controls, control_names):
            continue
        selectors, score = build_selectors(el, shared)
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
