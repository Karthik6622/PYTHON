"""Grounding of generated test cases in what discovery observed.

A model writes test cases from prose, and prose invents: a heading called "Settle" where the page says "Settings", an error text nobody
saw, a signed-in control on a public view. This pass looks at every case and, for the view it belongs to,
  * resolves ``related_page`` to a real view,
  * adds the sign-in precondition of signed-in views,
  * corrects a quoted text to the closest text that view really shows (and says so in the tags),
  * tags a quoted text nothing observed (``unverified-text``): the automation step then asserts only what is certain.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Any

from ats.discovery.facts import Evidence, heading_texts, norm
from ats.generation.scenarios import page_names, resolve_page
from ats.models import DiscoveryResult, Scenario, TestCase

QUOTED = re.compile(r"\"([^\"\n]{2,80})\"|“([^”\n]{2,80})”|‘([^’\n]{2,80})’|(?<![\w])'([^'\n]{2,80})'(?![\w])")
CHECK_STEP = re.compile(r"^\s*(?:\d+[.)]\s*)?(verify|check|assert|confirm|ensure|expect|observe|validate|see that|make sure)\b", re.I)
SIGN_IN_WORDS = re.compile(r"sign(ed)?[ -]?in|log(ged)?[ -]?in", re.I)
ENV = re.compile(r"\{\{env:[^}]+\}\}")


@dataclass
class GroundingReport:
    corrected: int = 0
    unverified: int = 0
    unresolved_view: int = 0


def view_strings(page: Any) -> list[str]:
    """The texts of a view as the application wrote them (original case), most meaningful first."""
    out = [*heading_texts(page), *page.messages, *page.texts]
    for el in page.elements:
        if el.get("visible"):
            out += [str(el.get(k)) for k in ("name", "label", "text", "placeholder") if el.get(k)]
    for outcome in page.outcomes:
        out += [outcome.get("result", ""), *outcome.get("shown_messages", [])]
    return [s for s in dict.fromkeys(s.strip() for s in out) if s]


def closest(claim: str, candidates: list[str]) -> str:
    wanted, best, best_score = norm(claim), "", 0.0
    for text in candidates:
        score = difflib.SequenceMatcher(None, wanted, norm(text)).ratio()
        if score > best_score:
            best, best_score = text, score
    return best if best_score >= 0.6 else ""


def _claims(text: str) -> list[tuple[str, str]]:
    """(whole match, inner text) for every quoted text."""
    return [(m.group(0), next(g for g in m.groups() if g)) for m in QUOTED.finditer(text or "")]


def ground_case(case: TestCase, scenario: Scenario | None, discovery: DiscoveryResult, evidence: Evidence, names: dict[str, str], report: GroundingReport) -> TestCase:
    known = {p.page_key for p in discovery.pages}
    pages = {p.page_key: p for p in discovery.pages}
    view = resolve_page(case.related_page, known, names)
    if view not in known and scenario is not None:
        view = resolve_page(scenario.page, known, names)
    page = pages.get(view)
    if page is None:
        report.unresolved_view += 1
        return case
    update: dict[str, Any] = {"related_page": view}
    tags = list(case.tags)
    preconditions = list(case.preconditions)
    if page.signed_in and not any(SIGN_IN_WORDS.search(p) for p in preconditions):
        preconditions.insert(0, "Signed in with the test account")
    update["preconditions"] = preconditions
    typed = {norm(v) for v in case.test_data.values()}
    candidates = view_strings(page)
    steps, expected = list(case.steps), case.expected_result
    corrected = unverified = 0

    def fix(text: str) -> str:
        nonlocal corrected, unverified
        for whole, inner in _claims(text):
            if ENV.search(inner) or norm(inner) in typed or evidence.level(inner, None, view) in {"view", "element"}:
                continue
            if evidence.level(inner, None, view) == "app" and len(norm(inner)) <= 3:
                continue
            near = closest(inner, candidates)
            if near and norm(near) != norm(inner):
                text = text.replace(whole, whole.replace(inner, near))
                corrected += 1
            else:
                unverified += 1
        return text

    expected = fix(expected)
    steps = [fix(s) if CHECK_STEP.match(s) else s for s in steps]
    report.corrected += corrected
    report.unverified += unverified
    if corrected and "text-corrected" not in tags:
        tags.append("text-corrected")
    if unverified and "unverified-text" not in tags:
        tags.append("unverified-text")
    update.update({"steps": steps, "expected_result": expected, "tags": tags})
    return case.model_copy(update=update)


def ground_cases(cases: list[TestCase], scenarios: list[Scenario], discovery: DiscoveryResult, locators: dict[str, Any] | None = None) -> tuple[list[TestCase], GroundingReport]:
    evidence = Evidence(discovery, locators or {})
    names = page_names(discovery)
    by_id = {s.scenario_id: s for s in scenarios}
    report = GroundingReport()
    return [ground_case(c, by_id.get(c.scenario_id), discovery, evidence, names, report) for c in cases], report
