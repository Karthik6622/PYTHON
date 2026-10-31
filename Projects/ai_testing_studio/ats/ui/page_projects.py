"""Projects page: create, open, configure and delete projects."""

from __future__ import annotations

import streamlit as st

from ats.config import get_settings
from ats.models import COVERAGE_GUIDE, CUSTOM_CATEGORIES, AuthConfig, DiscoveryLimits
from ats.repository import Project
from ats.security import UnsafeURLError, validate_target_url
from ats.services import Services
from ats.ui.session import current_project, notify, owner_id, safe, select_project, show_notices
from ats.ui.widgets import stage_tracker
from ats.workflow import compute_workflow

ENVIRONMENTS = ["Dev", "QA", "Staging", "UAT", "Production-like"]
AUTH_MODES = {
    "none": "No authentication", "storage_state": "Saved browser session (storage state)", "env_credentials": "Username / password from environment variables",
    "login_workflow": "Scripted login form", "manual_capture": "Sign in manually in a browser window",
}  # fmt: skip


def project_form(existing: Project | None, key: str) -> dict | None:
    """Render the project form. Returns validated field values when submitted, else None."""
    settings = get_settings()
    p = existing
    limits, auth = (p.limits if p else DiscoveryLimits()), (p.auth if p else AuthConfig())
    with st.form(key):
        left, right = st.columns(2)
        name = left.text_input("Project name", value=p.name if p else "", max_chars=80)
        url = right.text_input("Application URL", value=p.url if p else "", placeholder="https://app.example.com")
        left, right = st.columns(2)
        environment = left.selectbox("Environment", ENVIRONMENTS, index=ENVIRONMENTS.index(p.environment) if p and p.environment in ENVIRONMENTS else 1)
        base_url = right.text_input("Test base URL (optional)", value=p.base_url if p else "", help="Used by generated tests when it differs from the discovery URL.")
        description = st.text_area("Description (helps the AI understand the application)", value=p.description if p else "", height=80)
        coverage_options = list(COVERAGE_GUIDE)
        coverage = st.selectbox("Coverage level", coverage_options, index=coverage_options.index(p.coverage) if p else 0, format_func=lambda c: c.title())
        st.caption(COVERAGE_GUIDE[coverage])
        custom = st.multiselect("Categories (used when coverage is CUSTOM)", CUSTOM_CATEGORIES, default=p.custom_categories if p else [])
        with st.expander("Discovery limits"):
            a, b = st.columns(2)
            max_pages = a.number_input("Maximum pages", 1, 50, limits.max_pages)
            max_depth = b.number_input("Maximum link depth", 0, 5, limits.max_depth)
            domains = st.text_area("Additional allowed domains (one per line)", value="\n".join(limits.allowed_domains), height=70)
            excluded = st.text_area("Excluded paths (one per line)", value="\n".join(limits.excluded_paths), height=70, placeholder="/logout\n/admin")
            c, d = st.columns(2)
            shots = c.checkbox("Capture screenshots", value=limits.include_screenshots)
            insecure = d.checkbox("Ignore HTTPS certificate errors", value=limits.ignore_https_errors)
        with st.expander("Authentication"):
            modes = list(AUTH_MODES)
            mode = st.selectbox("Mode", modes, index=modes.index(auth.mode), format_func=AUTH_MODES.get)
            st.caption("Credentials are never stored. Enter the NAMES of environment variables; values are provided when you run the tests.")
            a, b = st.columns(2)
            user_env = a.text_input("Username variable", value=auth.username_env)
            pass_env = b.text_input("Password variable", value=auth.password_env)
            login_url = st.text_input("Login page URL", value=auth.login_url)
            a, b, c = st.columns(3)
            user_sel = a.text_input("Username field selector", value=auth.username_selector)
            pass_sel = b.text_input("Password field selector", value=auth.password_selector)
            submit_sel = c.text_input("Submit button selector", value=auth.submit_selector)
            success = st.text_input("URL contains after login", value=auth.success_url_contains)
            state_file = st.text_input("Storage-state file name (in the secure folder)", value=auth.storage_state_file)
        notes = st.text_area("Test data notes (never put secrets here)", value=p.test_data_notes if p else "", height=70)
        submitted = st.form_submit_button("Save project" if p else "Create project", type="primary")
    if not submitted:
        return None
    if not name.strip():
        st.error("Enter a project name.")
        return None
    try:
        clean_url = validate_target_url(url, settings.allow_private_network)
        clean_base = validate_target_url(base_url, settings.allow_private_network) if base_url.strip() else ""
    except UnsafeURLError as exc:
        st.error(str(exc))
        return None
    lines = lambda text: [x.strip() for x in text.splitlines() if x.strip()]  # noqa: E731
    return {
        "name": name.strip(), "url": clean_url, "base_url": clean_base, "environment": environment, "description": description.strip(),
        "coverage": coverage, "custom_categories": custom, "test_data_notes": notes.strip(),
        "limits": DiscoveryLimits(max_pages=int(max_pages), max_depth=int(max_depth), allowed_domains=lines(domains), excluded_paths=lines(excluded), include_screenshots=shots, ignore_https_errors=insecure),
        "auth": AuthConfig(mode=mode, username_env=user_env.strip(), password_env=pass_env.strip(), login_url=login_url.strip(), username_selector=user_sel.strip(),
                           password_selector=pass_sel.strip(), submit_selector=submit_sel.strip(), success_url_contains=success.strip(), storage_state_file=state_file.strip()),
    }  # fmt: skip


def render(svc: Services) -> None:
    st.header("Projects")
    show_notices()
    owner = owner_id()
    projects = svc.repo.list_projects(owner)
    active = current_project(svc)

    if projects:
        st.subheader("Your projects")
        for project in projects:
            with st.container(border=True):
                a, b, c, d = st.columns([4, 3, 1, 1])
                a.markdown(f"**{project.name}**  \n{project.url}")
                b.caption(f"{project.environment} | coverage {project.coverage.title()} | {project.framework} / {project.browser}")
                if c.button("Open", key=f"open_{project.id}", type="primary" if not active or active.id != project.id else "secondary"):
                    select_project(project.id)
                    st.rerun()
                if d.button("Delete", key=f"del_{project.id}"):
                    st.session_state["confirm_delete"] = project.id
                if st.session_state.get("confirm_delete") == project.id:
                    st.warning("This permanently deletes the project, its generated files and its run history.")
                    x, y = st.columns(2)
                    if x.button("Yes, delete", key=f"yes_{project.id}"):
                        svc.repo.delete_project(project.id, owner)
                        st.session_state.pop("confirm_delete", None)
                        if st.session_state.get("project_id") == project.id:
                            st.session_state.pop("project_id", None)
                        st.rerun()
                    if y.button("Cancel", key=f"no_{project.id}"):
                        st.session_state.pop("confirm_delete", None)
                        st.rerun()

    if active:
        st.subheader(f"Workflow - {active.name}")
        state = compute_workflow(svc.repo, active)
        stage_tracker(state)
        st.info(f"Next: {state.next_step}")
        with st.expander("Project settings"):
            values = project_form(active, "edit_project")
            if values:
                svc.repo.update_project(active.id, **values)
                svc.repo.audit(active.id, "user", "project.updated", "project", {"name": values["name"]})
                notify("Project settings saved.")
                st.rerun()

    st.subheader("Create a new project")
    values = project_form(None, "new_project")
    if values:
        project = safe(lambda: svc.repo.create_project(owner, **values))
        if project:
            select_project(project.id)
            notify(f"Project '{project.name}' created. Continue with Discovery.")
            st.rerun()
