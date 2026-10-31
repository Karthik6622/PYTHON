"""Execute page: choose what to run, supply run-time secrets, start, watch live progress, cancel."""

from __future__ import annotations

import shutil

import pandas as pd
import streamlit as st

from ats.config import get_settings
from ats.execution.executor import discover_ids
from ats.generation.adapters.common import ENV_PLACEHOLDER
from ats.services import Services
from ats.ui.page_github import imported_files
from ats.ui.session import notify, require_project, safe, show_notices
from ats.ui.widgets import chip
from ats.workflow import IN_PROGRESS_STATUSES

POLICY_TEXT = {
    "manual": "Propose locator fixes and wait for my approval. Fixes are verified by re-running the test before they can be applied.",
    "auto_pr": "Verify fixes automatically and open a pull request with the verified locator changes (needs a GitHub token). Nothing is merged for me.",
}


def required_variables(project, files: dict[str, str]) -> list[str]:
    names = {m.group(1) for content in files.values() for m in ENV_PLACEHOLDER.finditer(content)}
    if project.auth.mode in {"env_credentials", "login_workflow"}:
        names |= {n for n in (project.auth.username_env, project.auth.password_env) if n}
    return sorted(names)


@st.fragment(run_every="2s")
def live_run(svc: Services, project_id: str, execution_id: str) -> None:
    execution = svc.repo.get_execution(execution_id)
    if execution is None:
        return
    running = execution["status"] in IN_PROGRESS_STATUSES
    if running:
        st.session_state["live_seen"] = execution_id
    st.markdown(f"Run #{execution['run_number']}: {chip(execution['status'])} {execution['phase']}")
    st.code(svc.executor.log_tail(project_id, execution_id, 60) or "Waiting for output...", language="text", height=260)
    if running and st.button("Cancel run", key=f"cancel_{execution_id}"):
        svc.executor.cancel(execution_id)
    if not running and st.session_state.get("live_seen") == execution_id:
        st.session_state.pop("live_seen", None)
        st.rerun()


def render(svc: Services) -> None:
    project = require_project(svc)
    st.header("Execute tests")
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

    active = next((e for e in svc.repo.list_executions(project.id, ("full",)) if e["status"] in IN_PROGRESS_STATUSES), None)
    if active:
        st.subheader("Run in progress")
        live_run(svc, project.id, active["id"])
        return

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

    mode = settings.execution.mode
    if mode == "docker" and not shutil.which("docker"):
        st.error("Docker is required (EXECUTION_MODE=docker) but was not found. Start Docker Desktop, or set EXECUTION_MODE=local to run on this machine.")
    elif mode == "local":
        st.info("Local execution mode: tests run directly on this machine instead of an isolated Docker container.")

    ids = discover_ids(files)
    chosen = st.multiselect("Test cases to run (empty = all)", ids, key="run_subset")
    variables = required_variables(project, files)
    secrets: dict[str, str] = {}
    if variables:
        with st.expander("Run-time values (credentials and test data)", expanded=True):
            st.caption("Values are used for this run only. They are masked in logs and never saved.")
            cols = st.columns(2)
            for index, name in enumerate(variables):
                secrets[name] = cols[index % 2].text_input(name, type="password", key=f"secret_{name}")

    policy_options = list(POLICY_TEXT)
    current_policy = svc.analysis.policy_for(project.id)
    policy = st.radio("When a locator breaks", policy_options, index=policy_options.index(current_policy), format_func=lambda p: {"manual": "Ask me first", "auto_pr": "Verify, then open a pull request"}[p], help=POLICY_TEXT[current_policy])
    st.caption(POLICY_TEXT[policy])
    if policy == "auto_pr" and not svc.tokens.get(project.id):
        st.warning("No GitHub token is available for this project, so pull requests will be skipped (the verified fixes stay available for review).")
    svc.analysis.policies[project.id] = policy
    analyze = st.checkbox("Analyze failures after the run", value=True)

    if st.button("Start execution", type="primary", disabled=not files):
        execution_id = safe(
            lambda: svc.executor.start(
                project, files, secrets={k: v for k, v in secrets.items() if v}, framework=framework, browser=browser, bundle_id=bundle_id,
                source="github" if ref else "bundle", branch=ref, test_case_ids=chosen or None, analyze=analyze,
            )
        )
        if execution_id:
            notify("Execution started.")
            st.rerun()

    history = svc.repo.list_executions(project.id, ("full",))
    if history:
        st.subheader("Previous runs")
        rows = [{"Run": e["run_number"], "Status": e["status"], "Framework": e["framework"], "Browser": e["browser"], "Passed": e["totals"].get("passed", ""), "Failed": e["totals"].get("failed", ""), "Healed": e["totals"].get("healed", ""), "Started": e["started_at"]} for e in history[:15]]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
