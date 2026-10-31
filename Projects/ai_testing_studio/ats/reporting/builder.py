"""Assemble an execution report: results joined with test cases, analysis, healing, defects and traceability."""

from __future__ import annotations

from collections import Counter
from typing import Any

from ats.ai.agents import ReportAgent
from ats.errors import NotFoundError, StudioError
from ats.execution.executor import compute_totals, run_dir
from ats.logging_setup import get_logger
from ats.models import Status, utc_now
from ats.repository import Project, Repository
from ats.security import mask_obj

LOGGER = get_logger("reporting")
FAILURE_STATUSES = {Status.FAIL.value, Status.INCONCLUSIVE.value}


def deterministic_summary(report: dict[str, Any]) -> dict[str, Any]:
    """Plain-language summary built only from recorded facts. Used when the model is unavailable."""
    totals, execution = report["totals"], report["execution"]
    ran = totals["total"] - totals["skipped"]
    summary = (
        f"Run #{execution['run_number']} executed {ran} of {totals['total']} test cases on {execution['browser']} "
        f"({execution['framework']}): {totals['passed']} passed, {totals['failed']} failed, {totals['healed']} healed, "
        f"{totals['inconclusive']} inconclusive, {totals['skipped']} skipped. Pass rate {totals['pass_rate']}%."
    )
    highlights, risks, recommendations = [], [], []
    if totals["healed"]:
        highlights.append(f"{totals['healed']} test(s) recovered after a verified locator fix. They are reported as HEALED, not PASS.")
    if totals["failed"] == 0 and totals["inconclusive"] == 0 and ran:
        highlights.append("No unresolved failures in this run.")
    categories = report["by_category"]
    if categories.get("LIKELY APPLICATION DEFECT") or categories.get("ASSERTION FAILURE"):
        risks.append("Possible application defects were found; draft defect reports are included.")
        recommendations.append("Review the drafted defects and confirm them manually before filing.")
    if categories.get("ENVIRONMENT ISSUE") or categories.get("TEST DATA ISSUE"):
        risks.append("Some failures look environmental or data related and do not indicate product regressions.")
        recommendations.append("Check environment availability, credentials and test data, then re-run the failed tests.")
    if totals["inconclusive"]:
        risks.append("Inconclusive tests failed once and passed on re-check; they may be flaky.")
        recommendations.append("Investigate synchronization or test isolation for the inconclusive tests.")
    if totals["skipped"]:
        risks.append(f"{totals['skipped']} test case(s) did not report a result.")
    if report["healings"]:
        recommendations.append("Review proposed locator fixes before accepting them.")
    return {"summary": summary, "highlights": highlights, "risks": risks, "recommendations": recommendations, "ai_generated": False}


