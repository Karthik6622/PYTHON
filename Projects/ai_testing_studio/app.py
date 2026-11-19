"""RK Testing Studio - Streamlit entry point.

Run:  streamlit run app.py
"""

from __future__ import annotations

import streamlit as st

from ats.ui import (
    page_api,
    page_audit,
    page_automation,
    page_connections,
    page_discovery,
    page_execute,
    page_github,
    page_mobile,
    page_projects,
    page_reports,
    page_results,
    page_review,
    jobs_ui,
    storage_status,
    theme,
)
from ats.persistence import get_durable
from ats.ui.auth_session import require_login, user_chip
from ats.ui.layers import LayerPage, build_pages, open_next_step, page_of
from ats.ui.session import current_project, flush_cookie, get_services, owner_id, register_pages, resume_pending_navigation, select_project
from ats.workflow import WorkflowState, compute_workflow, progress_fraction

st.set_page_config(page_title="RK Testing Studio", page_icon=":material/bolt:", layout="wide", initial_sidebar_state="expanded")


def sidebar(svc, project, state: WorkflowState | None, pages) -> None:  # noqa: ANN001
    with st.sidebar:
        st.markdown(theme.brand(), unsafe_allow_html=True)  # the logo comes first; Streamlit's own page list would be drawn above it, so it is hidden
        for page in pages:
            st.page_link(page)
        projects = svc.repo.list_projects(owner_id())
        if projects:
            names = {p.id: p.name for p in projects}
            ids = list(names)
            current = st.session_state.get("project_id")
            index = ids.index(current) if current in ids else None
            choice = st.selectbox("Project", ids, index=index, format_func=names.get, placeholder="Choose a project")
            if choice and choice != current:
                select_project(choice)
                st.rerun()
        if project and state:
            st.progress(progress_fraction(state), text=f"{int(progress_fraction(state) * 100)}% complete")
            st.markdown(f'<div class="ats-next"><b>NEXT</b> // {state.next_step}</div>', unsafe_allow_html=True)
            if st.button("Go to next step", type="primary", width="stretch"):
                open_next_step(project, state)
            jobs_ui.sidebar_activity(svc, project.id)
        user_chip()


# The navigation, one row per page. A row with `layers` is shown only for projects that have one of those channels
# ("ui" = Web, "api", "mobile"); `needs_project` rows appear once a project is open. Add a page by adding a row.
PAGE_TABLE = [
    LayerPage("projects", "Projects", ":material/folder:", page_of(page_projects.render), default=True),
    LayerPage("discovery", "Discovery", ":material/travel_explore:", page_of(page_discovery.render), layers=("ui",)),
    LayerPage("api", "API", ":material/api:", page_of(page_api.render), layers=("api",)),
    LayerPage("mobile", "Mobile", ":material/smartphone:", page_of(page_mobile.render), layers=("mobile",)),
    LayerPage("connections", "Connections", ":material/key:", page_of(page_connections.render), needs_project=True),
    LayerPage("scenarios", "Scenarios", ":material/account_tree:", page_of(page_review.render_scenarios)),
    LayerPage("test-cases", "Test cases", ":material/checklist:", page_of(page_review.render_test_cases)),
    LayerPage("automation", "Automation", ":material/code:", page_of(page_automation.render)),
    LayerPage("github", "GitHub", ":material/merge:", page_of(page_github.render)),
    LayerPage("execute", "Execute", ":material/play_arrow:", page_of(page_execute.render)),
    LayerPage("results", "Results", ":material/fact_check:", page_of(page_results.render)),
    LayerPage("reports", "Reports", ":material/description:", page_of(page_reports.render)),
    LayerPage("audit", "Status", ":material/shield:", page_of(page_audit.render)),
]


def main() -> None:
    get_durable().start()  # brings the data back on a host that lost its disk; must run before any database is opened
    svc = get_services()
    owner_id()
    flush_cookie()
    theme.apply()
    if not require_login():
        return
    storage_status.alert()

    if not st.session_state.get("project_id"):  # a new session (reconnect, new tab) continues with the project used last
        recent = svc.repo.list_projects(owner_id())
        if recent:
            select_project(recent[0].id)
    project = current_project(svc)  # the navigation depends on the channels of the open project
    pages = build_pages(svc, project, PAGE_TABLE)
    register_pages(pages)
    page = st.navigation(pages, position="hidden")
    resume_pending_navigation()
    jobs_ui.follow_finished(svc)  # a job this session was watching has finished: report it and move to the next step
    state = compute_workflow(svc.repo, project) if project else None
    sidebar(svc, project, state, pages)
    if state:
        theme.pipeline(state)
    page.run()


main()
