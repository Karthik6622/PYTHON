"""UI hierarchy (Appium page source) -> screens and elements with ranked, stable locators.

Locator ranking: 1 accessibility id, 2 resource id, 3 UiSelector attributes (text / description), 4 a SHORT attribute-based XPath as the last
resort. An absolute XPath (``/hierarchy/...``) is never produced, and a locator that matches several elements is ranked behind unique ones.
"""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

from ats.mobile.models import MobileElement, MobileError, MobileSelector
from ats.models import slugify

IGNORED_PACKAGES = {"com.android.systemui"}  # status bar and navigation bar are not part of the app
LAYOUT_CLASSES = ("ViewGroup", "FrameLayout", "LinearLayout", "RelativeLayout", "ConstraintLayout", "CoordinatorLayout", "View", "ComposeView", "CardView")
BOUNDS = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")
DYNAMIC_TEXT = re.compile(r"^[\d\s.,:/%$€£+\-()]+$")
# Controls that change or destroy something: exploration never taps them.
DESTRUCTIVE = re.compile(
    r"\b(delete|remove|log\s?out|logout|sign\s?out|signout|pay|buy|purchase|place\s+order|send|submit|reset|uninstall|erase|wipe|clear\s+data|unsubscribe|"
    r"deactivate|close\s+account|factory|format|terminate)\b",
    re.I,
)
NAV_HINT = re.compile(r"\b(next|continue|skip|get\s+started|start|home|search|menu|more|settings|profile|account|dashboard|explore|discover|browse|allow|got\s+it|ok)\b", re.I)
TAB_HINT = re.compile(r"(?i)\b(tab|navigation|nav|bottom|menu|drawer)\b")


@dataclass
class Node:
    cls: str
    resource_id: str = ""
    desc: str = ""
    text: str = ""
    hint: str = ""
    package: str = ""
    clickable: bool = False
    enabled: bool = True
    focusable: bool = False
    scrollable: bool = False
    checkable: bool = False
    password: bool = False
    selected: bool = False
    displayed: bool = True
    bounds: tuple[int, ...] = ()

    @property
    def short_class(self) -> str:
        return self.cls.rsplit(".", 1)[-1]

    @property
    def id_name(self) -> str:
        return self.resource_id.split("/", 1)[-1] if self.resource_id else ""


def parse_bounds(text: str) -> tuple[int, ...]:
    match = BOUNDS.search(text or "")
    return tuple(int(v) for v in match.groups()) if match else ()


def _flag(attributes: dict[str, str], name: str, default: bool = False) -> bool:
    value = attributes.get(name)
    return default if value is None else value.strip().lower() == "true"


def parse_page_source(xml: str) -> list[Node]:
    """Every node of an Appium UiAutomator2 page source. The XML comes from the app under test, so entity declarations are refused."""
    if not xml or "<!DOCTYPE" in xml or "<!ENTITY" in xml:
        raise MobileError("The screen could not be read (the page source was empty or unsafe).")
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise MobileError("The screen could not be read (the page source is not valid XML).") from exc
    nodes: list[Node] = []
    for item in root.iter():
        if item is root and item.tag == "hierarchy":
            continue
        attributes = item.attrib
        cls = attributes.get("class") or item.tag
        nodes.append(
            Node(
                cls=cls, resource_id=attributes.get("resource-id", ""), desc=attributes.get("content-desc", "").strip(), text=attributes.get("text", "").strip(),
                hint=attributes.get("hint", "").strip(), package=attributes.get("package", ""), clickable=_flag(attributes, "clickable") or _flag(attributes, "long-clickable"),
                enabled=_flag(attributes, "enabled", True), focusable=_flag(attributes, "focusable"), scrollable=_flag(attributes, "scrollable"),
                checkable=_flag(attributes, "checkable"), password=_flag(attributes, "password"), selected=_flag(attributes, "selected"),
                displayed=_flag(attributes, "displayed", True), bounds=parse_bounds(attributes.get("bounds", "")),
            )
        )
    return [n for n in nodes if n.package not in IGNORED_PACKAGES]


# ----------------------------------------------------------------------------------------
# safety
# ----------------------------------------------------------------------------------------
def _words(text: str) -> str:
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text or "")
    return re.sub(r"[_\-./:]+", " ", text)


def is_destructive(*labels: str) -> bool:
    """True when a control's label (text, description or resource id) says it deletes, pays, sends, submits, signs out or resets something."""
    return any(DESTRUCTIVE.search(_words(label)) for label in labels if label)


