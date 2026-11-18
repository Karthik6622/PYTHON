"""Execute page: choose what to run, start it in the background, watch every test live, see what was repaired and reported."""

from __future__ import annotations

import shutil
from functools import partial
from html import escape

import pandas as pd
import streamlit as st

from ats.config import get_settings, lookup_secret
from ats.errors import ExecutionError
from ats.execution.executor import discover_ids
from ats.execution.runner import resolve_mode
from ats.generation.adapters.common import ENV_PLACEHOLDER
from ats.jobs import JobCancelled
from ats.services import Services
from ats.ui import jobs_ui, theme
from ats.ui.page_github import imported_files
from ats.ui.session import go_to, require_project, show_notices
from ats.ui.widgets import chip
from ats.workflow import IN_PROGRESS_STATUSES

POLICY_TEXT = {
    "manual": "Propose locator fixes and wait for my approval. Fixes are verified by re-running the test before they can be applied.",
    "auto_pr": "Verify fixes automatically and open a pull request with the verified locator changes (needs a GitHub token). Nothing is merged for me.",
}
STAGES = ["Prepare", "Run tests", "Analyze", "Auto-fix", "Report"]
STATUS_LABEL = {"PASS": "✅ Passed", "FAIL": "❌ Failed", "HEALED": "🛠 Fixed automatically", "SKIPPED": "⏭ Skipped", "INCONCLUSIVE": "❔ Inconclusive"}


def required_variables(project, files: dict[str, str], extra: list[str] | None = None) -> list[str]:  # noqa: ANN001
    names = {m.group(1) for content in files.values() for m in ENV_PLACEHOLDER.finditer(content)}
    if project.auth.mode in {"env_credentials", "login_workflow"}:
        names |= {n for n in (project.auth.username_env, project.auth.password_env) if n}
    names |= set(extra or [])
    return sorted(names)


def stage_index(phase: str, status: str) -> int:
    """Which of the five stages a run is in, from its phase text."""
    text = (phase or "").lower()
    if status in {"completed"} and text in {"complete", "results collected", ""}:
        return len(STAGES)
    if text.startswith(("running", "executing")):
        return 1
    if text.startswith(("analyz", "collecting", "re-checking")):
        return 2
    if text.startswith(("auto-fix", "self-healing", "saving", "healing")):
        return 3
    if text.startswith(("drafting", "writing", "complete")):
        return 4
    return 0


def timeline(current: int) -> str:
    steps = []
    for number, name in enumerate(STAGES):
        kind = "done" if number < current else "current" if number == current else ""
        steps.append(f'<div class="ats-step {kind}"><span class="n">{number + 1:02d}</span><span class="t">{escape(name)}</span><span class="d">&nbsp;</span></div>')
    return f'<div class="ats-pipe" style="grid-template-columns: repeat({len(STAGES)}, minmax(0, 1fr))">{"".join(steps)}</div>'


def test_rows(svc: Services, project_id: str, execution: dict, running: bool) -> list[dict[str, str]]:
    totals = execution.get("totals") or {}
    expected = totals.get("expected") or []  # empty until the run has started
    final = svc.repo.result_statuses(execution["id"])
    live = totals.get("live") or {}
    titles = {c.test_case_id: c.title for c in svc.repo.list_test_cases(project_id)}
    rows, marked = [], False
    for tc in expected or list(final):
        status = final.get(tc) or live.get(tc)
        if status:
            label = STATUS_LABEL.get(status, status)
        elif running and not marked:
            label, marked = "⏳ Running", True
        else:
            label = "· Waiting"
        rows.append({"Test case": tc, "Title": titles.get(tc, ""), "Status": label})
    return rows


def live_body(svc: Services, project_id: str, execution: dict) -> None:
    """Stage timeline, counters and a per-test status table for one run."""
    running = execution["status"] in IN_PROGRESS_STATUSES
    st.markdown(timeline(stage_index(execution["phase"], execution["status"])), unsafe_allow_html=True)
    rows = test_rows(svc, project_id, execution, running)
    counts = {label: sum(r["Status"] == label for r in rows) for label in STATUS_LABEL.values()}
    a, b, c, d = st.columns(4)
    a.metric("Tests", len(rows))
    b.metric("Passed", counts[STATUS_LABEL["PASS"]])
    c.metric("Failed", counts[STATUS_LABEL["FAIL"]])
    d.metric("Fixed automatically", counts[STATUS_LABEL["HEALED"]])
    st.caption(f"Run #{execution['run_number']} | {execution['phase'] or execution['status']}")
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", height=min(60 + 36 * len(rows), 420))
    with st.expander("Runner log", expanded=False):
        st.code(svc.executor.log_tail(project_id, execution["id"], 50) or "Waiting for output...", language="text")


