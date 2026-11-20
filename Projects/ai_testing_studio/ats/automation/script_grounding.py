"""Grounding of generated scripts: every step is checked against what discovery observed, and fixed or trimmed when it is not true.

A script is a walk through the application. This module walks the same path on paper:
  * the walk starts on the view of the first element; a click on a navigation control moves it to the view that control opens
    (from the recorded views), so each following step is checked against the RIGHT view;
  * an element of another view is replaced by its twin on the current view (the same menu item exists once per view) or the script
    stops there instead of waiting for an element that cannot be on screen;
  * an action must fit the element (no clicking a heading, no typing into a button): a fitting twin is used, otherwise the script stops;
  * an expected text must be something that element - or at least that view - was observed to show. Anything else is corrected to what
    the element really says, moved to the element that really carries it, or weakened to "is visible". The wording of the test case
    itself is never evidence.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Any

from ats.discovery.facts import Evidence, closest_raw, element_texts, norm
from ats.models import AutomationStep, LocatorSpec

CLICKABLE = {"button", "link", "tab", "menuitem", "menuitemradio", "menuitemcheckbox", "radio", "checkbox", "switch", "option", "treeitem"}
TYPEABLE = {"textbox", "searchbox", "spinbutton"}
ENV_RE = re.compile(r"\{\{env:[A-Za-z_][A-Za-z0-9_]*\}\}")
ASSERTION_PREFERENCE = ("heading", "alert", "status", "caption")


def role_of(spec: LocatorSpec) -> str:
    return (spec.role or spec.tag or "").lower()


def compatible(action: str, spec: LocatorSpec) -> bool:
    role, tag = role_of(spec), (spec.tag or "").lower()
    if action in {"click", "dblclick"}:
        return role in CLICKABLE or tag in {"button", "a", "summary"}
    if action in {"check", "uncheck"}:
        return role in {"checkbox", "radio", "switch"}
    if action in {"fill", "clear"}:
        return role in TYPEABLE or tag in {"input", "textarea"} and role not in CLICKABLE
    if action == "select":
        return role == "combobox" or tag == "select"
    if action == "press":
        return role in TYPEABLE | {"combobox", "button", "link"} or tag in {"input", "textarea"}
    return True  # hover and every expect_* work on any element


@dataclass
class Walk:
    """State of the paper walk through one script."""

    locators: dict[str, LocatorSpec]
    evidence: Evidence | None
    views: dict[str, Any]
    view: str = ""
    typed: set[str] = field(default_factory=set)  # values the script itself typed (an expect_value on them is true by construction)
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.by_view: dict[str, list[LocatorSpec]] = {}
        for spec in self.locators.values():
            self.by_view.setdefault(spec.page_key, []).append(spec)
        self.opens: dict[tuple[bool, str, str], str] = {}  # (signed_in, role, label) of a navigation control -> the view it opens
        for key, view in (self.views.get("views") or {}).items():
            steps = view.get("steps") or []
            if steps and steps[-1].get("role") != "url":
                self.opens[(bool(view.get("signed_in")), steps[-1].get("role", ""), norm(steps[-1].get("label")))] = key

    # ------------------------------------------------------------------ helpers
    def twin(self, spec: LocatorSpec, view: str, action: str = "") -> LocatorSpec | None:
        """The element of ``view`` that is the same thing as ``spec`` (same name and, for an action, a fitting role)."""
        wanted = element_texts(spec) or {norm(spec.name)}
        for other in self.by_view.get(view, []):
            if other.element_key == spec.element_key or (action and not compatible(action, other)):
                continue
            if role_of(other) == role_of(spec) and norm(other.name) == norm(spec.name) and norm(spec.name):
                return other
        for other in self.by_view.get(view, []):
            if other.element_key == spec.element_key or (action and not compatible(action, other)):
                continue
            if wanted & element_texts(other) and (not action or compatible(action, other)):
                return other
        return None

    def signed_in(self, view: str) -> bool:
        return bool(((self.views.get("views") or {}).get(view) or {}).get("signed_in"))

    # ------------------------------------------------------------------ one step
    def check(self, index: int, step: AutomationStep) -> tuple[AutomationStep | None, str]:
        """(the step to keep, or None and why the script must stop here)."""
        if not step.element:
            if step.action == "goto":
                self.view = ""  # a fresh page load: the next element decides the view again
            return step, ""
        spec = self.locators[step.element]
        # 1. the action must fit the element
        if not compatible(step.action, spec):
            fit = self.twin(spec, spec.page_key, step.action)
            if fit is None:
                return None, f"step {index}: '{step.action}' does not fit {role_of(spec) or 'this element'} '{spec.name}'"
            self.notes.append(f"Step {index}: {step.action} on '{spec.name}' (a {role_of(spec) or 'static element'}) was moved to the {role_of(fit)} with that name.")
            step, spec = step.model_copy(update={"element": fit.element_key}), fit
        # 2. the element must be on the view the walk is on
        if not self.view:
            self.view = spec.page_key
        elif spec.page_key != self.view:
            other = self.twin(spec, self.view, step.action if step.action in {"click", "dblclick", "check", "uncheck", "fill", "clear", "select", "press"} else "")
            if other is None:
                return None, f"step {index}: '{spec.name}' is on the '{spec.page_key}' view, but the script is on the '{self.view}' view"
            step, spec = step.model_copy(update={"element": other.element_key}), other
        # 3. expectations must be true to the observed page
        if step.action.startswith("expect_") and step.action in {"expect_text", "expect_value"} and not ENV_RE.search(step.value or ""):
            step = self.ground_text(index, step, spec)
        if step.action == "select" and step.value:
            step = self.ground_option(index, step, spec)
        if step.action in {"fill", "select"} and step.value:
            self.typed.add(norm(step.value))
        # 4. a click on a navigation control moves the walk to the view it opens
        if step.action in {"click", "check"}:
            target = self.opens.get((self.signed_in(self.view), role_of(spec), norm(spec.name)))
            if target:
                self.view = target
        return step, ""

    def ground_text(self, index: int, step: AutomationStep, spec: LocatorSpec) -> AutomationStep:
        value = (step.value or "").strip()
        if step.action == "expect_value" and norm(value) in self.typed:
            return step
        if self.evidence is None:
            return step
        level = self.evidence.level(value, spec, spec.page_key)
        if level == "element":
            return step
        if step.action == "expect_text":
            for holder in sorted(self.evidence.holders(value, spec.page_key), key=lambda s: (role_of(s) not in ASSERTION_PREFERENCE, s.element_key)):
                self.notes.append(f"Step {index}: '{value}' is shown by '{holder.name or holder.element_key}', so the check moved to that element.")
                return step.model_copy(update={"element": holder.element_key})
            near = closest_raw(value, spec)
            if near:
                self.notes.append(f"Step {index}: expected text {value!r} corrected to what '{spec.name}' shows: {near!r}.")
                return step.model_copy(update={"value": near})
        self.notes.append(f"Step {index}: {value!r} was never observed on '{spec.name}'; the check is limited to the element being visible.")
        return step.model_copy(update={"action": "expect_visible", "value": None})

    def ground_option(self, index: int, step: AutomationStep, spec: LocatorSpec) -> AutomationStep:
        options = list((spec.evidence or {}).get("options") or [])
        if not options or norm(step.value) in {norm(o) for o in options}:
            return step
        near = difflib.get_close_matches(step.value or "", options, n=1, cutoff=0.5)
        chosen = near[0] if near else options[0]
        self.notes.append(f"Step {index}: option {step.value!r} does not exist in '{spec.name}'; {chosen!r} is used.")
        return step.model_copy(update={"value": chosen})

    def ground_page_checks(self, index: int, step: AutomationStep) -> tuple[AutomationStep | None, str]:
        """expect_url_contains / expect_title_contains must name something the application's URLs or titles contain."""
        value = (step.value or "").strip()
        if ENV_RE.search(value) or self.evidence is None:
            return step, ""
        supported = self.evidence.url_supported(value) if step.action == "expect_url_contains" else self.evidence.title_supported(value)
        if supported:
            return step, ""
        self.notes.append(f"Step {index}: {step.action} {value!r} was not observed anywhere in the application and was left out.")
        return None, ""
