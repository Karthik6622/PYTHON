"""Failure analysis: gather evidence, check the locator against the failing DOM, classify with rules plus the AI agent."""

from __future__ import annotations

import json
from typing import Any

from ats.ai.agents import FailureAnalysisAgent
from ats.analysis import dom
from ats.analysis.classifier import classify
from ats.analysis.findings import Finding
from ats.errors import StudioError
from ats.execution.executor import ExecutionContext
from ats.execution.junit import read_dom
from ats.logging_setup import get_logger
from ats.models import FailureAnalysis, FailureCategory, LocatorSpec, Selector
from ats.repository import Repository
from ats.security import mask, mask_obj

LOGGER = get_logger("analysis.pipeline")
MAX_SCREENSHOT_BYTES = 1_500_000
DETERMINISTIC = {FailureCategory.TEST_DATA.value, FailureCategory.ENVIRONMENT.value}


def locator_index(ctx: ExecutionContext, repo: Repository) -> dict[str, LocatorSpec]:
    """Locators as they exist in the executed files (the source of truth), enriched with discovery evidence."""
    known = {spec.element_key: spec for spec in repo.list_locators(ctx.project.id)}
    try:
        file_entries = json.loads(ctx.files.get("config/locators.json", "{}"))
    except ValueError:
        file_entries = {}
    index: dict[str, LocatorSpec] = dict(known)
    for key, entry in file_entries.items():
        try:
            preferred = Selector.model_validate(entry["preferred"])
            alternatives = [Selector.model_validate(a) for a in entry.get("alternatives", [])]
        except (KeyError, ValueError, TypeError):
            continue
        base = known.get(key)
        data = base.model_dump() if base else {"element_key": key}
        data.update(
            {
                "preferred": preferred, "alternatives": alternatives, "page_key": entry.get("page", data.get("page_key", "")),
                "intent": entry.get("intent") or data.get("intent", ""), "role": entry.get("role") or data.get("role", ""),
                "name": entry.get("name") or data.get("name", ""),
            }
        )  # fmt: skip
        index[key] = LocatorSpec.model_validate(data)
    return index


def script_excerpt(files: dict[str, str], test_case_id: str, lines: int = 55) -> str:
    needle = test_case_id.lower()
    for rel, content in sorted(files.items()):
        if not rel.endswith((".py", ".ts", ".js", ".java")) or not any(m in rel for m in ("tests/", "src/test/", "test/")):
            continue
        rows = content.splitlines()
        for index, row in enumerate(rows):
            if needle in row.lower():
                return mask("\n".join(rows[max(index - 2, 0) : index + lines]))
    return ""


def read_screenshot(ctx: ExecutionContext, evidence: dict[str, Any]) -> bytes | None:
    rel = evidence.get("screenshot")
    if not rel:
        return None
    path = (ctx.workdir / rel).resolve()
    if ctx.workdir.resolve() not in path.parents or not path.is_file() or path.stat().st_size > MAX_SCREENSHOT_BYTES:
        return None
    return path.read_bytes()