# ----------------------------------------------------------------------------------------
# elements
# ----------------------------------------------------------------------------------------
def role_of(node: Node) -> str:
    cls = node.short_class
    blob = f"{cls} {node.id_name}".lower()
    if "edittext" in blob or "textinput" in blob or node.password:
        return "textbox"
    if "checkbox" in blob:
        return "checkbox"
    if "switch" in blob or "togglebutton" in blob:
        return "switch"
    if "radiobutton" in blob:
        return "radio"
    if "spinner" in blob:
        return "dropdown"
    if "tab" in blob and node.clickable:
        return "tab"
    if "button" in blob or (node.clickable and node.text and cls == "TextView"):
        return "button"
    if "imageview" in blob and node.clickable:
        return "button"
    if "recyclerview" in blob or "listview" in blob or "scrollview" in blob or node.scrollable:
        return "list"
    if "imageview" in blob or "image" in blob:
        return "image"
    if cls == "TextView" or node.text:
        return "text"
    return "element"


def _is_dynamic(text: str) -> bool:
    return not text or len(text) > 60 or "\n" in text or bool(DYNAMIC_TEXT.match(text))


def _ui_literal(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def xpath_literal(value: str) -> str:
    if "'" not in value:
        return f"'{value}'"
    if '"' not in value:
        return f'"{value}"'
    return "concat(" + ", \"'\", ".join(f"'{part}'" for part in value.split("'")) + ")"


def _interesting(node: Node) -> bool:
    if not node.displayed:
        return False
    if node.short_class in LAYOUT_CLASSES and not (node.clickable or node.scrollable or node.desc):
        return False
    if "EditText" in node.cls or node.password:
        return True
    return bool(node.clickable or node.checkable or node.scrollable or node.desc or node.text or (node.focusable and node.resource_id))


def _name(node: Node) -> str:
    return node.desc or node.text or node.hint or _words(node.id_name).strip()


def selectors_for(node: Node, nodes: list[Node]) -> list[MobileSelector]:
    """Ranked locators of one node. Unique matches come first; within them: accessibility id, resource id, UiSelector, XPath."""
    same = lambda attr, value: sum(1 for n in nodes if getattr(n, attr) == value)  # noqa: E731
    found: list[MobileSelector] = []
    if node.desc:
        found.append(MobileSelector(strategy="accessibility_id", value=node.desc, unique=same("desc", node.desc) == 1))
    if node.resource_id:
        found.append(MobileSelector(strategy="id", value=node.resource_id, unique=same("resource_id", node.resource_id) == 1))
    if node.text and not _is_dynamic(node.text) and not node.password:
        count = sum(1 for n in nodes if n.text == node.text and n.cls == node.cls)
        found.append(MobileSelector(strategy="uiautomator", value=f"new UiSelector().className({_ui_literal(node.cls)}).text({_ui_literal(node.text)})", unique=count == 1))
    if node.desc:
        count = sum(1 for n in nodes if n.desc == node.desc and n.cls == node.cls)
        found.append(MobileSelector(strategy="uiautomator", value=f"new UiSelector().className({_ui_literal(node.cls)}).description({_ui_literal(node.desc)})", unique=count == 1))
    found.append(_xpath_selector(node, nodes))
    unique: list[MobileSelector] = []
    for selector in found:
        if selector.identity() not in {s.identity() for s in unique}:
            unique.append(selector)
    rank = {"accessibility_id": 0, "id": 1, "uiautomator": 2, "xpath": 3}
    return sorted(unique, key=lambda s: (not s.unique, rank[s.strategy]))[:5]


def _xpath_selector(node: Node, nodes: list[Node]) -> MobileSelector:
    """A short, attribute-based XPath. Only an element with no attribute at all gets a positional one (``(//Class)[n]``); never an absolute path."""
    cls = node.cls
    if node.desc:
        predicate, matches = f"@content-desc={xpath_literal(node.desc)}", [n for n in nodes if n.cls == cls and n.desc == node.desc]
    elif node.text and not _is_dynamic(node.text):
        predicate, matches = f"@text={xpath_literal(node.text)}", [n for n in nodes if n.cls == cls and n.text == node.text]
    elif node.resource_id:
        predicate, matches = f"@resource-id={xpath_literal(node.resource_id)}", [n for n in nodes if n.cls == cls and n.resource_id == node.resource_id]
    else:
        same_class = [n for n in nodes if n.cls == cls]
        index = next((i for i, n in enumerate(same_class, 1) if n is node), 1)
        return MobileSelector(strategy="xpath", value=f"(//{cls})[{index}]", unique=True)
    base = f"//{cls}[{predicate}]"
    if len(matches) == 1:
        return MobileSelector(strategy="xpath", value=base, unique=True)
    index = next((i for i, n in enumerate(matches, 1) if n is node), 1)
    return MobileSelector(strategy="xpath", value=f"({base})[{index}]", unique=True)


def build_elements(nodes: list[Node], screen_key: str) -> list[MobileElement]:
    """The interesting nodes of a screen as elements with unique keys, in reading order (top to bottom)."""
    chosen = [n for n in nodes if _interesting(n)]
    chosen.sort(key=lambda n: (n.bounds[1] if n.bounds else 0, n.bounds[0] if n.bounds else 0))
    elements: list[MobileElement] = []
    used: set[str] = set()
    for node in chosen:
        name = _name(node)
        role = role_of(node)
        base = f"{screen_key}.{slugify(name, role)[:40].strip('_') or role}_{role}"
        key, number = base, 2
        while key in used:
            key, number = f"{base}_{number}", number + 1
        used.add(key)
        elements.append(
            MobileElement(
                key=key, screen=screen_key, name=name[:120], role=role, resource_id=node.resource_id, accessibility_id=node.desc, text=node.text[:200], class_name=node.cls,
                package=node.package, clickable=node.clickable, enabled=node.enabled, focusable=node.focusable, scrollable=node.scrollable, checkable=node.checkable,
                password=node.password, bounds=list(node.bounds), selectors=selectors_for(node, nodes),
            )
        )
    return elements


def title_of(nodes: list[Node], fallback: str = "") -> str:
    """A readable screen title: a title-like view, else the first prominent text, else ``fallback``."""
    for node in nodes:
        if node.text and re.search(r"(?i)(title|toolbar|heading|header)", node.id_name) and not node.clickable:
            return node.text[:80]
    for node in sorted((n for n in nodes if n.text and "TextView" in n.cls and not n.clickable), key=lambda n: (n.bounds[1] if n.bounds else 0)):
        return node.text[:80]
    return fallback


def fingerprint_of(nodes: list[Node]) -> str:
    """Identity of a screen layout: the same fingerprint means the same screen (used to avoid recording a screen twice)."""
    parts = sorted({f"{n.cls}|{n.resource_id}|{n.desc or ('' if _is_dynamic(n.text) else n.text)}" for n in nodes if n.displayed})
    return hashlib.sha1("\n".join(parts).encode("utf-8")).hexdigest()[:16]  # noqa: S324 - not security relevant


def tap_candidates(elements: list[MobileElement], limit: int) -> list[MobileElement]:
    """Safe controls worth tapping to reach other screens: tabs and menu items first, then 'Next'-style buttons, then other labelled buttons.

    Text fields, switches, checkboxes and anything whose label looks destructive are never candidates."""
    ranked: list[tuple[int, int, MobileElement]] = []
    for order, element in enumerate(elements):
        if not element.clickable or not element.enabled or element.role in {"textbox", "checkbox", "switch", "radio", "dropdown", "list", "image"}:
            continue
        if is_destructive(element.name, element.text, element.accessibility_id, element.resource_id):
            continue
        if element.role == "tab" or TAB_HINT.search(element.resource_id):
            tier = 0
        elif NAV_HINT.search(element.name):
            tier = 1
        elif element.role == "button" and element.name:
            tier = 2
        else:
            continue
        ranked.append((tier, order, element))
    ranked.sort(key=lambda item: (item[0], item[1]))
    return [e for _, _, e in ranked[:limit]]


def blocked_controls(elements: list[MobileElement]) -> list[str]:
    """Labels of clickable controls that exploration deliberately skipped."""
    return [e.name for e in elements if e.clickable and e.name and is_destructive(e.name, e.text, e.accessibility_id, e.resource_id)]


def selector_dicts(element: MobileElement) -> list[dict[str, Any]]:
    return [s.model_dump() for s in element.selectors]


UI_ATTRIBUTE = re.compile(r'\.(text|description)\("((?:[^"\\]|\\.)*)"\)')


def element_present(nodes: list[Node], element: MobileElement) -> bool | None:
    """Does a recorded element still exist in a page source? ``None`` when none of its locators can be checked offline (XPath only)."""
    checked = False
    for selector in element.selectors:
        if selector.strategy == "accessibility_id":
            checked, hit = True, any(n.desc == selector.value for n in nodes)
        elif selector.strategy == "id":
            checked, hit = True, any(n.resource_id == selector.value for n in nodes)
        elif selector.strategy == "uiautomator":
            match = UI_ATTRIBUTE.search(selector.value)
            if not match:
                continue
            value = re.sub(r"\\(.)", r"\1", match.group(2))
            checked, hit = True, any((n.text if match.group(1) == "text" else n.desc) == value for n in nodes)
        else:
            continue
        if hit:
            return True
    return False if checked else None
