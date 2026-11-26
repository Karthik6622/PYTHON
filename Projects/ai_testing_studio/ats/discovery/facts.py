"""What discovery actually SAW, in the form generation and repair need it.

* ``facts_digest`` - per view: signed in or not, how to reach it, headings, messages, readable text, controls and what a safe probe
  showed. Controls that are the same on most views (a sidebar menu) are listed once, not on every view, so the content of each view
  is never crowded out of the model's input.
* ``Evidence`` - the grounding index: is a piece of text something the application really shows (on this element, on this view,
  anywhere)? Test expectations are judged against it, never against what a model wrote in a test case.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Any

from ats.models import DiscoveryResult, LocatorSpec, PageSnapshot

_INTERACTIVE = {"button", "link", "textbox", "searchbox", "combobox", "spinbutton", "checkbox", "radio", "switch", "tab", "menuitem", "slider", "option"}
_HEADING_PREFIX = re.compile(r"^h[1-6]:\s*")


def norm(text: Any) -> str:
    """Case, spacing and surrounding quotes / punctuation do not make two texts different."""
    value = re.sub(r"\s+", " ", str(text or "")).strip().lower()
    return value.strip(" \t\"'`“”‘’.:;!?-–—")


def heading_texts(page: PageSnapshot) -> list[str]:
    return [t for t in (_HEADING_PREFIX.sub("", h).strip() for h in page.headings) if t]


def _control_key(el: dict[str, Any]) -> tuple[str, str]:
    return (el.get("role") or el.get("tag") or "", norm(el.get("name") or el.get("label") or el.get("text")))


def shared_controls(discovery: DiscoveryResult) -> set[tuple[str, str, bool]]:
    """(role, name, signed_in) of controls present on most views of the same kind: the application's navigation chrome."""
    result: set[tuple[str, str, bool]] = set()
    for signed in (True, False):
        pages = [p for p in discovery.pages if p.signed_in == signed]
        if len(pages) < 3:
            continue
        counts: dict[tuple[str, str], int] = {}
        for page in pages:
            for key in {_control_key(e) for e in page.elements if e.get("visible")}:
                counts[key] = counts.get(key, 0) + 1
        result |= {(role, name, signed) for (role, name), n in counts.items() if n == len(pages) and name}
    return result


def control_facts(el: dict[str, Any]) -> dict[str, Any]:
    data = {
        "role": el.get("role") or el.get("tag"), "name": el.get("name") or el.get("label") or el.get("text"), "type": el.get("type") or None,
        "placeholder": el.get("placeholder") or None, "required": el.get("required") or None, "disabled": el.get("disabled") or None,
        "options": (el.get("options") or [])[:12] or None, "maxlength": el.get("maxlength") or None, "pattern": el.get("pattern") or None,
        "min": el.get("min") or None, "max": el.get("max") or None, "checked": el.get("checked") or None,
        "validation_message": el.get("validation") or None,
    }  # fmt: skip
    return {k: v for k, v in data.items() if v not in (None, "", [], False)}


def view_facts(page: PageSnapshot, shared: set[tuple[str, str, bool]] | None = None, max_controls: int = 40) -> dict[str, Any]:
    shared = shared or set()
    controls = []
    for el in page.elements:
        role = el.get("role") or el.get("tag") or ""
        if not el.get("visible") or role not in _INTERACTIVE and el.get("tag") not in {"input", "select", "textarea", "button", "a"}:
            continue
        name = norm(el.get("name") or el.get("label") or el.get("text"))
        if (role, name, page.signed_in) in shared:
            continue
        if role == "link" and not name:
            continue
        controls.append(control_facts(el))
        if len(controls) >= max_controls:
            break
    facts: dict[str, Any] = {
        "page_key": page.page_key, "name": page.view_name, "signed_in": page.signed_in, "reached_by": page.reached_by, "title": page.title,
        "headings": heading_texts(page)[:8], "messages": page.messages[:6], "texts": page.texts[:25], "controls": controls,
    }  # fmt: skip
    if page.outcomes:
        facts["observed_outcomes"] = page.outcomes
    if page.forms:
        facts["forms"] = [{"submit": f.get("submit", ""), "fields": len(f.get("fields", []))} for f in page.forms[:4]]
    return {k: v for k, v in facts.items() if v not in ("", [], None)}


