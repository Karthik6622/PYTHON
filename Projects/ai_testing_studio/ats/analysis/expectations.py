"""Rule-based repair of expectations that were never true.

A failed text check has two possible meanings: the application changed (a real defect) or the test claimed something the application
never showed (an invented expectation). Discovery tells them apart: if the expected text was observed on that element, the failure is a
regression and is left alone; if it never was, the test is wrong, and the failure message itself says what the page really shows
("Actual value: ..."). The repair is then exact and needs no model:

  * the expected text is replaced by what the element shows when the two are close (a different wording of the same thing);
  * unrelated wording is left for review; a visibility check does not prove a text or value expectation.

Every such repair is recorded with the reason, so a person can review what was corrected.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from ats.analysis.autofix_text import statement_span
from ats.discovery.facts import Evidence, closest_raw, norm
from ats.models import LocatorSpec, RepairEdit, RepairResult

EXPECTED = re.compile(r"expected to (?:contain text|have text|have value|contain value)\b[:\s]*['\"“](.+?)['\"”]?\s*(?:\n|$)", re.I | re.S)
EXPECTED_ALT = re.compile(r"(?:Expected (?:string|substring|value)|Expected)[:\s]+['\"“]?(.+?)['\"”]?\s*(?:\n|$)", re.I)
ACTUAL = re.compile(r"(?:Actual value|Received string|Received|Actual)[:\s]+['\"“]?(.*?)['\"”]?\s*(?:\n|Call log|$)", re.I)
URL_EXPECTED = re.compile(r"(?:Page URL|URL) expected to match[^\n]*", re.I)
SIMILAR = 0.5


@dataclass
class Claim:
    expected: str
    actual: str


def parse_claim(error: str) -> Claim | None:
    """The expected and actual text out of a Playwright assertion error."""
    text = error or ""
    match = EXPECTED.search(text) or EXPECTED_ALT.search(text)
    if not match:
        return None
    actual = ACTUAL.search(text)
    return Claim(match.group(1).strip(), (actual.group(1).strip() if actual else ""))


def similar(a: str, b: str) -> bool:
    x, y = norm(a), norm(b)
    return bool(x and y) and (x in y or y in x or difflib.SequenceMatcher(None, x, y).ratio() >= SIMILAR)


def repair_expectation(
    files: dict[str, str], test_case_id: str, element_key: str, action: str, error: str, spec: LocatorSpec | None, evidence: Evidence,
) -> tuple[RepairResult | None, str]:  # fmt: skip
    """``(repair, why)``. ``repair`` is None when the failure is not an invented expectation (``why`` says what it is instead)."""
    if action not in {"expect_text", "expect_value"} or spec is None:
        return None, ""
    claim = parse_claim(error)
    if claim is None or not claim.expected:
        return None, "the expected text could not be read from the error"
    view = spec.page_key
    if evidence.level(claim.expected, spec, view) == "element":
        return None, f"'{claim.expected}' was observed on this element during discovery: the application changed (reported as a defect)"
    method = "to_contain_text" if action == "expect_text" else "to_have_value"
    span = statement_span(files, test_case_id, element_key, method, claim.expected)
    if span is None:
        return None, "the check could not be located in the test file"
    path, segment, old_call = span
    own_best = closest_raw(claim.expected, spec)
    shown = claim.actual
    if action == "expect_value":
        return None, "an input value cannot be repaired from its label or visible text"
    if shown and own_best and norm(shown) == norm(own_best) and similar(claim.expected, shown) and norm(shown) != norm(claim.expected):
        new_call, note = f"{method}({shown!r})", f"expected text {claim.expected!r} was never observed; corrected to what the page shows: {shown!r}"
    elif own_best:
        new_call, note = f"{method}({own_best!r})", f"expected text {claim.expected!r} was never observed; corrected to the observed text {own_best!r}"
    else:
        return None, "no observed text supports this expectation; review the case rather than weakening the assertion"
    new_segment = segment.replace(old_call, new_call, 1)
    return RepairResult(verdict="fixed", explanation=note, edits=[RepairEdit(path=path, find=segment, replace=new_segment)]), note
