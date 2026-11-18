"""Automatic repair of failed tests.

After a run the studio does not stop at "N tests failed". For every failure it asks: is this the automation's fault or the
application's? Automation faults are repaired (a locator that stopped matching, a missing click or wait, a wrong sequence), the
repaired tests are re-run, the fixed project is saved and pushed to the project's GitHub branch, and the loop repeats on whatever
still fails. A failure that survives - or that the repair agent proves to be wrong application behaviour - is reported as a defect
for the customer. Assertions are never changed to make a test pass.
"""

from __future__ import annotations

import difflib
import json
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ats.ai.agents import ScriptGenerationAgent
from ats.analysis import dom
from ats.analysis.findings import Finding
from ats.analysis.healing import HealingEngine
from ats.analysis.patching import LOCATOR_FILE, PatchError, entry_diff, patch_locators
from ats.analysis.pipeline import FailureAnalyzer, locator_index
from ats.automation.bundle_store import BundleStore
from ats.automation.script_service import check_syntax
from ats.errors import StudioError
from ats.execution.executor import ExecutionContext, ExecutionService
from ats.logging_setup import get_logger
from ats.models import FailureCategory, RepairResult, Selector, Status
from ats.progress import ProgressFn, report
from ats.repository import Repository
from ats.security import mask, mask_obj

LOGGER = get_logger("analysis.autofix")
VIEWS_FILE = "config/views.json"
REPAIRABLE = {
    FailureCategory.AUTOMATION_ISSUE.value, FailureCategory.LOCATOR_DRIFT.value, FailureCategory.TIMEOUT.value,
    FailureCategory.UNKNOWN.value, FailureCategory.ASSERTION.value,
}  # fmt: skip
PushFn = Callable[[Any, dict[str, str], str], "dict[str, Any] | None"]
MAX_FUNCTION_CHARS = 7000
MAX_ATTEMPTS_PER_TEST = 2
PARALLEL_CALLS = 3


class RepairRejected(ValueError):
    """The proposed repair was refused by a safety check (never applied)."""


def allowed_path(path: str) -> bool:
    return (path.startswith("tests/") and path.endswith(".py")) or path == VIEWS_FILE


def apply_repair(files: dict[str, str], result: RepairResult) -> dict[str, str]:
    """Return the files with the repair applied, or raise ``RepairRejected``. Only exact, unique replacements are accepted."""
    new = dict(files)
    touched: set[str] = set()
    for edit in result.edits:
        if not allowed_path(edit.path) or edit.path not in new:
            raise RepairRejected(f"The repair wants to change {edit.path or 'an unknown file'}, which is not allowed.")
        text = new[edit.path]
        if not edit.find.strip() or text.count(edit.find) != 1:
            raise RepairRejected(f"The text to replace does not appear exactly once in {edit.path}.")
        for needle in ("expect(", "assert ", "@pytest.mark.tc("):
            if edit.replace.count(needle) < edit.find.count(needle):
                raise RepairRejected("The repair would remove an assertion or the test id marker, which is never allowed.")
        if re.search(r"(?i)(password|passwd|secret|token)\s*=\s*['\"][^'\"]{4,}['\"]", edit.replace):
            raise RepairRejected("The repair contains a hardcoded credential.")
        new[edit.path] = text.replace(edit.find, edit.replace, 1)
        touched.add(edit.path)
    if result.locator_updates:
        try:
            data = json.loads(new[LOCATOR_FILE])
        except (KeyError, ValueError) as exc:
            raise RepairRejected("The locator file is missing or invalid.") from exc
        for update in result.locator_updates:
            if update.element_key not in data:
                raise RepairRejected(f"Element '{update.element_key}' is not in the locator file.")
            entry = data[update.element_key]
            entry["preferred"] = update.preferred.model_dump(exclude_none=True)
            entry["alternatives"] = [s.model_dump(exclude_none=True) for s in update.alternatives[:5]]
        new[LOCATOR_FILE] = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        touched.add(LOCATOR_FILE)
    if not touched:
        raise RepairRejected("The repair contained no change.")
    problems = check_syntax({rel: new[rel] for rel in touched})
    if problems:
        raise RepairRejected("The repaired file failed the syntax check: " + problems[0])
    return new


