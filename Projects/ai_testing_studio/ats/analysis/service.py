"""Post-run orchestration: analyse failures, re-check flaky ones, heal what is healable, draft defects for the rest."""

from __future__ import annotations

from collections.abc import Callable

from ats.analysis.defects import DEFECT_CATEGORIES, DefectBuilder
from ats.analysis.findings import Finding
from ats.analysis.healing import HealingEngine
from ats.analysis.pipeline import FailureAnalyzer, locator_index
from ats.config import get_settings
from ats.errors import NotFoundError
from ats.execution.executor import ExecutionContext, ExecutionService, compute_totals, run_dir
from ats.logging_setup import get_logger
from ats.models import HEALABLE_CATEGORIES, FailureAnalysis, FailureCategory, Status, utc_now
from ats.repository import Project, Repository

LOGGER = get_logger("analysis.service")
RECHECK_CATEGORIES = {FailureCategory.TIMEOUT.value, FailureCategory.UNKNOWN.value}
POLICIES = ("manual", "auto_pr")


class AnalysisService:
    def __init__(
        self,
        repo: Repository,
        executor: ExecutionService,
        analyzer: FailureAnalyzer | None = None,
        healer: HealingEngine | None = None,
        defects: DefectBuilder | None = None,
        on_verified: Callable[[ExecutionContext, list[int]], None] | None = None,
    ) -> None:
        self.repo = repo
        self.executor = executor
        self.analyzer = analyzer or FailureAnalyzer(repo)
        self.healer = healer or HealingEngine(repo, executor, self.analyzer)
        self.defects = defects or DefectBuilder(repo)
        self.on_verified = on_verified
        self.policies: dict[str, str] = {}  # project id -> policy chosen in the UI (default comes from settings)

    def policy_for(self, project_id: str) -> str:
        value = self.policies.get(project_id) or get_settings().healing.approval_policy
        return value if value in POLICIES else "manual"

    # ------------------------------------------------------------------ main entry point (ExecutionService.post_run)
    def post_run(self, ctx: ExecutionContext) -> None:
        update = self.repo.update_execution
        try:
            update(ctx.execution_id, status="analyzing", phase="Analyzing failures")
            self._run(ctx)
        except Exception:  # noqa: BLE001
            LOGGER.exception("Post-run analysis failed for %s", ctx.execution_id)
            update(ctx.execution_id, phase="Analysis incomplete", error="Failure analysis did not finish. The test results themselves are valid.")
        finally:
            update(ctx.execution_id, status="completed", finished_at=utc_now())

    def _run(self, ctx: ExecutionContext) -> None:
        settings = get_settings().healing
        rows = [r for r in self.repo.list_results(ctx.execution_id) if r["status"] == Status.FAIL.value]
        if not rows:
            self.repo.update_execution(ctx.execution_id, phase="Complete")
            return
        index = locator_index(ctx, self.repo)
        findings: list[Finding] = []
        for number, row in enumerate(rows, 1):
            self.repo.update_execution(ctx.execution_id, phase=f"Analyzing failures ({number}/{len(rows)})")
            finding = self.analyzer.build(ctx, row, index)
            self.analyzer.analyze(ctx, finding)
            self.repo.update_result(ctx.execution_id, finding.test_case_id, analysis=finding.to_dict())
            findings.append(finding)

        if settings.recheck_flaky:
            self.repo.update_execution(ctx.execution_id, phase="Re-checking possible flaky failures")
            self._recheck(ctx, [f for f in findings if f.category in RECHECK_CATEGORIES])

        pending = [f for f in findings if self._status(ctx, f) == Status.FAIL.value]
        healable = [f for f in pending if f.analysis.category in HEALABLE_CATEGORIES]
        if settings.enabled and healable:
            self.repo.update_execution(ctx.execution_id, phase="Self-healing locators")
            self.healer.heal(ctx, healable, self.policy_for(ctx.project.id), self.on_verified)

        self.repo.update_execution(ctx.execution_id, phase="Drafting defect reports")
        execution = self.repo.get_execution(ctx.execution_id)
        for finding in findings:
            if self._status(ctx, finding) != Status.FAIL.value:
                continue
            self.repo.update_result(ctx.execution_id, finding.test_case_id, analysis=finding.to_dict())
            if finding.category in DEFECT_CATEGORIES:
                self.defects.save(ctx.project, ctx, finding, execution)
        totals = compute_totals(self.repo.list_results(ctx.execution_id), float((execution or {}).get("duration") or 0.0))
        note = ((execution or {}).get("totals") or {}).get("note")
        if note:
            totals["note"] = note
        self.repo.update_execution(ctx.execution_id, totals=totals, phase="Complete")
        self.repo.audit(ctx.project.id, "system", "analysis.completed", "execution", {"id": ctx.execution_id, "failures": len(findings)})

    def _status(self, ctx: ExecutionContext, finding: Finding) -> str:
        for row in self.repo.list_results(ctx.execution_id):
            if row["test_case_id"] == finding.test_case_id:
                return row["status"]
        return Status.FAIL.value

    # ------------------------------------------------------------------ flaky re-check
    def _recheck(self, ctx: ExecutionContext, findings: list[Finding]) -> None:
        """Failures with no hard evidence get one unchanged rerun. A pass is INCONCLUSIVE: it is neither a pass nor a defect."""
        if not findings:
            return
        ids = [f.test_case_id for f in findings]
        run_id = self.executor.create(
            ctx.project, ctx.framework, ctx.browser, bundle_id=ctx.bundle_id, source="recheck", kind="recheck", parent_id=ctx.execution_id, mode=ctx.mode
        )
        rerun = self.executor.execute(run_id, ctx.project, ctx.files, ctx.secrets, ctx.framework, ctx.browser, ctx.bundle_id, test_case_ids=ids, mode=ctx.mode)
        if rerun is None:
            return
        passed = {r["test_case_id"] for r in self.repo.list_results(run_id) if r["status"] == Status.PASS.value}
        for finding in findings:
            if finding.test_case_id not in passed:
                finding.notes.append("The failure was reproduced on a second run.")
                continue
            finding.notes.append("Passed on an unchanged re-check, so the first failure may be intermittent.")
            finding.analysis.summary = f"Intermittent: failed once, passed on re-check. {finding.analysis.summary}".strip()
            self.repo.update_result(
                ctx.execution_id, finding.test_case_id, status=Status.INCONCLUSIVE.value, analysis=finding.to_dict(),
                message="Failed on the first run and passed on an unchanged re-check. Treat as intermittent until it is investigated.",
            )  # fmt: skip

    # ------------------------------------------------------------------ on-demand operations
    def context_for(self, project: Project, execution_id: str, secrets: dict[str, str] | None = None) -> ExecutionContext:
        execution = self.repo.get_execution(execution_id)
        if execution is None or execution["project_id"] != project.id:
            raise NotFoundError()
        files = self.healer.load_files(project, execution)
        workdir = run_dir(project.id, execution_id) / "workspace"
        return ExecutionContext(execution_id, project, workdir, files, execution["framework"], execution["browser"], dict(secrets or {}), execution.get("bundle_id"), execution.get("mode", "docker"))

    def reanalyze(self, project: Project, execution_id: str, secrets: dict[str, str] | None = None) -> None:
        """Run the analysis (and, per policy, healing) on an execution that has already finished."""
        self.post_run(self.context_for(project, execution_id, secrets))

    def draft_defect(self, project: Project, execution_id: str, test_case_id: str) -> dict:
        """Create a defect draft for any failed test (the person decides; the classification is only advice)."""
        ctx = self.context_for(project, execution_id)
        row = next((r for r in self.repo.list_results(execution_id) if r["test_case_id"] == test_case_id), None)
        if row is None or row["status"] not in {Status.FAIL.value, Status.INCONCLUSIVE.value}:
            raise NotFoundError("Only failed or inconclusive tests can have a defect report.")
        finding = self.analyzer.build(ctx, row, locator_index(ctx, self.repo))
        stored = row.get("analysis") or {}
        finding.analysis = FailureAnalysis.model_validate({k: v for k, v in stored.items() if k in FailureAnalysis.model_fields})
        return self.defects.save(project, ctx, finding, self.repo.get_execution(execution_id))