@st.fragment(run_every="3s")
def live_tests(svc: Services, project_id: str, execution_id: str) -> None:
    """Live view of a run on the Results page: refreshes itself and reloads the page once the run has finished."""
    execution = svc.repo.get_execution(execution_id)
    if execution is None:
        return
    running = execution["status"] in IN_PROGRESS_STATUSES
    if not running and st.session_state.get("_live_seen") == execution_id:
        st.session_state.pop("_live_seen", None)
        st.rerun()
    if running:
        st.session_state["_live_seen"] = execution_id
    live_body(svc, project_id, execution)


live_run = live_tests  # kept for pages that embed the live view


def live_active_run(svc: Services, project_id: str) -> None:
    """Drawn inside the job's own polling fragment: finds the run when its record appears, so the view never needs a page reload."""
    execution = svc.repo.active_execution(project_id)
    if execution is None:
        st.caption("Preparing the run...")
        return
    live_body(svc, project_id, execution)


def summary(svc: Services, execution: dict) -> None:
    """What the last finished run produced, including what the automatic repair did."""
    totals = execution.get("totals") or {}
    st.markdown(f"Last run: #{execution['run_number']} {chip(execution['status'])} {execution['started_at'][:19]}")
    cols = st.columns(5)
    for col, (label, key) in zip(cols, [("Tests", "total"), ("Passed", "passed"), ("Fixed automatically", "healed"), ("Failed", "failed"), ("Pass rate %", "pass_rate")], strict=True):
        col.metric(label, totals.get(key, 0))
    fix = totals.get("autofix") or {}
    if fix:
        parts = []
        if fix.get("repaired") or fix.get("healed_locators") or fix.get("promoted"):
            parts.append(f"{len(fix.get('repaired', []))} script repair(s), {len(fix.get('healed_locators', [])) + len(fix.get('promoted', []))} locator fix(es)")
        if fix.get("pushed"):
            parts.append(f"pushed to branch `{fix.get('branch')}`")
        if fix.get("defects") or fix.get("unresolved"):
            parts.append(f"{len(fix.get('defects', [])) + len(fix.get('unresolved', []))} failure(s) reported for review")
        if parts:
            st.info("Auto-fix: " + "; ".join(parts) + ".")
        if fix.get("push_error"):
            st.warning(f"The fixes could not be pushed to GitHub: {fix['push_error']}")
    if execution.get("error"):
        st.error(execution["error"])
    if st.button("Open the detailed results", key="to_results"):
        go_to("results")


def start_run(svc: Services, project, files, framework, browser, bundle_id, ref, chosen, secrets, analyze) -> None:  # noqa: ANN001
    """The whole run (tests, analysis, automatic repair) is one background job: it survives closing the tab or locking the screen."""

    def work(ctx):  # noqa: ANN001, ANN202
        execution_id = svc.executor.run(
            project, files, secrets=secrets, framework=framework, browser=browser, bundle_id=bundle_id, source="github" if ref else "bundle", branch=ref,
            test_case_ids=chosen or None, analyze=analyze, progress=ctx.reporter, cancel=ctx.cancel_event,
        )
        execution = svc.repo.get_execution(execution_id) or {}
        if execution.get("status") == "cancelled":
            raise JobCancelled()
        if execution.get("status") == "error":
            raise ExecutionError(execution.get("error") or "The run could not be completed.")
        totals = execution.get("totals") or {}
        return {"execution_id": execution_id, "run": execution.get("run_number", 0), "passed": totals.get("passed", 0), "healed": totals.get("healed", 0), "failed": totals.get("failed", 0)}

    jobs_ui.start_job(
        svc, project, "execution", "Test execution", work, next_page="results",
        notice="Run #{run} finished: {passed} passed, {healed} fixed automatically, {failed} failed.",
    )