def diff_text(old: dict[str, str], new: dict[str, str]) -> str:
    chunks = []
    for rel in sorted(new):
        if old.get(rel) != new[rel]:
            chunks.extend(difflib.unified_diff((old.get(rel) or "").splitlines(), new[rel].splitlines(), f"a/{rel}", f"b/{rel}", lineterm="", n=2))
    return "\n".join(chunks)[:6000]


def test_function(files: dict[str, str], test_case_id: str) -> tuple[str, str]:
    """(path, source) of the generated test for a test case id."""
    marker = re.compile(r"@pytest\.mark\.tc\(['\"]" + re.escape(test_case_id) + r"['\"]\)", re.I)
    for rel, content in sorted(files.items()):
        if not (rel.startswith("tests/") and rel.endswith(".py")):
            continue
        found = marker.search(content)
        if not found:
            continue
        end = content.find("\n@pytest.mark.tc(", found.end())
        return rel, content[found.start() : end if end > 0 else len(content)][:MAX_FUNCTION_CHARS]
    return "", ""


class AutoFixer:
    def __init__(
        self, repo: Repository, executor: ExecutionService, analyzer: FailureAnalyzer, healer: HealingEngine, store: BundleStore,
        agent: ScriptGenerationAgent | None = None, push: PushFn | None = None,
    ) -> None:  # fmt: skip
        self.repo, self.executor, self.analyzer, self.healer, self.store = repo, executor, analyzer, healer, store
        self.agent = agent or ScriptGenerationAgent(repository=repo)
        self.push = push

    # ------------------------------------------------------------------ 1. selectors that only worked through a fallback
    def promotions(self, ctx: ExecutionContext) -> dict[str, tuple[Selector, list[str]]]:
        """Elements the run could only find through an alternative selector: ``{key: (working selector, test ids)}``."""
        found: dict[str, tuple[Selector, list[str]]] = {}
        for row in self.repo.list_results(ctx.execution_id):
            fallbacks = (row.get("evidence") or {}).get("fallbacks") or {}
            for key, info in fallbacks.items():
                if info.get("ambiguous"):
                    continue  # matched several elements: not a selector worth promoting
                try:
                    selector = Selector.model_validate(info["selector"])
                except (KeyError, ValueError):
                    continue
                entry = found.setdefault(key, (selector, []))
                entry[1].append(row["test_case_id"])
        return found

    def _promote(self, ctx: ExecutionContext, files: dict[str, str], summary: dict[str, Any]) -> dict[str, str]:
        selenium = ctx.framework.startswith("selenium")
        for key, (selector, test_ids) in self.promotions(ctx).items():
            try:
                patched, old_entry, new_entry = patch_locators(files, key, selector, selenium)
            except PatchError:
                continue
            self.repo.create_healing(
                ctx.project.id, ctx.execution_id, test_case_ids=sorted(set(test_ids)), element_key=key, old_locator=old_entry.get("preferred", {}),
                new_locator=new_entry.get("preferred", {}), reason="The preferred selector no longer matched uniquely; this alternative worked in the live run.",
                confidence=0.9, validation={"worked_in_live_run": True}, original_code=json.dumps(old_entry, indent=2),
                proposed_code=entry_diff(key, old_entry, new_entry), status="applied", outcome="fallback_promoted",
            )  # fmt: skip
            files = patched
            summary["promoted"].append(key)
        return files

    # ------------------------------------------------------------------ 2. AI repair of the script
    def _payload(self, ctx: ExecutionContext, finding: Finding, files: dict[str, str], previous: list[dict[str, Any]]) -> dict[str, Any]:
        rel, source = test_function(files, finding.test_case_id)
        evidence = finding.result.get("evidence") or {}
        steps = evidence.get("steps") or []
        try:
            locators = json.loads(files.get(LOCATOR_FILE, "{}"))
        except ValueError:
            locators = {}
        used = {s.get("element") for s in steps if s.get("element")} | ({finding.element_key} if finding.element_key else set())
        try:
            views = json.loads(files.get(VIEWS_FILE, "{}")).get("views", {})
        except ValueError:
            views = {}
        view_key = str(finding.failure.get("view") or "")
        case = next((c for c in self.repo.list_test_cases(ctx.project.id) if c.test_case_id == finding.test_case_id), None)
        return mask_obj(
            {
                "test_case": case.model_dump(include={"test_case_id", "title", "steps", "expected_result", "preconditions", "test_data"}) if case else {"test_case_id": finding.test_case_id},
                "failing_step": {k: finding.failure.get(k) for k in ("step", "action", "element", "error")},
                "error": finding.error[:1500], "executed_steps": steps[-25:], "test_file": {rel: source} if rel else {},
                "locators": {k: v for k, v in locators.items() if k in used}, "view": {view_key: views.get(view_key)} if view_key in views else {},
                "dom_excerpt": dom.excerpt(finding.html) if finding.html else "", "page_url": finding.url, "rule_hint": finding.hint.as_dict(),
                "previous_attempts": previous,
            }
        )  # fmt: skip

    def repair(self, ctx: ExecutionContext, finding: Finding, files: dict[str, str], previous: list[dict[str, Any]]) -> RepairResult:
        try:
            return self.agent.repair(self._payload(ctx, finding, files, previous), ctx.project.id)
        except StudioError as exc:
            LOGGER.warning("Repair agent unavailable for %s: %s", finding.test_case_id, exc.user_message)
            return RepairResult(verdict="cannot_determine", explanation=f"The AI repair agent was not available: {exc.user_message}")

    def _rerun(self, ctx: ExecutionContext, files: dict[str, str], ids: list[str]) -> tuple[ExecutionContext | None, str]:
        run_id = self.executor.create(
            ctx.project, ctx.framework, ctx.browser, bundle_id=ctx.bundle_id, source="autofix", kind="rerun", parent_id=ctx.execution_id, mode=ctx.mode
        )
        return self.executor.execute(run_id, ctx.project, files, ctx.secrets, ctx.framework, ctx.browser, ctx.bundle_id, test_case_ids=ids, mode=ctx.mode), run_id

    def _mark_fixed(self, ctx: ExecutionContext, finding: Finding, note: str, diff: str, run_id: str) -> None:
        stored = finding.result.get("analysis") or finding.to_dict()
        finding.healing = {"status": "verified", "message": note, "rerun_execution_id": run_id}
        details = {**(finding.result.get("details") or {}), "autofix": {"explanation": note, "diff": diff[:3000], "rerun_execution_id": run_id}, "original_status": Status.FAIL.value}
        self.repo.update_result(ctx.execution_id, finding.test_case_id, status=Status.HEALED.value, message=note, details=details, analysis={**stored, "healing": finding.healing})
        self.repo.create_healing(
            ctx.project.id, ctx.execution_id, test_case_ids=[finding.test_case_id], element_key=f"{finding.test_case_id} (script)", reason=note,
            confidence=0.8, validation={"rerun_passed": True}, proposed_code=diff[:6000], rerun_execution_id=run_id, status="applied", outcome="rerun_passed",
        )  # fmt: skip

    # ------------------------------------------------------------------ orchestration
    def run(self, ctx: ExecutionContext, findings: list[Finding], max_rounds: int, progress: ProgressFn | None = None) -> dict[str, Any]:
        """Repair what can be repaired. Returns a summary and leaves still-failing findings categorised for the defect report."""
        summary: dict[str, Any] = {"promoted": [], "healed_locators": [], "repaired": [], "defects": [], "unresolved": [], "pushed": None, "rounds": 0}
        files = dict(ctx.files)
        original = dict(files)

        report(progress, "Promoting selectors that only worked through a fallback", 0.8)
        files = self._promote(ctx, files, summary)

        pending = [f for f in findings if self._failing(ctx, f)]
        drift = [f for f in pending if f.analysis.category == FailureCategory.LOCATOR_DRIFT and HealingEngine.eligible(f)[0]]
        if drift:
            report(progress, f"Healing {len(drift)} locator(s) and re-running the affected tests", 0.82)
            files = self._heal_locators(ctx, drift, files, summary)
            pending = [f for f in findings if self._failing(ctx, f)]

        previous: dict[str, list[dict[str, Any]]] = {}
        for round_no in range(1, max(max_rounds, 0) + 1):
            candidates = [f for f in pending if f.analysis.category.value in REPAIRABLE and len(previous.get(f.test_case_id, [])) < MAX_ATTEMPTS_PER_TEST]
            if not candidates:
                break
            summary["rounds"] = round_no
            span = 0.12 / max(max_rounds, 1)
            report(progress, f"Auto-fix round {round_no}/{max_rounds}: repairing {len(candidates)} test(s)", 0.84 + span * (round_no - 1))
            plans: dict[str, tuple[dict[str, str], RepairResult]] = {}
            with ThreadPoolExecutor(max_workers=PARALLEL_CALLS) as pool:  # the model calls are independent: ask for all repairs at once
                results = list(pool.map(lambda f: self.repair(ctx, f, files, previous.get(f.test_case_id, [])), candidates))
            for finding, result in zip(candidates, results, strict=True):
                if result.verdict == "application_defect":
                    finding.analysis.category = FailureCategory.APPLICATION_DEFECT
                    finding.analysis.automation_fixable = False
                    finding.analysis.summary = result.explanation or finding.analysis.summary
                    finding.notes.append("The repair agent verified that the automation is correct: the application does not behave as expected.")
                    summary["defects"].append(finding.test_case_id)
                    continue
                if result.verdict != "fixed":
                    previous.setdefault(finding.test_case_id, []).append({"verdict": result.verdict, "why": result.explanation})
                    continue
                try:
                    plans[finding.test_case_id] = (apply_repair(files, result), result)
                except RepairRejected as exc:
                    previous.setdefault(finding.test_case_id, []).append({"rejected": str(exc), "why": result.explanation})
                    finding.notes.append(f"A proposed repair was refused: {exc}")
            if not plans:
                break
            candidate_files = dict(files)
            for new_files, _ in plans.values():
                candidate_files.update({rel: text for rel, text in new_files.items() if text != files.get(rel)})
            report(progress, f"Auto-fix round {round_no}/{max_rounds}: re-running {len(plans)} repaired test(s)", 0.84 + span * (round_no - 0.5))
            rerun_ctx, run_id = self._rerun(ctx, candidate_files, sorted(plans))
            if rerun_ctx is None:
                break
            rows = {r["test_case_id"]: r for r in self.repo.list_results(run_id)}
            index = locator_index(rerun_ctx, self.repo)
            keep: dict[str, str] = {}
            for finding in candidates:
                plan = plans.get(finding.test_case_id)
                if plan is None:
                    continue
                new_files, result = plan
                row = rows.get(finding.test_case_id) or {"status": Status.SKIPPED.value}
                if row["status"] == Status.PASS.value:
                    self._mark_fixed(ctx, finding, result.explanation or "The automation was repaired and the test now passes.", diff_text(files, new_files), run_id)
                    keep.update({rel: text for rel, text in new_files.items() if text != files.get(rel)})
                    summary["repaired"].append(finding.test_case_id)
                elif row["status"] == Status.FAIL.value:
                    previous.setdefault(finding.test_case_id, []).append({"repair": result.explanation, "still_failing": mask(str(row.get("message", "")))[:300]})
                    follow = self.analyzer.build(rerun_ctx, row, index)
                    self.analyzer.analyze(rerun_ctx, follow)
                    finding.failure, finding.html, finding.error, finding.element_key = follow.failure, follow.html, follow.error, follow.element_key
                    finding.hint, finding.result = follow.hint, {**finding.result, "evidence": row.get("evidence") or {}}
                    finding.analysis = follow.analysis
            files = {**files, **keep}
            pending = [f for f in findings if self._failing(ctx, f)]

        summary["unresolved"] = [f.test_case_id for f in pending if f.test_case_id not in summary["defects"]]
        changed = {rel for rel in files if files[rel] != original.get(rel)}
        if changed:
            self._save(ctx, files, changed, summary, progress)
        return summary

    # ------------------------------------------------------------------ pieces
    def _failing(self, ctx: ExecutionContext, finding: Finding) -> bool:
        for row in self.repo.list_results(ctx.execution_id):
            if row["test_case_id"] == finding.test_case_id:
                return row["status"] == Status.FAIL.value
        return True

    def _heal_locators(self, ctx: ExecutionContext, drift: list[Finding], files: dict[str, str], summary: dict[str, Any]) -> dict[str, str]:
        """DOM-grounded locator healing with verification by re-run (existing engine); verified fixes are applied straight away."""
        base = ExecutionContext(ctx.execution_id, ctx.project, ctx.workdir, files, ctx.framework, ctx.browser, ctx.secrets, ctx.bundle_id, ctx.mode, ctx.expected_ids)
        created = self.healer.heal(base, drift, "auto_apply", None)
        selenium = ctx.framework.startswith("selenium")
        for record_id in created:
            record = self.repo.get_healing(record_id)
            if not record or record["status"] != "verified":
                continue
            try:
                files, _, _ = patch_locators(files, record["element_key"], Selector.model_validate(record["new_locator"]), selenium)
            except PatchError:
                continue
            self.repo.update_healing(record_id, status="applied")
            summary["healed_locators"].append(record["element_key"])
        return files

    def _save(self, ctx: ExecutionContext, files: dict[str, str], changed: set[str], summary: dict[str, Any], progress: ProgressFn | None) -> None:
        """Keep the fixed project: stored bundle first, then the project's GitHub branch."""
        if ctx.bundle_id and self.store.exists(ctx.project.id, ctx.bundle_id):
            for rel in sorted(changed):
                try:
                    self.store.write_file(ctx.project.id, ctx.bundle_id, rel, files[rel])
                except Exception:  # noqa: BLE001
                    LOGGER.warning("Could not save %s to the bundle", rel, exc_info=True)
        specs = self.repo.list_locators(ctx.project.id)
        try:
            index = {k: v for k, v in json.loads(files[LOCATOR_FILE]).items()}
            for spec in specs:
                entry = index.get(spec.element_key)
                if entry and Selector.model_validate(entry["preferred"]).identity() != spec.preferred.identity():
                    spec.alternatives = [spec.preferred, *[a for a in spec.alternatives if a.identity() != Selector.model_validate(entry["preferred"]).identity()]][:5]
                    spec.preferred = Selector.model_validate(entry["preferred"])
            self.repo.replace_locators(ctx.project.id, specs)
        except (KeyError, ValueError):
            pass
        self.repo.audit(ctx.project.id, "system", "autofix.saved", "bundle", {"files": sorted(changed), "execution": ctx.execution_id})
        if self.push is None:
            return
        report(progress, "Pushing the fixes to the GitHub branch", 0.96)
        names = summary["promoted"] + summary["healed_locators"] + summary["repaired"]
        message = f"Auto-fix: {len(names)} automation repair(s) after run {ctx.execution_id}\n\n" + "\n".join(f"- {n}" for n in names[:40])
        try:
            summary["pushed"] = self.push(ctx.project, {rel: files[rel] for rel in sorted(changed)}, message)  # only what changed: other channels' files stay untouched
        except StudioError as exc:
            summary["push_error"] = exc.user_message
            self.repo.audit(ctx.project.id, "system", "autofix.push_failed", "github", {"error": exc.user_message})


__all__ = ["AutoFixer", "RepairRejected", "apply_repair", "test_function"]