def facts_digest(discovery: DiscoveryResult, only: set[str] | None = None, max_controls: int = 40) -> dict[str, Any]:
    """``{"shared_controls": ..., "views": [...]}`` for the prompts of scenario, test case and script generation."""
    shared = shared_controls(discovery)
    pages = [p for p in discovery.pages if not only or p.page_key in only]
    chrome = {}
    for role, name, signed in sorted(shared):
        chrome.setdefault("after sign-in" if signed else "before sign-in", []).append(f"{role} '{name}'")
    return {
        "shared_controls_on_most_views": chrome,
        "views": [view_facts(p, shared, max_controls) for p in pages],
        "note": "Only what is listed here was observed. Anything else (messages after saving, results of actions, other texts) is unknown.",
    }  # fmt: skip


# ----------------------------------------------------------------------------------------
# grounding
# ----------------------------------------------------------------------------------------
def element_raw_texts(spec: LocatorSpec) -> list[str]:
    """The texts of this element as the application wrote them (original case), shortest first."""
    ev = spec.evidence or {}
    values = [spec.name, ev.get("accessible_name"), ev.get("text"), ev.get("label"), ev.get("placeholder"), ev.get("title"), *(ev.get("options") or [])]
    return sorted({str(v).strip(): None for v in values if v and str(v).strip()}, key=len)


def element_texts(spec: LocatorSpec) -> set[str]:
    """Every text the application showed for this element during discovery (normalised for comparing)."""
    return {n for n in (norm(v) for v in element_raw_texts(spec)) if n}


def closest_raw(value: str, spec: LocatorSpec, cutoff: float = 0.6) -> str:
    """The text this element really shows that is closest to ``value`` (original case), or ''."""
    raw = element_raw_texts(spec)
    by_norm = {norm(t): t for t in raw}
    near = difflib.get_close_matches(norm(value), list(by_norm), n=1, cutoff=cutoff)
    return by_norm[near[0]] if near else ""


@dataclass
class Evidence:
    """Index of everything discovery observed. Build once per generation / repair."""

    discovery: DiscoveryResult
    locators: dict[str, LocatorSpec] = field(default_factory=dict)
    view_texts: dict[str, set[str]] = field(init=False, default_factory=dict)
    app_texts: set[str] = field(init=False, default_factory=set)
    urls: list[str] = field(init=False, default_factory=list)
    titles: list[str] = field(init=False, default_factory=list)

    def __post_init__(self) -> None:
        for page in self.discovery.pages:
            texts = {norm(t) for t in [page.title, page.view_name, *heading_texts(page), *page.messages, *page.texts] if t}
            for el in page.elements:
                texts |= {norm(el.get(k)) for k in ("name", "label", "text", "placeholder", "title", "value", "validation") if el.get(k)}
                texts |= {norm(o) for o in el.get("options") or []}
            for outcome in page.outcomes:
                texts |= {norm(outcome.get("result"))} | {norm(m) for m in outcome.get("shown_messages", [])}
            texts.discard("")
            self.view_texts[page.page_key] = texts
            self.app_texts |= texts
            self.urls += [page.url, page.final_url]
            self.titles.append(norm(page.title))

    def level(self, value: str, spec: LocatorSpec | None = None, view: str = "") -> str:
        """How well the application backs this text: ``element`` (that element showed it), ``view`` (this view showed it), ``app`` (another
        view showed it) or ``""`` (nothing observed it)."""
        needle = norm(value)
        if not needle:
            return ""
        if spec is not None and self.shows(spec, value):
            return "element"
        if self._within(needle, self.view_texts.get(view or (spec.page_key if spec else ""), set())):
            return "view"
        return "app" if self._within(needle, self.app_texts) else ""

    @staticmethod
    def _within(needle: str, texts: set[str]) -> bool:
        """Equal to a text the page showed, or (for a longer phrase) a part of one. A short word is not 'shown' because it is part of a longer text."""
        return needle in texts or (len(needle) >= 12 and any(needle in t for t in texts))

    @staticmethod
    def shows(spec: LocatorSpec, value: str) -> bool:
        """What a Playwright text check does: the element's text CONTAINS the value, case-sensitively (whitespace collapsed)."""
        wanted = re.sub(r"\s+", " ", value or "").strip()
        return bool(wanted) and any(wanted in re.sub(r"\s+", " ", raw) for raw in element_raw_texts(spec))

    def url_supported(self, fragment: str) -> bool:
        needle = (fragment or "").strip().lower()
        return bool(needle) and any(needle in (u or "").lower() for u in self.urls)

    def title_supported(self, fragment: str) -> bool:
        needle = norm(fragment)
        return bool(needle) and any(needle in t for t in self.titles)

    def holders(self, value: str, view: str) -> list[LocatorSpec]:
        """Elements of ``view`` whose text contains exactly this text (best candidates to assert it on)."""
        return [s for s in self.locators.values() if s.page_key == view and self.shows(s, value)]


__all__ = ["Evidence", "element_texts", "facts_digest", "heading_texts", "norm", "shared_controls", "view_facts"]
