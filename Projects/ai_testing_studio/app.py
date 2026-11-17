"""AI Autonomous Testing Studio - Streamlit entry point.

Run:  streamlit run app.py
"""

from __future__ import annotations

from functools import partial

import streamlit as st

from ats.ui import (
    page_audit,
    page_automation,
    page_discovery,
    page_execute,
    page_github,
    page_projects,
    page_reports,
    page_results,
    page_review,
    theme,
)
from ats.ui.session import current_project, flush_cookie, get_services, go_to, owner_id, register_pages, select_project
from ats.workflow import WorkflowState, compute_workflow, next_page, progress_fraction

st.set_page_config(page_title="ATS Studio", page_icon=":material/bolt:", layout="wide", initial_sidebar_state="expanded")


def sidebar(svc, project, state: WorkflowState | None) -> None:  # noqa: ANN001
    with st.sidebar:
        st.markdown(theme.brand(), unsafe_allow_html=True)
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
                go_to(next_page(state))
        st.caption("Projects are private to this browser.")


def main() -> None:
    svc = get_services()
    owner_id()
    flush_cookie()
    theme.apply()

    pages = [
        st.Page(partial(page_projects.render, svc), title="Projects", icon=":material/folder:", url_path="projects", default=True),
        st.Page(partial(page_discovery.render, svc), title="Discovery", icon=":material/travel_explore:", url_path="discovery"),
        st.Page(partial(page_review.render_scenarios, svc), title="Scenarios", icon=":material/account_tree:", url_path="scenarios"),
        st.Page(partial(page_review.render_test_cases, svc), title="Test cases", icon=":material/checklist:", url_path="test-cases"),
        st.Page(partial(page_automation.render, svc), title="Automation", icon=":material/code:", url_path="automation"),
        st.Page(partial(page_github.render, svc), title="GitHub", icon=":material/merge:", url_path="github"),
        st.Page(partial(page_execute.render, svc), title="Execute", icon=":material/play_arrow:", url_path="execute"),
        st.Page(partial(page_results.render, svc), title="Results", icon=":material/fact_check:", url_path="results"),
        st.Page(partial(page_reports.render, svc), title="Reports", icon=":material/description:", url_path="reports"),
        st.Page(partial(page_audit.render, svc), title="Status", icon=":material/shield:", url_path="audit"),
    ]
    register_pages(pages)
    page = st.navigation(pages)

    project = current_project(svc)
    state = compute_workflow(svc.repo, project) if project else None
    sidebar(svc, project, state)
    if state:
        theme.pipeline(state)
    page.run()


main()
