"""Workflow progress for a project: which of the nine stages are done, in progress or waiting, and what to do next."""

from __future__ import annotations

from dataclasses import dataclass, field
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
    discover_page: str = "discovery"  # where the Discover step is done: Web discovery, the API page or the Mobile page
    layers: dict[str, str] = field(default_factory=dict)  # stage name -> first layer that still needs work (multi-channel projects)

    def stage(self, name: str) -> Stage:
        return next(s for s in self.stages if s.name == name)


def _web_discovery(repo: Repository, project: Project) -> tuple[str, str]:
    discovery = repo.latest_discovery(project.id)
    status = discovery[0]["status"] if discovery else ""
    if status == "completed":
        pages = len(discovery[1].pages) if discovery and discovery[1] else 0
        return "done", f"{pages} pages"
    if status == "running":
        return "current", "running"
    return "current", "failed - run again" if status else "not started"


def _inputs(repo: Repository, project: Project) -> tuple[str, str, str]:
    """The Discover stage: Web is discovered, API means a definition is imported, Mobile means the app was analysed."""
    parts: list[tuple[str, str, str]] = []  # (status, detail, page)
    if "web" in project.channels:
        parts.append((*_web_discovery(repo, project), "discovery"))
    if "api" in project.channels:
        count = len(repo.list_api_endpoints(project.id))
        parts.append(("done", f"{count} endpoints", "api") if count else ("current", "no API definition", "api"))
    if "mobile" in project.channels:
        analysed = getattr(repo, "mobile_analysis", None)  # supplied by the Mobile channel; without it the app counts as not analysed
        ready = bool(analysed(project.id)) if callable(analysed) else False
        parts.append(("done", "app analysed", "mobile") if ready else ("current", "app not analysed", "mobile"))
    if len(parts) == 1:
        return parts[0]
    todo = next((p for p in parts if p[0] != "done"), None)
    if todo is None:
        return "done", ", ".join(p[1] for p in parts), parts[0][2]
    return "current", f"{todo[1]} ({todo[2]})", todo[2]


def _review_stage(items: list, layers: list[str]) -> tuple[str, str, str]:
    """Scenarios / test cases: done when every layer of the project has approved items. Returns (status, detail, first layer still open)."""
    mine = [i for i in items if i.layer in layers]
    approved = [i for i in mine if i.status == "approved"]
    open_layers = [layer for layer in layers if not any(i.layer == layer and i.status == "approved" for i in mine)]
    if not open_layers:
        return "done", f"{len(approved)} approved of {len(mine)}", ""
    if approved:  # another channel of the project still has nothing approved
        return "current", f"{len(approved)} approved of {len(mine)}", open_layers[0]
    if mine:
        return "current", f"{len(mine)} awaiting review", next((layer for layer in open_layers if any(i.layer == layer for i in mine)), open_layers[0])
    return "waiting", "", open_layers[0]


def compute_workflow(repo: Repository, project: Project) -> WorkflowState:
    layers = project.layers
    scenarios = repo.list_scenarios(project.id)
    cases = repo.list_test_cases(project.id)
    bundles = {layer: repo.latest_bundle(project.id, layer=layer) for layer in layers}
    github = repo.get_github(project.id) or {}
    executions = repo.list_executions(project.id, ("full",))
    latest = executions[0] if executions else None
    healings = repo.list_healings(project.id)

    states: dict[str, tuple[str, str]] = {"Setup": ("done", project.app_base_url or project.api_base_url)}
    open_layer: dict[str, str] = {}

    discover_status, discover_detail, discover_page = _inputs(repo, project)
    states["Discover"] = (discover_status, discover_detail)

    for stage, items in (("Scenarios", scenarios), ("Test Cases", cases)):
        status, detail, layer = _review_stage(items, layers)
        states[stage] = (status, detail)
        if layer:
            open_layer[stage] = layer

    waiting = [layer for layer in layers if not bundles[layer] or bundles[layer]["status"] not in {"approved", "committed"}]
    existing = [b for b in bundles.values() if b]
    if not waiting:
        states["Automation"] = ("done", " + ".join(f"{b['framework']} / {b['browser']}" for b in bundles.values()))
    elif existing:
        states["Automation"] = ("current", "awaiting approval")
        open_layer["Automation"] = next((layer for layer in waiting if bundles[layer]), waiting[0])
    else:
        states["Automation"] = ("waiting", "")
        open_layer["Automation"] = waiting[0]

    # GitHub comes right after Automation and before Execute: publish the tests to a branch, or skip it explicitly.
    if github.get("branch"):
        states["GitHub"] = ("done", github["branch"])
    elif repo.has_audit(project.id, "github.skipped"):
        states["GitHub"] = ("done", "skipped")
    elif states["Automation"][0] == "done":
        states["GitHub"] = ("current", "publish the tests to a branch, or skip")
    else:
        states["GitHub"] = ("optional", "linked" if github.get("repo_url") else "optional")

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
    return WorkflowState(stages, _next_step(stages, running), running, discover_page, open_layer)


def _next_step(stages: list[Stage], running: bool) -> str:
    if running:
        return "A test run is in progress."
    hints: dict[str, str] = {
        "Discover": "Run website discovery.",
        "Scenarios": "Generate and approve test scenarios.",
        "Test Cases": "Generate and approve test cases.",
        "Automation": "Generate and approve the automation project.",
        "GitHub": "Publish the tests to a GitHub branch (or skip).",
        "Execute": "Execute the automated tests.",
        "Analyze": "Review failures and proposed locator fixes.",
        "Report": "Open the execution report.",
    }
    for stage in stages:
        if stage.name in hints and stage.status in {"current", "waiting"}:
            return hints[stage.name]
    return "Everything is up to date."


STAGE_PAGE = {
    "Discover": "discovery", "Scenarios": "scenarios", "Test Cases": "test-cases", "Automation": "automation",
    "GitHub": "github", "Execute": "execute", "Analyze": "results", "Report": "reports",
}  # fmt: skip


def _next_stage(state: WorkflowState) -> Stage | None:
    return next((s for s in state.stages if s.name in STAGE_PAGE and s.status in {"current", "waiting"}), None)


def next_page(state: WorkflowState) -> str:
    """URL path of the page where the next workflow step is done."""
    if state.running:
        return "execute"
    stage = _next_stage(state)
    if stage is None:
        return "reports"
    return state.discover_page if stage.name == "Discover" else STAGE_PAGE[stage.name]


def next_layer(state: WorkflowState) -> str:
    """The channel the next step is about (empty when the project has one channel or the step is not per channel)."""
    stage = _next_stage(state)
    return state.layers.get(stage.name, "") if stage and not state.running else ""


def progress_fraction(state: WorkflowState) -> float:
    done = sum(1 for s in state.stages if s.status == "done")
    return done / len(state.stages)


def stage_dicts(state: WorkflowState) -> list[dict[str, Any]]:
    return [{"stage": s.name, "status": s.status, "detail": s.detail} for s in state.stages]
