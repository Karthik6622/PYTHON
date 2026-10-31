"""Execution orchestration: workspace preparation, running, result collection and the post-run analysis hook."""

from __future__ import annotations

import re
import shutil
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ats.config import get_settings
from ats.errors import ExecutionError
from ats.execution.junit import collect
from ats.execution.runner import RunOutcome, RunRequest, run_project
from ats.logging_setup import get_logger
from ats.models import Status, utc_now
from ats.repository import Project, Repository
from ats.security import mask, register_secret

LOGGER = get_logger("executor")
TC_ID = re.compile(r"(?i)\btc_[a-z0-9]{2,6}_\d{3}\b")
TEST_PATH_MARKERS = ("tests/", "src/test/java/", "test/")
_CANCEL: dict[str, threading.Event] = {}
_LOCK = threading.Lock()


@dataclass
class ExecutionContext:
    """Everything the analysis / healing stages need to know about a finished execution."""

    execution_id: str
    project: Project
    workdir: Path
    files: dict[str, str]
    framework: str
    browser: str
    secrets: dict[str, str] = field(default_factory=dict, repr=False)
    bundle_id: int | None = None
    mode: str = "docker"
    expected_ids: list[str] = field(default_factory=list)


def discover_ids(files: dict[str, str]) -> list[str]:
    found: dict[str, None] = {}
    for rel, content in sorted(files.items()):
        if rel.endswith((".py", ".ts", ".js", ".java")) and any(m in rel for m in TEST_PATH_MARKERS):
            for match in TC_ID.finditer(content):
                found[match.group(0).upper()] = None
    return list(found)


def compute_totals(results: list[dict[str, Any]], duration: float = 0.0) -> dict[str, Any]:
    counts = {s.value: 0 for s in Status}
    for row in results:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    total = len(results)
    ran = total - counts[Status.SKIPPED.value]
    return {
        "total": total,
        "passed": counts[Status.PASS.value],
        "failed": counts[Status.FAIL.value],
        "healed": counts[Status.HEALED.value],
        "skipped": counts[Status.SKIPPED.value],
        "inconclusive": counts[Status.INCONCLUSIVE.value],
        "pass_rate": round(100 * counts[Status.PASS.value] / ran, 1) if ran else 0.0,
        "duration": round(duration, 1),
    }


def run_dir(project_id: str, execution_id: str) -> Path:
    return get_settings().runs_dir / project_id / execution_id


