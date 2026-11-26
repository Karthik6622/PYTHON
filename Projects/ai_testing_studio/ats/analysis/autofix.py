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
from ats.analysis.expectations import repair_expectation
from ats.analysis.pipeline import FailureAnalyzer, locator_index
from ats.analysis.relocate import Relocation, Relocator
from ats.automation.bundle_store import BundleStore
from ats.automation.script_service import check_syntax
from ats.discovery.facts import Evidence
from ats.errors import StudioError
from ats.execution.executor import ExecutionContext, ExecutionService
from ats.logging_setup import get_logger
from ats.models import FailureCategory, RepairResult, Selector, Status
from ats.progress import ProgressFn, report
from ats.repository import Repository
from ats.security import mask, mask_obj

LOGGER = get_logger("analysis.autofix")
VIEWS_FILE = "config/views.json"
PushFn = Callable[[Any, dict[str, str], str], "dict[str, Any] | None"]
MAX_FUNCTION_CHARS = 7000
PARALLEL_CALLS = 5


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
        for method in ("to_contain_text", "to_have_text", "to_have_value"):
            if edit.replace.count(method) < edit.find.count(method):
                raise RepairRejected("The repair would remove a text or value check. Preserve the assertion and repair its target instead.")
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
        agent: ScriptGenerationAgent | None = None, push: PushFn | None = None, relocator: Relocator | None = None,
    ) -> None:  # fmt: skip
        self.repo, self.executor, self.analyzer, self.healer, self.store = repo, executor, analyzer, healer, store
        self.agent = agent or ScriptGenerationAgent(repository=repo)
        self.push = push
        self.relocator = relocator or Relocator()

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
    def _payload(self, ctx: ExecutionContext, finding: Finding, files: dict[str, str], previous: list[dict[str, Any]], live: Relocation | None = None) -> dict[str, Any]:
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
                "live_check": (
                    {"element": live.key, "result": live.status, "detail": live.detail, "found_on_view": live.found_on_view} if live is not None else {}
                ),
            }
        )  # fmt: skip

    def repair(self, ctx: ExecutionContext, finding: Finding, files: dict[str, str], previous: list[dict[str, Any]], live: Relocation | None = None) -> RepairResult:
        try:
            return self.agent.repair(self._payload(ctx, finding, files, previous, live), ctx.project.id)
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
        """Repair every failing test, verify each repair by re-running it, keep what passes and push it once at the end.

        Each attempt (up to ``max_rounds``, default 3) works on ALL tests that still fail:
          1. every failing element is looked for again on the live application (views opened like the tests open them) and the
             verified selector is patched into the locator file;
          2. every failing test that a locator change does not cover gets an AI repair of its script (applied one after another,
             so several repairs in one file never overwrite each other);
          3. all still-failing tests are re-run together, in parallel browsers;
          4. a test that passes after a change is HEALED and its change is kept; a test that passes without any change was
             intermittent; the rest go into the next attempt with what was learned.
        What still fails after the last attempt is left for the failure report."""
        summary: dict[str, Any] = {
            "promoted": [], "relocated": [], "healed_locators": [], "repaired": [], "intermittent": [], "defects": [], "unresolved": [],
            "pushed": None, "rounds": 0,
        }  # fmt: skip
        files = dict(ctx.files)
        original = dict(files)
        selenium = ctx.framework.startswith("selenium")
        discovery = self.repo.latest_successful_discovery(ctx.project.id)
        evidence = Evidence(discovery, {s.element_key: s for s in self.repo.list_locators(ctx.project.id)}) if discovery is not None else None

        report(progress, "Promoting selectors that only worked through a fallback", 0.8)
        files = self._promote(ctx, files, summary)

        pending = [f for f in findings if self._failing(ctx, f)]
        history: dict[str, list[dict[str, Any]]] = {}
        rounds = max(max_rounds, 0)
        for attempt in range(1, rounds + 1):
            if not pending:
                break
            summary["rounds"] = attempt
            base = 0.8 + 0.16 * (attempt - 1) / max(rounds, 1)
            step = 0.16 / max(rounds, 1)
            candidate = dict(files)
            changed_for: dict[str, list[str]] = {}  # test id -> what was changed for it in this attempt
            patched_keys: dict[str, tuple[dict[str, Any], dict[str, Any], str]] = {}

            # 1. live locator search for every failing element
            keys = sorted({f.element_key for f in pending if f.element_key})
            live = {}
            if keys:
                report(progress, f"Attempt {attempt}/{rounds}: looking for {len(keys)} failing element(s) on the live application", base)
                live = self.relocator.run(candidate, ctx.project.app_base_url, keys, ctx.secrets, ctx.project.limits.ignore_https_errors)
                for key, found in live.items():
                    if found.status != "relocated" or found.selector is None:
                        continue
                    try:
                        candidate, old_entry, new_entry = patch_locators(candidate, key, found.selector, selenium, found.alternatives)
                    except PatchError:
                        continue
                    patched_keys[key] = (old_entry, new_entry, found.detail)
                for finding in pending:
                    if finding.element_key in patched_keys:
                        changed_for.setdefault(finding.test_case_id, []).append(f"locator {finding.element_key}: {patched_keys[finding.element_key][2]}")

            # 2. rule repairs of invented expectations (no model needed), then AI repair of what is still unexplained
            edits: dict[str, RepairResult] = {}
            if evidence is not None:
                index_now = locator_index(ctx, self.repo)
                for finding in [f for f in pending if f.test_case_id not in changed_for]:
                    result, why = repair_expectation(candidate, finding.test_case_id, finding.element_key, finding.action, finding.error, index_now.get(finding.element_key), evidence)
                    if result is not None:
                        try:
                            candidate = apply_repair(candidate, result)
                        except RepairRejected as exc:
                            history.setdefault(finding.test_case_id, []).append({"attempt": attempt, "rejected": str(exc)})
                            continue
                        edits[finding.test_case_id] = result
                        changed_for.setdefault(finding.test_case_id, []).append(f"expectation: {result.explanation}")
                    elif why.startswith("'") and "application changed" in why:
                        finding.analysis.category = FailureCategory.APPLICATION_DEFECT
                        finding.analysis.automation_fixable = False
                        finding.analysis.summary = f"The expected text was observed during discovery but the page now shows something else: {why}"
                        summary["defects"].append(finding.test_case_id)
            needs_ai = [
                f for f in pending
                if f.test_case_id not in changed_for and f.test_case_id not in summary["defects"]
                and f.analysis.category not in {FailureCategory.ENVIRONMENT, FailureCategory.TEST_DATA, FailureCategory.APPLICATION_DEFECT}
            ]  # fmt: skip
            if needs_ai:
                report(progress, f"Attempt {attempt}/{rounds}: repairing {len(needs_ai)} test script(s)", base + step * 0.25)
                with ThreadPoolExecutor(max_workers=PARALLEL_CALLS) as pool:  # independent model calls: ask for all repairs at once
                    results = list(pool.map(lambda f: self.repair(ctx, f, candidate, history.get(f.test_case_id, []), live.get(f.element_key)), needs_ai))
                for finding, result in zip(needs_ai, results, strict=True):
                    if result.verdict == "application_defect":
                        finding.analysis.category = FailureCategory.APPLICATION_DEFECT
                        finding.analysis.automation_fixable = False
                        finding.analysis.summary = result.explanation or finding.analysis.summary
                        finding.notes.append("The repair agent verified that the automation is correct: the application does not behave as expected.")
                        summary["defects"].append(finding.test_case_id)
                        continue
                    if result.verdict != "fixed":
                        history.setdefault(finding.test_case_id, []).append({"attempt": attempt, "verdict": result.verdict, "why": result.explanation})
                        continue
                    try:
                        candidate = apply_repair(candidate, result)  # on top of the earlier repairs of this attempt
                    except RepairRejected as exc:
                        history.setdefault(finding.test_case_id, []).append({"attempt": attempt, "rejected": str(exc), "why": result.explanation})
                        finding.notes.append(f"A proposed repair was refused: {exc}")
                        continue
                    edits[finding.test_case_id] = result
                    changed_for.setdefault(finding.test_case_id, []).append(f"script: {result.explanation or 'repaired'}")
            pending = [f for f in pending if f.test_case_id not in summary["defects"]]
            # the first re-run covers every failing test (it also tells intermittent failures apart); later ones only what changed
            to_run = pending if attempt == 1 else [f for f in pending if f.test_case_id in changed_for]
            if not to_run:
                continue

            # 3. one re-run of the tests to verify
            report(progress, f"Attempt {attempt}/{rounds}: re-running {len(to_run)} test(s)", base + step * 0.6)
            rerun_ctx, run_id = self._rerun(ctx, candidate, sorted(f.test_case_id for f in to_run))
            if rerun_ctx is None:
                break
            rows = {r["test_case_id"]: r for r in self.repo.list_results(run_id)}
            files = self._promote(rerun_ctx, files, summary)  # elements the re-run only found by fingerprint: that selector worked live
            index = locator_index(rerun_ctx, self.repo)

            # 4. keep what was verified
            keep_keys: set[str] = set()
            run_ids = {f.test_case_id for f in to_run}
            still: list[Finding] = [f for f in pending if f.test_case_id not in run_ids]
            for finding in to_run:
                row = rows.get(finding.test_case_id) or {"status": Status.SKIPPED.value, "message": "The test did not run in the re-run."}
                what = changed_for.get(finding.test_case_id, [])
                if row["status"] == Status.PASS.value:
                    if finding.element_key in patched_keys:
                        keep_keys.add(finding.element_key)
                    if not what:
                        self._mark_intermittent(ctx, finding, run_id)
                        summary["intermittent"].append(finding.test_case_id)
                        continue
                    result = edits.get(finding.test_case_id)
                    before = dict(files)
                    if result is not None:
                        try:
                            files = apply_repair(files, result)  # only this test's own script change is kept
                        except RepairRejected:
                            LOGGER.warning("Verified repair of %s could not be re-applied on its own", finding.test_case_id)
                    diff = diff_text(before, files) if result is not None else entry_diff(finding.element_key, *patched_keys[finding.element_key][:2])
                    self._mark_fixed(ctx, finding, "; ".join(what), diff, run_id)
                    (summary["repaired"] if result is not None else summary["relocated"]).append(finding.test_case_id)
                    continue
                failing_key = str(((row.get("evidence") or {}).get("failure") or {}).get("element") or "")
                if finding.element_key in patched_keys and failing_key != finding.element_key:
                    keep_keys.add(finding.element_key)  # the element is found now; the test fails further on
                history.setdefault(finding.test_case_id, []).append(
                    {"attempt": attempt, "changed": what, "still_failing": mask(str(row.get("message", "")))[:300], "failing_element": failing_key}
                )  # fmt: skip
                follow = self.analyzer.build(rerun_ctx, row, index)
                finding.failure, finding.html, finding.error, finding.element_key = follow.failure, follow.html, follow.error, follow.element_key
                finding.hint, finding.result, finding.check, finding.candidates = follow.hint, {**finding.result, "evidence": row.get("evidence") or {}}, follow.check, follow.candidates
                finding.old_spec = follow.old_spec
                still.append(finding)
            for key in sorted(keep_keys):
                old_entry, new_entry, detail = patched_keys[key]
                if self._locator_differs(files, key, new_entry):
                    try:
                        alternatives = [Selector.model_validate(a) for a in new_entry.get("alternatives", [])[:3]]
                        files, _, _ = patch_locators(files, key, Selector.model_validate(new_entry["preferred"]), selenium, alternatives)
                    except PatchError:
                        continue
                users = sorted({f.test_case_id for f in pending if any(f"locator {key}:" in w for w in changed_for.get(f.test_case_id, []))})
                self.repo.create_healing(
                    ctx.project.id, ctx.execution_id, test_case_ids=users, element_key=key, old_locator=old_entry.get("preferred", {}),
                    new_locator=new_entry.get("preferred", {}), reason=detail, confidence=0.9, validation={"found_on_live_page": True, "rerun_execution_id": run_id},
                    original_code=json.dumps(old_entry, indent=2), proposed_code=entry_diff(key, old_entry, new_entry), rerun_execution_id=run_id,
                    status="applied", outcome="relocated_live",
                )  # fmt: skip
                summary["healed_locators"].append(key)
            pending = still

        summary["unresolved"] = [f.test_case_id for f in pending if f.test_case_id not in summary["defects"]]
        for finding in pending:  # say WHY a test stayed failing: attempts, what was tried, what the live page showed
            tries = history.get(finding.test_case_id, [])
            if tries:
                finding.notes.append("Auto-fix tried " + "; ".join(
                    f"attempt {t.get('attempt')}: " + (", ".join(t.get("changed") or []) or t.get("why") or t.get("rejected") or t.get("verdict", "no change"))
                    + (f" -> still failing: {t['still_failing']}" if t.get("still_failing") else "")
                    for t in tries[-3:]
                ))  # fmt: skip
            else:
                finding.notes.append("Auto-fix found nothing it could change for this failure (no locator found on the live page, no unsupported expectation, no script repair proposed).")
        changed = {rel for rel in files if files[rel] != original.get(rel)}
        if changed:
            self._save(ctx, files, changed, summary, progress)
        return summary

    @staticmethod
    def _locator_differs(files: dict[str, str], key: str, new_entry: dict[str, Any]) -> bool:
        try:
            return json.loads(files[LOCATOR_FILE])[key]["preferred"] != new_entry["preferred"]
        except (KeyError, ValueError):
            return False

    def _mark_intermittent(self, ctx: ExecutionContext, finding: Finding, run_id: str) -> None:
        finding.notes.append("Passed on a re-run without any change, so the first failure was intermittent.")
        finding.analysis.summary = f"Intermittent: failed once, passed on a re-run without changes. {finding.analysis.summary}".strip()
        self.repo.update_result(
            ctx.execution_id, finding.test_case_id, status=Status.INCONCLUSIVE.value, analysis=finding.to_dict(),
            message=f"Failed on the first run and passed on an unchanged re-run ({run_id}). Treat as intermittent until it is investigated.",
        )  # fmt: skip

    # ------------------------------------------------------------------ pieces
    def _failing(self, ctx: ExecutionContext, finding: Finding) -> bool:
        for row in self.repo.list_results(ctx.execution_id):
            if row["test_case_id"] == finding.test_case_id:
                return row["status"] == Status.FAIL.value
        return True

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