class ReportService:
    def __init__(self, repo: Repository, agent: ReportAgent | None = None) -> None:
        self.repo = repo
        self.agent = agent or ReportAgent(repository=repo)

    # ------------------------------------------------------------------ assembly
    def build(self, project: Project, execution_id: str, *, with_ai: bool = True) -> dict[str, Any]:
        execution = self.repo.get_execution(execution_id)
        if not execution or execution["project_id"] != project.id:
            raise NotFoundError()
        raw_results = self.repo.list_results(execution_id)
        cases = {c.test_case_id: c for c in self.repo.list_test_cases(project.id)}
        bundle = self.repo.get_bundle(execution["bundle_id"]) if execution.get("bundle_id") else None
        trace = {t["test_case_id"]: t for t in (bundle or {}).get("traceability", []) if t.get("test_case_id")}

        results: list[dict[str, Any]] = []
        for row in raw_results:
            case, analysis = cases.get(row["test_case_id"]), row.get("analysis") or {}
            results.append(
                {
                    "test_case_id": row["test_case_id"], "title": case.title if case else row.get("test_name", ""),
                    "module": case.module if case else "", "scenario_id": case.scenario_id if case else (trace.get(row["test_case_id"]) or {}).get("scenario_id", ""),
                    "priority": case.priority if case else "", "test_type": case.test_type if case else "", "status": row["status"],
                    "duration": round(float(row["duration"]), 2), "message": row["message"][:1200],
                    "category": analysis.get("category", ""), "confidence": analysis.get("confidence", ""), "analysis_summary": analysis.get("summary", ""),
                    "recommended_action": analysis.get("recommended_action", ""), "file": (trace.get(row["test_case_id"]) or {}).get("file", ""),
                    "screenshot": (row.get("evidence") or {}).get("screenshot", ""), "healing": (analysis.get("healing") or {}),
                }
            )  # fmt: skip
        by_module: dict[str, Counter[str]] = {}
        for item in results:
            by_module.setdefault(item["module"] or "General", Counter())[item["status"]] += 1
        history = [
            {"run_number": e["run_number"], "execution_id": e["id"], "status": e["status"], "started_at": e["started_at"], "totals": e["totals"], "branch": e["branch"]}
            for e in self.repo.list_executions(project.id, ("full",))[:10]
        ]  # fmt: skip
        defects = [d["data"] for d in self.repo.list_defects(project.id, execution_id)]
        healings = [
            {k: h[k] for k in ("id", "element_key", "test_case_ids", "old_locator", "new_locator", "reason", "confidence", "status", "outcome", "pr_url")}
            for h in self.repo.list_healings(project.id, execution_id)
        ]  # fmt: skip
        coverage = [{**t, "status": next((r["status"] for r in results if r["test_case_id"] == tc), "NOT RUN")} for tc, t in trace.items()]
        report = {
            "generated_at": utc_now(),
            "project": {"name": project.name, "url": project.url, "base_url": project.app_base_url, "environment": project.environment, "coverage": project.coverage},
            "execution": {k: execution[k] for k in ("id", "run_number", "kind", "status", "framework", "browser", "mode", "branch", "commit_sha", "started_at", "finished_at", "duration", "error")},
            "totals": execution["totals"] or compute_totals(results),
            "results": results,
            "by_module": [{"module": m, **{s.value: c.get(s.value, 0) for s in Status}, "total": sum(c.values())} for m, c in sorted(by_module.items())],
            "by_category": dict(Counter(r["category"] for r in results if r["category"] and r["status"] in FAILURE_STATUSES)),
            "defects": defects, "healings": healings, "traceability": coverage, "history": history,
        }  # fmt: skip
        report["summary"] = self._summary(project, report) if with_ai else deterministic_summary(report)
        return mask_obj(report)

    def _summary(self, project: Project, report: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "execution": {k: report["execution"][k] for k in ("run_number", "status", "framework", "browser", "branch")} | {"environment": project.environment},
            "totals": {k: int(v) for k, v in report["totals"].items() if isinstance(v, (int, float))},
            "failures": [
                {"test_case_id": r["test_case_id"], "title": r["title"], "status": r["status"], "category": r["category"], "summary": r["analysis_summary"] or r["message"][:200]}
                for r in report["results"] if r["status"] in FAILURE_STATUSES
            ][:30],
            "healings": [{"element": h["element_key"], "status": h["status"], "confidence": h["confidence"]} for h in report["healings"]][:20],
        }  # fmt: skip
        try:
            result = self.agent.summarize(mask_obj(payload), project.id)
        except StudioError as exc:
            LOGGER.warning("Executive summary by AI unavailable: %s", exc.user_message)
            return deterministic_summary(report)
        if not result.summary.strip():
            return deterministic_summary(report)
        return {"summary": result.summary, "highlights": result.highlights, "risks": result.risks, "recommendations": result.recommendations, "ai_generated": True}

    # ------------------------------------------------------------------ files for the archive
    @staticmethod
    def evidence_files(project_id: str, execution: dict[str, Any], limit_bytes: int = 15_000_000) -> dict[str, bytes]:
        """Screenshots, step logs, failure details, JUnit XML and the run log. Raw DOM dumps stay out of exports (they can contain user data)."""
        base = run_dir(project_id, execution["id"])
        workspace, found, size = base / "workspace", {}, 0
        candidates = [base / "run.log", workspace / "reports" / "junit.xml"]
        evidence_root = workspace / "reports" / "evidence"
        if evidence_root.is_dir():
            candidates += sorted(p for p in evidence_root.rglob("*") if p.is_file() and p.name in {"screenshot.png", "steps.json", "failure.json"})
        for path in candidates:
            if not path.is_file():
                continue
            try:
                data = path.read_bytes()
            except OSError:
                continue
            if size + len(data) > limit_bytes:
                continue
            if path.suffix in {".log", ".xml", ".json"}:
                data = mask_text_bytes(data)
            size += len(data)
            found[path.relative_to(base).as_posix().replace("workspace/", "")] = data
        return found


def mask_text_bytes(data: bytes) -> bytes:
    from ats.security import mask

    return mask(data.decode("utf-8", errors="replace")).encode("utf-8")
