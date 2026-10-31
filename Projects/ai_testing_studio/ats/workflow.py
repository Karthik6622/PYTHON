"""Workflow progress for a project: which of the nine stages are done, in progress or waiting, and what to do next."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ats.models import STAGES
from ats.repository import Project, Repository

IN_PROGRESS_STATUSES = {"queued", "running", "analyzing"}


@dataclass
class Stage:
    name: str
    status: str  # done | current | waiting | blocked | optional
    detail: str = ""


@dataclass
class WorkflowState:
    stages: list[Stage]
    next_step: str
    running: bool = False

    def stage(self, name: str) -> Stage:
        return next(s for s in self.stages if s.name == name)


def compute_workflow(repo: Repository, project: Project) -> WorkflowState:
    discovery = repo.latest_discovery(project.id)
    scenarios = repo.list_scenarios(project.id)
    approved_scenarios = [s for s in scenarios if s.status == "approved"]
    cases = repo.list_test_cases(project.id)
    approved_cases = [c for c in cases if c.status == "approved"]
    bundle = repo.latest_bundle(project.id)
    github = repo.get_github(project.id) or {}
    executions = repo.list_executions(project.id, ("full",))
    latest = executions[0] if executions else None
    healings = repo.list_healings(project.id)

    states: dict[str, tuple[str, str]] = {"Setup": ("done", project.app_base_url)}

    discovery_status = discovery[0]["status"] if discovery else ""
    if discovery_status == "completed":
        pages = len(discovery[1].pages) if discovery and discovery[1] else 0
        states["Discover"] = ("done", f"{pages} pages")
    elif discovery_status == "running":
        states["Discover"] = ("current", "running")
    else:
        states["Discover"] = ("current", "failed - run again" if discovery_status else "not started")

    if approved_scenarios:
        states["Scenarios"] = ("done", f"{len(approved_scenarios)} approved of {len(scenarios)}")
    elif scenarios:
        states["Scenarios"] = ("current", f"{len(scenarios)} awaiting review")
    else:
        states["Scenarios"] = ("waiting", "")

    if approved_cases:
        states["Test Cases"] = ("done", f"{len(approved_cases)} approved of {len(cases)}")
    elif cases:
        states["Test Cases"] = ("current", f"{len(cases)} awaiting review")
    else:
        states["Test Cases"] = ("waiting", "")

    if bundle and bundle["status"] in {"approved", "committed"}:
        states["Automation"] = ("done", f"{bundle['framework']} / {bundle['browser']}")
    elif bundle:
        states["Automation"] = ("current", "awaiting approval")
    else:
        states["Automation"] = ("waiting", "")

    states["GitHub"] = ("done", github.get("branch", "")) if github.get("branch") else ("optional", "linked" if github.get("repo_url") else "optional")

    running = bool(latest and latest["status"] in IN_PROGRESS_STATUSES)
    if running:
        states["Execute"] = ("current", latest["phase"] or latest["status"])
    elif latest and latest["status"] == "completed":
        states["Execute"] = ("done", f"run #{latest['run_number']}")
    elif latest:
        states["Execute"] = ("current", f"run #{latest['run_number']} {latest['status']}")
    else:
        states["Execute"] = ("waiting", "")

    if latest and latest["status"] == "completed":
        totals = latest["totals"] or {}
        failed = totals.get("failed", 0) + totals.get("inconclusive", 0)
        pending = [h for h in healings if h["status"] in {"proposed", "verified"}]
        if failed or pending:
            states["Analyze"] = ("current", f"{failed} failing, {len(pending)} fix(es) to review")
        else:
            states["Analyze"] = ("done", "no open failures")
        states["Report"] = ("current", "ready")
    else:
        states["Analyze"] = ("waiting", "")
        states["Report"] = ("waiting", "")

    stages = [Stage(name, *states[name]) for name in STAGES]
    return WorkflowState(stages, _next_step(stages, running), running)


def _next_step(stages: list[Stage], running: bool) -> str:
    if running:
        return "A test run is in progress."
    hints: dict[str, str] = {
        "Discover": "Run website discovery.",
        "Scenarios": "Generate and approve test scenarios.",
        "Test Cases": "Generate and approve test cases.",
        "Automation": "Generate and approve the automation project.",
        "Execute": "Execute the automated tests.",
        "Analyze": "Review failures and proposed locator fixes.",
        "Report": "Open the execution report.",
    }
    for stage in stages:
        if stage.name in hints and stage.status in {"current", "waiting"}:
            return hints[stage.name]
    return "Everything is up to date."


def progress_fraction(state: WorkflowState) -> float:
    done = sum(1 for s in state.stages if s.status == "done")
    return done / len(state.stages)


def stage_dicts(state: WorkflowState) -> list[dict[str, Any]]:
    return [{"stage": s.name, "status": s.status, "detail": s.detail} for s in state.stages]
