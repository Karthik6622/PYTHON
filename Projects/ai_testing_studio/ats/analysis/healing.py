"""Self-healing engine.

Scope is deliberately narrow: it may replace the *selector* of an element that no longer matches the page. It never edits
assertions, expected values, test data or test logic, and a test that passes only after healing is reported as HEALED, not PASS.
"""

from __future__ import annotations

import html as html_lib
import json
import re
import threading
from collections.abc import Callable
from typing import Any

from ats.ai.agents import SelfHealingAgent
from ats.analysis import dom
from ats.analysis.classifier import RuleHint
from ats.analysis.findings import Finding
from ats.analysis.patching import LOCATOR_FILE, PatchError, entry_diff, patch_locators
from ats.analysis.pipeline import FailureAnalyzer, locator_index, read_screenshot
from ats.automation.bundle_store import EXCLUDED_DIRS, MAX_FILE_BYTES, BundleStore, is_secret
from ats.config import get_settings
from ats.errors import NotFoundError, StudioError
from ats.execution.executor import ExecutionContext, ExecutionService, compute_totals, run_dir
from ats.logging_setup import get_logger
from ats.models import HEALABLE_CATEGORIES, FailureCategory, Selector, Status
from ats.repository import Project, Repository
from ats.security import mask, mask_obj

LOGGER = get_logger("analysis.healing")
_NO_HINT = RuleHint(FailureCategory.UNKNOWN.value, 0.0, "")
MAX_PATCHES_PER_RUN = 6
ASSERTION_MIN_CONFIDENCE = 0.8
_QUOTED = re.compile(r"""["']([^"']{2,})["']""")


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(text or "")).strip().lower()


def is_grounded(selector: Selector, html: str) -> bool:
    """Every literal the proposal relies on must exist in the page. This blocks invented attributes and text."""
    page = normalise(html)
    if selector.kind == "role":
        return not selector.name or normalise(selector.name) in page
    if selector.kind in {"css", "xpath"}:
        literals = _QUOTED.findall(selector.value)
        ids = re.findall(r"#([\w-]+)", selector.value) if selector.kind == "css" else []
        return all(normalise(x) in page for x in [*literals, *ids])
    return normalise(selector.value) in page