def render(svc: Services) -> None:
    project = require_project(svc)
    theme.page_header("Execute", "Run the approved tests in the background, watch every test live, and let the studio repair automation problems and report real defects.", "STEP 06 // EXECUTE")
    show_notices()
    settings = get_settings()
    bundle = svc.repo.latest_bundle(project.id)
    imported = imported_files(project.id)
    sources = []
    if bundle:
        sources.append("Generated automation project")
    if imported:
        sources.append("Imported from GitHub")
    if not sources:
        st.info("Generate an automation project (or import tests from GitHub) first.")
        return

    if jobs_ui.running_panel(svc, project, ("execution",), "Run in progress", extra=partial(live_active_run, svc, project.id)):
        return
    jobs_ui.last_problem(svc, project, ("execution",))

    source = st.radio("What to run", sources, horizontal=True)
    if source == "Generated automation project":
        if bundle["status"] == "draft":
            st.warning("This automation project has not been approved. Approve it on the Automation page, or run it anyway.")
        files, framework, browser, bundle_id, ref = svc.store.read_all(project.id, bundle["id"]), bundle["framework"], bundle["browser"], bundle["id"], ""
    else:
        files, ref = imported
        framework = st.selectbox("Framework of the imported tests", ["playwright_python", "playwright_typescript", "playwright_javascript", "selenium_python", "selenium_java"], index=0)
        browser, bundle_id = project.browser, None
    st.caption(f"{len(files)} files | framework {framework} | browser {browser} | target {project.app_base_url}")

    mode = resolve_mode(settings.execution.mode)
    if mode == "docker" and not shutil.which("docker"):
        st.error("Docker is required (EXECUTION_MODE=docker) but was not found. Start Docker Desktop, or set EXECUTION_MODE=local (or auto) to run on this machine.")
    elif mode == "local":
        st.caption("Local mode: tests run as a separate process on this machine (Docker is not used).")

    ids = discover_ids(files)
    chosen = st.multiselect("Test cases to run (empty = all)", ids, key="run_subset")
    extra = svc.connections.variable_names(project.id) if hasattr(svc, "connections") else []
    variables = required_variables(project, files, extra)
    secrets: dict[str, str] = {}
    if hasattr(svc, "connections"):
        secrets.update(svc.connections.environment(project.id))
    if variables:
        configured = {name: lookup_secret(name) for name in variables if lookup_secret(name)}
        secrets.update({k: v for k, v in configured.items() if k not in secrets})
        missing = [name for name in variables if name not in secrets]
        supplied = [name for name in variables if name in secrets]
        if supplied:
            st.markdown("".join(theme.tag(name, "ok") for name in supplied) + '<span class="ats-card-meta"> supplied from saved connections or configured secrets</span>', unsafe_allow_html=True)
        if missing:
            with st.expander("Run-time values (credentials and test data)", expanded=True):
                st.caption("Values are used for this run only. They are masked in logs and never saved. Save them once on the Connections page to avoid typing them again.")
                cols = st.columns(2)
                for index, name in enumerate(missing):
                    secrets[name] = cols[index % 2].text_input(name, type="password", key=f"secret_{name}")

    link = svc.repo.get_github(project.id) or {}
    with st.container(border=True):
        auto = st.toggle("Auto-fix automation problems", value=svc.analysis.autofix.get(project.id, True), help="Repair locators, waits and script logic, re-run the failed tests, save the fixed project and push it to the GitHub branch.")
        svc.analysis.autofix[project.id] = auto
        if auto:
            branch = link.get("branch")
            st.caption(
                "After the run the studio classifies every failure. Automation problems (a locator that stopped matching, a missing wait or click, a wrong sequence) are repaired and re-run "
                f"(up to {settings.healing.autofix_rounds} rounds) and the fixed project is saved"
                + (f" and pushed to branch `{branch}`." if branch else ".")
                + " Failures caused by the application are never hidden: they go into a failure report with evidence."
            )
            if branch and not svc.tokens.get(project.id):
                st.warning(f"Add a GitHub token on the GitHub page so the fixes can be pushed to `{branch}`. Without it they are saved in the studio only.")
        else:
            policy_options = list(POLICY_TEXT)
            current_policy = svc.analysis.policy_for(project.id)
            policy = st.radio("When a locator breaks", policy_options, index=policy_options.index(current_policy), format_func=lambda p: {"manual": "Ask me first", "auto_pr": "Verify, then open a pull request"}[p])
            st.caption(POLICY_TEXT[policy])
            svc.analysis.policies[project.id] = policy
    analyze = st.checkbox("Analyze failures after the run", value=True)

    if st.button("Start execution", type="primary", disabled=not files):
        start_run(svc, project, files, framework, browser, bundle_id, ref, chosen, {k: v for k, v in secrets.items() if v}, analyze)

    history = svc.repo.list_executions(project.id, ("full",))
    if history:
        summary(svc, history[0])
        st.subheader("Previous runs")
        rows = [{"Run": e["run_number"], "Status": e["status"], "Framework": e["framework"], "Browser": e["browser"], "Passed": e["totals"].get("passed", ""), "Failed": e["totals"].get("failed", ""), "Fixed": e["totals"].get("healed", ""), "Started": e["started_at"]} for e in history[:15]]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