class FailureAnalyzer:
    def __init__(self, repo: Repository, agent: FailureAnalysisAgent | None = None) -> None:
        self.repo = repo
        self.agent = agent or FailureAnalysisAgent(repository=repo)

    # ------------------------------------------------------------------ evidence
    def build(self, ctx: ExecutionContext, row: dict[str, Any], index: dict[str, LocatorSpec]) -> Finding:
        evidence = row.get("evidence") or {}
        failure = evidence.get("failure") or {}
        key = str(failure.get("element") or "")
        action = str(failure.get("action") or "")
        error = mask(failure.get("error") or row.get("message") or "")
        html = read_dom(ctx.workdir, evidence)
        old = index.get(key) if key else None
        check: dict[str, Any] = {"checked": False}
        candidates: list[dict[str, Any]] = []
        in_dom: bool | None = None
        notes: list[str] = []
        if old is not None and html:
            results, current = dom.analyze_failure_dom(html, str(failure.get("url") or ""), old.all_selectors())
            if results:
                counts = [int(r.get("count", 0)) for r in results]
                in_dom = counts[0] > 0
                check = {
                    "checked": True, "preferred_count": counts[0], "alternative_counts": counts[1:],
                    "any_alternative_matches": any(c > 0 for c in counts[1:]), "preferred": old.preferred.display(),
                }  # fmt: skip
                candidates = dom.rank_candidates(old, current)
            else:
                notes.append("The failing DOM could not be inspected.")
        elif old is None and key:
            notes.append(f"Element '{key}' is not present in the locator file.")
        elif not html:
            notes.append("No DOM snapshot was captured for this failure.")
        hint = classify(error, action, key, in_dom, [str(c) for c in failure.get("console", [])])
        return Finding(
            test_case_id=row["test_case_id"], result=row, failure=failure, element_key=key, action=action, error=error, html=html,
            old_spec=old, check=check, candidates=candidates, hint=hint, notes=notes,
        )  # fmt: skip

    # ------------------------------------------------------------------ classification
    def analyze(self, ctx: ExecutionContext, finding: Finding, evidence: dict[str, Any] | None = None) -> Finding:
        evidence = evidence or finding.result.get("evidence") or {}
        screenshot = read_screenshot(ctx, evidence)
        cases = {c.test_case_id: c for c in self.repo.list_test_cases(ctx.project.id)}
        case = cases.get(finding.test_case_id)
        payload = {
            "test_case": (
                case.model_dump(include={"test_case_id", "title", "steps", "expected_result", "preconditions", "test_data", "test_type"})
                if case else {"test_case_id": finding.test_case_id, "title": finding.result.get("test_name", "")}
            ),
            "executed_steps": (evidence.get("steps") or [])[-30:],
            "script_excerpt": script_excerpt(ctx.files, finding.test_case_id),
            "error": {
                "message": finding.error, "element": finding.element_key, "action": finding.action,
                "url": finding.url, "title": finding.failure.get("title", ""),
            },
            "logs": {"console": [mask(str(c))[:300] for c in finding.failure.get("console", [])][-15:]},
            "dom_excerpt": dom.excerpt(finding.html) if finding.html else "",
            "previous_locator": (
                {"element_key": finding.element_key, "preferred": finding.old_spec.preferred.model_dump(exclude_none=True),
                 "alternatives": [s.model_dump(exclude_none=True) for s in finding.old_spec.alternatives],
                 "intent": finding.old_spec.intent, "check_against_failing_dom": finding.check}
                if finding.old_spec else {}
            ),
            "locator_candidates": finding.candidates,
            "rule_based_hint": finding.hint.as_dict(),
        }  # fmt: skip
        try:
            analysis = self.agent.analyze(mask_obj(payload), ctx.project.id, screenshot)
            finding.ai_used = True
        except StudioError as exc:
            LOGGER.warning("AI failure analysis unavailable for %s: %s", finding.test_case_id, exc.user_message)
            finding.notes.append("AI analysis was unavailable; the classification comes from deterministic rules only.")
            analysis = FailureAnalysis(
                category=FailureCategory(finding.hint.category), confidence=min(finding.hint.confidence, 0.6), summary=finding.hint.reason,
                reasoning=finding.hint.reason, evidence_used=["error message", "DOM check"] if finding.check.get("checked") else ["error message"],
                insufficient_evidence=finding.hint.category == FailureCategory.UNKNOWN.value, automation_fixable=finding.hint.locator_suspect,
                recommended_action="Review the failure evidence manually.",
            )  # fmt: skip
        finding.analysis = self.reconcile(finding, analysis, screenshot is not None)
        return finding

    @staticmethod
    def reconcile(finding: Finding, analysis: FailureAnalysis, has_screenshot: bool) -> FailureAnalysis:
        """Deterministic evidence outranks the model: it can refine a classification but not contradict a proven fact."""
        hint = finding.hint
        if hint.category in DETERMINISTIC and hint.confidence >= 0.9 and analysis.category.value != hint.category:
            finding.notes.append(f"Classification set to {hint.category}: {hint.reason}")
            analysis.category = FailureCategory(hint.category)
            analysis.confidence = max(analysis.confidence, hint.confidence)
        if analysis.category == FailureCategory.LOCATOR_DRIFT and finding.check.get("checked") and finding.check.get("preferred_count", 0) > 0:
            finding.notes.append("The locator still matches the failing page, so this is not locator drift.")
            analysis.category = FailureCategory(hint.category) if hint.category != FailureCategory.LOCATOR_DRIFT.value else FailureCategory.TIMEOUT
            analysis.automation_fixable = False
        if analysis.category == FailureCategory.LOCATOR_DRIFT and not finding.element_key:
            analysis.category = FailureCategory.UNKNOWN
            analysis.automation_fixable = False
        if not finding.html or not has_screenshot:
            analysis.insufficient_evidence = analysis.insufficient_evidence or not finding.html
            if not finding.html:
                analysis.confidence = min(analysis.confidence, 0.5)
        if analysis.category not in {FailureCategory.LOCATOR_DRIFT, FailureCategory.AUTOMATION_ISSUE}:
            analysis.automation_fixable = False
        return analysis