class HealingEngine:
    def __init__(
        self,
        repo: Repository,
        executor: ExecutionService,
        analyzer: FailureAnalyzer,
        agent: SelfHealingAgent | None = None,
        store: BundleStore | None = None,
    ) -> None:
        self.repo = repo
        self.executor = executor
        self.analyzer = analyzer
        self.agent = agent or SelfHealingAgent(repository=repo)
        self.store = store or BundleStore()

    # ------------------------------------------------------------------ eligibility
    @staticmethod
    def eligible(finding: Finding) -> tuple[bool, str]:
        if finding.analysis.category not in HEALABLE_CATEGORIES:
            return False, f"{finding.category} is not something locator healing can fix."
        if not finding.element_key or finding.old_spec is None:
            return False, "The failing element is not in the locator file."
        if not finding.html:
            return False, "No DOM snapshot was captured, so a replacement cannot be validated."
        if not finding.check.get("checked"):
            return False, "The failing DOM could not be inspected."
        if finding.check.get("preferred_count", 0) > 0:
            return False, "The locator still matches the page."
        if not finding.candidates:
            return False, "No element on the failing page resembles the one the test used."
        return True, ""

    @staticmethod
    def required_confidence(finding: Finding) -> float:
        base = get_settings().healing.min_confidence
        return max(base, ASSERTION_MIN_CONFIDENCE) if finding.action.startswith("expect_") else base

    # ------------------------------------------------------------------ proposal
    def propose(self, ctx: ExecutionContext, finding: Finding, previous: list[dict[str, Any]]) -> dict[str, Any]:
        """Ask the agent for a replacement and keep it only if it is grounded in the DOM and matches exactly one element."""
        old = finding.old_spec
        assert old is not None
        payload = {
            "element_key": finding.element_key, "intended_action": finding.action, "element_intent": old.intent or old.name,
            "old_locator": {"preferred": old.preferred.model_dump(exclude_none=True), "alternatives": [s.model_dump(exclude_none=True) for s in old.alternatives]},
            "error": finding.error, "page_url": finding.url, "dom_excerpt": dom.excerpt(finding.html), "candidates": finding.candidates,
            "previous_attempts": previous,
        }  # fmt: skip
        screenshot = read_screenshot(ctx, finding.result.get("evidence") or {})
        try:
            proposal = self.agent.propose(mask_obj(payload), ctx.project.id, screenshot)
        except StudioError as exc:
            return {"declined": f"The AI model could not propose a fix: {exc.user_message}", "kind": "model_error"}
        if proposal.behavior_changed:
            return {"declined": proposal.explanation or "The page behaviour changed; this is not a locator problem.", "kind": "behavior_changed"}
        tried = {(p.get("selector") or {}).get("value") for p in previous}
        needed = self.required_confidence(finding)
        usable = []
        for item in proposal.proposals[:3]:
            same = item.selector.identity() == old.preferred.identity()
            if same or item.selector.value in tried:
                continue
            usable.append(item)
        if not usable:
            return {"declined": proposal.explanation or "No usable replacement was proposed.", "kind": "no_proposal"}
        checks = dom.validate_in_html(finding.html, [p.selector for p in usable])
        reasons = []
        for item, outcome in zip(usable, checks, strict=False):
            count = int(outcome.get("count", 0))
            if item.confidence < needed:
                reasons.append(f"{item.selector.display()}: confidence {item.confidence:.2f} is below the required {needed:.2f}")
            elif not is_grounded(item.selector, finding.html):
                reasons.append(f"{item.selector.display()}: uses text or attributes that are not on the page")
            elif count != 1:
                reasons.append(f"{item.selector.display()}: matches {count} elements instead of exactly one")
            else:
                return {
                    "selector": item.selector, "confidence": item.confidence, "reason": item.reason or proposal.explanation,
                    "explanation": proposal.explanation,
                    "validation": {"dom_matches": count, "visible": int(outcome.get("visible", 0)), "grounded": True, "required_confidence": needed},
                }  # fmt: skip
        if not checks:
            reasons.append("The proposed selectors could not be validated against the failing DOM.")
        return {"declined": "; ".join(reasons) or "No proposal passed validation.", "kind": "failed_validation"}

    # ------------------------------------------------------------------ orchestration (policy applied by the caller)
    def heal(
        self,
        ctx: ExecutionContext,
        findings: list[Finding],
        policy: str,
        on_verified: Callable[[ExecutionContext, list[int]], None] | None = None,
    ) -> list[int]:
        """Try to heal the given findings. Returns ids of healing records created."""
        settings = get_settings().healing
        selenium = ctx.framework.startswith("selenium")
        files = dict(ctx.files)
        queue = [f for f in findings if f.analysis.category in HEALABLE_CATEGORIES]
        created: list[int] = []
        verified: list[int] = []
        done_keys: set[str] = set()
        followups: list[Finding] = []
        patches = 0
        while queue and patches < MAX_PATCHES_PER_RUN:
            first = queue.pop(0)
            if first.element_key in done_keys:
                first.healing = first.healing or {"status": "skipped", "message": "Element already handled in this run."}
                continue
            group = [first] + [f for f in queue if f.element_key == first.element_key]
            queue = [f for f in queue if f.element_key != first.element_key]
            done_keys.add(first.element_key)
            ok, why = self.eligible(first)
            if not ok:
                for f in group:
                    f.healing = {"status": "not_attempted", "message": why}
                continue
            previous: list[dict[str, Any]] = []
            for attempt in range(1, max(settings.max_attempts, 1) + 1):
                outcome = self.propose(ctx, first, previous)
                if "declined" in outcome:
                    message = mask(outcome["declined"])
                    for f in group:
                        f.healing = {"status": "declined", "message": message}
                    if outcome.get("kind") == "behavior_changed":
                        for f in group:
                            f.analysis.category = FailureCategory.APPLICATION_DEFECT
                            f.analysis.automation_fixable = False
                            f.notes.append("The healing agent reported that the page behaviour changed; reclassified as a likely application defect.")
                    break
                selector: Selector = outcome["selector"]
                try:
                    patched, old_entry, new_entry = patch_locators(files, first.element_key, selector, selenium)
                except PatchError as exc:
                    previous.append({"selector": selector.model_dump(exclude_none=True), "result": str(exc)})
                    continue
                ids = [f.test_case_id for f in group]
                record = self.repo.create_healing(
                    ctx.project.id, ctx.execution_id, test_case_ids=ids, element_key=first.element_key, old_locator=old_entry.get("preferred", {}),
                    new_locator=new_entry.get("preferred", {}), reason=mask(outcome["reason"]), confidence=outcome["confidence"],
                    evidence={"error": first.error, "page_url": first.url, "check": first.check, "candidates": first.candidates[:4], "analysis": first.analysis.summary},
                    validation=outcome["validation"], original_code=_dump(old_entry), proposed_code=entry_diff(first.element_key, old_entry, new_entry),
                    status="proposed",
                )  # fmt: skip
                created.append(record)
                self.repo.audit(ctx.project.id, "system", "healing.proposed", "healing", {"id": record, "element": first.element_key, "tests": ids})
                if policy == "manual":
                    for f in group:
                        f.healing = {"id": record, "status": "proposed", "message": "A fix was proposed and is waiting for approval."}
                    break
                patches += 1
                result = self._verify(ctx, record, patched, group, queue, followups)
                if result["passed"]:
                    files = patched
                    verified.append(record)
                    break
                previous.append({"selector": selector.model_dump(exclude_none=True), "result": result["message"]})
            else:
                for f in group:
                    f.healing = f.healing or {"status": "failed", "message": "No proposed fix made the test pass."}
        for follow in followups:
            if follow.origin is not None and follow.healing:
                follow.origin.healing = dict(follow.healing)
        self._totals(ctx.execution_id)
        if verified and policy == "auto_pr" and on_verified is not None:
            try:
                on_verified(ctx, verified)
            except StudioError as exc:
                self.repo.audit(ctx.project.id, "system", "healing.pr_failed", "healing", {"error": exc.user_message})
        return created

    # ------------------------------------------------------------------ verification by rerun
    def _verify(
        self, ctx: ExecutionContext, healing_id: int, files: dict[str, str], group: list[Finding], queue: list[Finding], followups: list[Finding]
    ) -> dict[str, Any]:
        """Rerun only the affected test cases with the patched locator file. HEALED means: failed before, passes now.

        A test that gets past the healed step and then fails on a different element counts as progress for this fix; the new
        failure is analysed and queued as its own healing candidate.
        """
        ids = [f.test_case_id for f in group]
        self.repo.update_healing(healing_id, status="running")
        rerun_id = self.executor.create(
            ctx.project, ctx.framework, ctx.browser, bundle_id=ctx.bundle_id, source="healing", kind="rerun", parent_id=ctx.execution_id, mode=ctx.mode
        )
        self.repo.update_healing(healing_id, rerun_execution_id=rerun_id)
        rerun_ctx = self.executor.execute(
            rerun_id, ctx.project, files, ctx.secrets, ctx.framework, ctx.browser, ctx.bundle_id, test_case_ids=ids, mode=ctx.mode
        )
        if rerun_ctx is None:
            error = mask((self.repo.get_execution(rerun_id) or {}).get("error", "The rerun could not be completed."))
            self.repo.update_healing(healing_id, status="failed", outcome="rerun_error", validation=self._merge_validation(healing_id, {"rerun_error": error}))
            for f in group:
                f.healing = {"id": healing_id, "status": "failed", "message": error}
            return {"passed": False, "message": f"rerun error: {error[:200]}"}
        rows = {r["test_case_id"]: r for r in self.repo.list_results(rerun_id)}
        index = locator_index(rerun_ctx, self.repo)
        healed = progressed = 0
        message = ""
        for f in group:
            row = rows.get(f.test_case_id) or {"status": Status.SKIPPED.value, "message": "No result was reported"}
            if row["status"] == Status.PASS.value:
                healed += 1
                f.healing = {"id": healing_id, "status": "verified", "message": f"Passed after replacing the locator for {f.element_key}.", "rerun_execution_id": rerun_id}
                self._mark_healed(ctx, f, healing_id, rerun_id)
                continue
            follow = self.analyzer.build(rerun_ctx, row, index) if row["status"] == Status.FAIL.value else None
            if follow is not None and follow.element_key and follow.element_key != f.element_key:
                progressed += 1
                f.healing = {"id": healing_id, "status": "partial", "message": f"The fix worked, but the test then failed at '{follow.element_key}'.", "rerun_execution_id": rerun_id}
                self.analyzer.analyze(rerun_ctx, follow)
                follow.origin = f
                queue.append(follow)
                followups.append(follow)
            else:
                message = f"{f.test_case_id} is still {row['status']}: {mask(str(row.get('message', '')))[:160]}"
                f.healing = {"id": healing_id, "status": "failed", "message": message, "rerun_execution_id": rerun_id}
        ok = healed + progressed == len(group)
        outcome = "rerun_passed" if healed == len(group) else "rerun_progress" if ok else "rerun_failed"
        self.repo.update_healing(healing_id, status="verified" if ok else "failed", outcome=outcome)
        self.repo.audit(ctx.project.id, "system", "healing.verified" if ok else "healing.failed", "healing", {"id": healing_id, "rerun": rerun_id, "outcome": outcome})
        return {"passed": ok, "message": message}

    def _mark_healed(self, ctx: ExecutionContext, finding: Finding, healing_id: int, rerun_id: str) -> None:
        stored = finding.result.get("analysis") or finding.to_dict()
        details = {
            **(finding.result.get("details") or {}), "healing_id": healing_id, "rerun_execution_id": rerun_id,
            "original_status": Status.FAIL.value, "original_message": finding.result.get("message", ""),
        }  # fmt: skip
        self.repo.update_result(
            ctx.execution_id, finding.test_case_id, status=Status.HEALED.value, message=finding.healing["message"], details=details,
            analysis={**stored, "healing": finding.healing},
        )

    def _merge_validation(self, healing_id: int, extra: dict[str, Any]) -> dict[str, Any]:
        record = self.repo.get_healing(healing_id) or {}
        return {**record.get("validation", {}), **extra}

    def _totals(self, execution_id: str) -> None:
        execution = self.repo.get_execution(execution_id) or {}
        rows = self.repo.list_results(execution_id)
        totals = compute_totals(rows, float(execution.get("duration") or 0.0))
        if execution.get("totals", {}).get("note"):
            totals["note"] = execution["totals"]["note"]
        self.repo.update_execution(execution_id, totals=totals)

    # ------------------------------------------------------------------ human-in-the-loop operations
    def load_files(self, project: Project, execution: dict[str, Any]) -> dict[str, str]:
        """The exact files that were executed (workspace snapshot), falling back to the stored bundle."""
        workspace = run_dir(project.id, execution["id"]) / "workspace"
        files: dict[str, str] = {}
        if workspace.is_dir():
            for path in sorted(workspace.rglob("*")):
                if not path.is_file():
                    continue
                parts = path.relative_to(workspace).parts
                rel = "/".join(parts)
                if any(p in EXCLUDED_DIRS for p in parts[:-1]) or is_secret(rel) or path.stat().st_size > MAX_FILE_BYTES:
                    continue
                try:
                    files[rel] = path.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
        if LOCATOR_FILE not in files and execution.get("bundle_id") and self.store.exists(project.id, execution["bundle_id"]):
            files = self.store.read_all(project.id, execution["bundle_id"])
        if LOCATOR_FILE not in files:
            raise NotFoundError("The files of that execution are no longer available.")
        return files

    def approve(self, healing_id: int, project: Project, secrets: dict[str, str], *, background: bool = True) -> None:
        """Run the rerun for a proposed fix a person has approved. Result is written to the original execution."""
        record = self.repo.get_healing(healing_id)
        if not record or record["project_id"] != project.id:
            raise NotFoundError()
        if record["status"] != "proposed":
            raise StudioError("This fix is not waiting for approval.")
        self.repo.update_healing(healing_id, status="running")
        self.repo.audit(project.id, "user", "healing.approved", "healing", {"id": healing_id})

        def work() -> None:
            try:
                self._run_approved(record, project, secrets)
            except Exception:  # noqa: BLE001
                LOGGER.exception("Approved healing %s crashed", healing_id)
                self.repo.update_healing(healing_id, status="failed", outcome="error")

        if background:
            threading.Thread(target=work, name=f"heal-{healing_id}", daemon=True).start()
        else:
            work()

    def _run_approved(self, record: dict[str, Any], project: Project, secrets: dict[str, str]) -> None:
        execution = self.repo.get_execution(record["execution_id"])
        if execution is None:
            raise NotFoundError()
        files = self.load_files(project, execution)
        selector = Selector.model_validate(record["new_locator"])
        patched, _, _ = patch_locators(files, record["element_key"], selector, execution["framework"].startswith("selenium"))
        workdir = run_dir(project.id, execution["id"]) / "workspace"
        ctx = ExecutionContext(execution["id"], project, workdir, files, execution["framework"], execution["browser"], secrets, execution.get("bundle_id"), execution.get("mode", "docker"))
        rows = {r["test_case_id"]: r for r in self.repo.list_results(execution["id"])}
        index = locator_index(ctx, self.repo)
        group = []
        for tc in record["test_case_ids"]:
            row = rows.get(tc)
            if row is None:
                continue
            group.append(Finding(tc, row, (row.get("evidence") or {}).get("failure", {}), record["element_key"], "", row.get("message", ""), "", index.get(record["element_key"]), {}, [], _NO_HINT))
        self._verify(ctx, record["id"], patched, group, [], [])
        self._totals(execution["id"])

    def apply(self, healing_id: int, project: Project) -> str:
        """Write a verified fix into the stored bundle and locator repository. Returns the diff that was applied."""
        record = self.repo.get_healing(healing_id)
        if not record or record["project_id"] != project.id:
            raise NotFoundError()
        if record["status"] != "verified":
            raise StudioError("Only fixes that passed the rerun can be applied.")
        execution = self.repo.get_execution(record["execution_id"]) or {}
        bundle_id = execution.get("bundle_id")
        selector = Selector.model_validate(record["new_locator"])
        selenium = str(execution.get("framework", "")).startswith("selenium")
        diff = record["proposed_code"]
        if bundle_id and self.store.exists(project.id, bundle_id):
            data = self.store.read_all(project.id, bundle_id)
            patched, old_entry, new_entry = patch_locators(data, record["element_key"], selector, selenium)
            self.store.write_file(project.id, bundle_id, LOCATOR_FILE, patched[LOCATOR_FILE])
            diff = entry_diff(record["element_key"], old_entry, new_entry)
        specs = self.repo.list_locators(project.id)
        for spec in specs:
            if spec.element_key == record["element_key"] and spec.preferred.identity() != selector.identity():
                spec.alternatives = [spec.preferred, *[a for a in spec.alternatives if a.identity() != selector.identity()]][:5]
                spec.preferred = selector
        self.repo.replace_locators(project.id, specs)
        self.repo.update_healing(healing_id, status="applied")
        self.repo.audit(project.id, "user", "healing.applied", "healing", {"id": healing_id, "element": record["element_key"]})
        return diff

    def reject(self, healing_id: int, project: Project) -> None:
        record = self.repo.get_healing(healing_id)
        if not record or record["project_id"] != project.id:
            raise NotFoundError()
        self.repo.update_healing(healing_id, status="rejected")
        self.repo.audit(project.id, "user", "healing.rejected", "healing", {"id": healing_id})


def _dump(entry: dict[str, Any]) -> str:
    return json.dumps(entry, indent=2, ensure_ascii=False)