class ExecutionService:
    def __init__(self, repo: Repository, post_run: Callable[[ExecutionContext], None] | None = None) -> None:
        self.repo = repo
        self.post_run = post_run

    # ------------------------------------------------------------------ public API
    def start(
        self,
        project: Project,
        files: dict[str, str],
        *,
        secrets: dict[str, str],
        framework: str,
        browser: str,
        bundle_id: int | None = None,
        source: str = "bundle",
        branch: str = "",
        commit_sha: str = "",
        test_case_ids: list[str] | None = None,
        mode: str | None = None,
        analyze: bool = True,
    ) -> str:
        """Create the execution record and run it in a background thread. Returns the execution id immediately."""
        if not files:
            raise ExecutionError("There are no files to execute.")
        execution_id = self.create(project, framework, browser, bundle_id=bundle_id, source=source, branch=branch, commit_sha=commit_sha, mode=mode)
        cancel = threading.Event()
        with _LOCK:
            _CANCEL[execution_id] = cancel

        def work() -> None:
            try:
                context = self.execute(execution_id, project, files, secrets, framework, browser, bundle_id, test_case_ids, mode, cancel)
                if context is not None and analyze and self.post_run is not None and not cancel.is_set():
                    self.post_run(context)
            except Exception:  # noqa: BLE001
                LOGGER.exception("Execution %s crashed", execution_id)
                self.repo.update_execution(execution_id, status="error", phase="Failed", error="Unexpected error while running the tests.", finished_at=utc_now())
            finally:
                with _LOCK:
                    _CANCEL.pop(execution_id, None)

        threading.Thread(target=work, name=f"exec-{execution_id}", daemon=True).start()
        return execution_id

    def create(
        self, project: Project, framework: str, browser: str, *, bundle_id: int | None = None, source: str = "bundle", branch: str = "",
        commit_sha: str = "", kind: str = "full", parent_id: str = "", mode: str | None = None,
    ) -> str:  # fmt: skip
        settings = get_settings().execution
        execution_id = self.repo.create_execution(
            project.id, bundle_id=bundle_id, parent_id=parent_id, kind=kind, status="queued", phase="Queued", branch=branch, commit_sha=commit_sha,
            source=source, framework=framework, browser=browser, environment=project.environment, mode=mode or settings.mode,
        )  # fmt: skip
        self.repo.audit(project.id, "user" if kind == "full" else "system", f"execution.{kind}.queued", "execution", {"id": execution_id, "framework": framework, "browser": browser, "source": source})
        return execution_id

    def cancel(self, execution_id: str) -> bool:
        with _LOCK:
            event = _CANCEL.get(execution_id)
        if event is None:
            return False
        event.set()
        return True

    def is_running(self, execution_id: str) -> bool:
        with _LOCK:
            return execution_id in _CANCEL

    @staticmethod
    def log_tail(project_id: str, execution_id: str, lines: int = 200) -> str:
        path = run_dir(project_id, execution_id) / "run.log"
        if not path.is_file():
            return ""
        try:
            return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])
        except OSError:
            return ""

    # ------------------------------------------------------------------ synchronous core
    def execute(
        self,
        execution_id: str,
        project: Project,
        files: dict[str, str],
        secrets: dict[str, str],
        framework: str,
        browser: str,
        bundle_id: int | None = None,
        test_case_ids: list[str] | None = None,
        mode: str | None = None,
        cancel: threading.Event | None = None,
    ) -> ExecutionContext | None:
        settings = get_settings()
        mode = mode or settings.execution.mode
        started = time.time()
        base = run_dir(project.id, execution_id)
        workdir = base / "workspace"
        log_path = base / "run.log"
        base.mkdir(parents=True, exist_ok=True)
        if workdir.exists():
            shutil.rmtree(workdir, ignore_errors=True)
        workdir.mkdir(parents=True, exist_ok=True)
        for rel, content in files.items():
            target = workdir / rel
            if workdir.resolve() not in target.resolve().parents:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="\n")
        for value in secrets.values():
            register_secret(value)
        expected = [i for i in (test_case_ids or discover_ids(files))]
        update = self.repo.update_execution
        update(execution_id, status="running", phase="Preparing workspace", mode=mode)

        log_file = log_path.open("a", encoding="utf-8")

        def on_log(line: str) -> None:
            log_file.write(line + "\n")
            log_file.flush()

        def on_phase(text: str) -> None:
            update(execution_id, phase=text)

        request = RunRequest(
            framework=framework, browser=browser, workdir=workdir, base_url=project.app_base_url, env=dict(secrets), test_case_ids=test_case_ids,
            ignore_https_errors=project.limits.ignore_https_errors, timeout=settings.execution.timeout_seconds, mode=mode, name=f"ats-{execution_id.lower()}",
        )  # fmt: skip
        try:
            outcome = run_project(request, on_log=on_log, on_phase=on_phase, cancel=cancel)
        finally:
            log_file.close()
        duration = time.time() - started
        context = ExecutionContext(execution_id, project, workdir, files, framework, browser, secrets, bundle_id, mode, expected)

        if outcome.cancelled:
            update(execution_id, status="cancelled", phase="Cancelled", error="The run was cancelled.", finished_at=utc_now(), duration=duration)
            return None
        if outcome.error:
            update(execution_id, status="error", phase="Failed", error=outcome.error, finished_at=utc_now(), duration=duration)
            self.repo.audit(project.id, "system", "execution.error", "execution", {"id": execution_id, "error": outcome.error})
            return None

        update(execution_id, phase="Collecting results")
        rows = collect(workdir, expected)
        no_results = rows and all(r["status"] == Status.SKIPPED.value and not r["test_name"] for r in rows)
        if no_results and (outcome.exit_code != 0 or outcome.timed_out):
            reason = "The run exceeded the time limit." if outcome.timed_out else self._explain_no_results(outcome)
            update(execution_id, status="error", phase="Failed", error=reason, finished_at=utc_now(), duration=duration)
            return None
        self.repo.replace_results(execution_id, rows)
        totals = compute_totals(rows, duration)
        if outcome.timed_out:
            totals["note"] = "The run hit the time limit; unfinished tests are reported as skipped."
        update(execution_id, status="completed", phase="Results collected", totals=totals, finished_at=utc_now(), duration=duration)
        self.repo.audit(project.id, "system", "execution.completed", "execution", {"id": execution_id, **{k: v for k, v in totals.items() if k != "note"}})
        return context

    @staticmethod
    def _explain_no_results(outcome: RunOutcome) -> str:
        tail = [line for line in outcome.log.splitlines() if line.strip()][-8:]
        hint = " | ".join(tail)[:500]
        return mask(f"The test run did not produce any results (exit code {outcome.exit_code}). {hint}")
