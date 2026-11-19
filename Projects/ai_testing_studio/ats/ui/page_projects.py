"""Projects page: create, open, configure and delete projects."""

from __future__ import annotations

from html import escape

import streamlit as st

from ats.config import get_settings
from ats.models import COVERAGE_GUIDE, CUSTOM_CATEGORIES, SCOPE_CHOICES, AuthConfig, DiscoveryLimits, parse_scope, scope_label, scope_text
from ats.repository import Project
from ats.security import UnsafeURLError, validate_target_url
from ats.services import Services
from ats.ui import storage_status, theme
from ats.ui.layers import open_next_step
from ats.ui.session import current_project, go_to, notify, owner_id, safe, select_project, show_notices
from ats.workflow import compute_workflow, next_page

FIRST_STEP = {
    "discovery": "Start by discovering the website.", "api": "Start by importing the API definition on the API page.",
    "mobile": "Start by describing the mobile app on the Mobile page.",
}

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
    # Outside the form on purpose: changing the testing type re-renders the form with only the inputs that apply to it.
    current_label = scope_label(p.test_scope) if p else SCOPE_CHOICES[0]
    scope_choice = st.selectbox(
        "Testing type", SCOPE_CHOICES, index=SCOPE_CHOICES.index(current_label), key=f"{key}_scope",
        help="The channels this project tests. Web, API and Mobile can be combined; each keeps its own scenarios, tests and results.",
    )
    channels = parse_scope(scope_choice)
    has_web = "web" in channels
    with st.form(key):
        tab_names = ["Essentials", "Discovery limits", "Authentication", "Notes"] if has_web else ["Essentials", "Notes"]
        tabs = st.tabs(tab_names)
        basics, extras = tabs[0], tabs[-1]
        with basics:
            left, right = st.columns(2)
            name = left.text_input("Project name", value=p.name if p else "", max_chars=80, placeholder="Personal Partner")
            url = right.text_input("Application URL" if has_web else "Application URL (optional)", value=p.url if p else "", placeholder="https://app.example.com")
            description = st.text_area("Description (helps the AI understand the application)", value=p.description if p else "", height=90)
            left, right = st.columns(2)
            environment = left.selectbox("Environment", ENVIRONMENTS, index=ENVIRONMENTS.index(p.environment) if p and p.environment in ENVIRONMENTS else 1)
            base_url = right.text_input("Test base URL (optional)", value=p.base_url if p else "", help="Used by generated tests when it differs from the discovery URL.")
            coverage_options = list(COVERAGE_GUIDE)
            coverage = st.selectbox("Coverage level", coverage_options, index=coverage_options.index(p.coverage) if p else 0, format_func=lambda c: c.title())
            st.caption(COVERAGE_GUIDE[coverage])
            custom = st.multiselect("Categories (used when coverage is CUSTOM)", CUSTOM_CATEGORIES, default=p.custom_categories if p else [])
        max_pages, max_depth, domains, excluded = limits.max_pages, limits.max_depth, "\n".join(limits.allowed_domains), "\n".join(limits.excluded_paths)
        shots, insecure = limits.include_screenshots, limits.ignore_https_errors
        mode, user_env, pass_env, login_url = auth.mode, auth.username_env, auth.password_env, auth.login_url
        user_sel, pass_sel, submit_sel, success, state_file = auth.username_selector, auth.password_selector, auth.submit_selector, auth.success_url_contains, auth.storage_state_file
        if has_web:
            with tabs[1]:
                a, b = st.columns(2)
                max_pages = a.number_input("Maximum pages", 1, 50, limits.max_pages)
                max_depth = b.number_input("Maximum link depth", 0, 5, limits.max_depth)
                domains = st.text_area("Additional allowed domains (one per line)", value="\n".join(limits.allowed_domains), height=70)
                excluded = st.text_area("Excluded paths (one per line)", value="\n".join(limits.excluded_paths), height=70, placeholder="/logout\n/admin")
                c, d = st.columns(2)
                shots = c.checkbox("Capture screenshots", value=limits.include_screenshots)
                insecure = d.checkbox("Ignore HTTPS certificate errors", value=limits.ignore_https_errors)
            with tabs[2]:
                modes = list(AUTH_MODES)
                mode = st.selectbox("Mode", modes, index=modes.index(auth.mode), format_func=AUTH_MODES.get)
                st.caption("Credentials are never stored here. Enter the NAMES of environment variables (or secrets); their values are read when discovery and tests run.")
                a, b = st.columns(2)
                user_env = a.text_input("Username variable", value=auth.username_env)
                pass_env = b.text_input("Password variable", value=auth.password_env)
                login_url = st.text_input("Login page URL (optional)", value=auth.login_url)
                a, b, c = st.columns(3)
                user_sel = a.text_input("Username field selector", value=auth.username_selector, help="Leave empty to detect the sign-in form automatically.")
                pass_sel = b.text_input("Password field selector", value=auth.password_selector)
                submit_sel = c.text_input("Submit button selector", value=auth.submit_selector)
                success = st.text_input("URL contains after login (optional)", value=auth.success_url_contains)
                state_file = st.text_input("Storage-state file name (in the secure folder)", value=auth.storage_state_file)
        with extras:
            if "api" in channels:
                st.info("API inputs (the OpenAPI / Postman definition, the API base URL and saved credentials) are set on the **API** and **Connections** pages.")
            if "mobile" in channels:
                st.info("Mobile app and device inputs are set on the **Mobile** page.")
            notes = st.text_area("Test data notes (never put secrets here)", value=p.test_data_notes if p else "", height=120)
        submitted = st.form_submit_button("Save project" if p else "Create project", type="primary")
    if not submitted:
        return None
    if not name.strip():
        st.error("Enter a project name.")
        return None
    try:
        clean_url = validate_target_url(url, settings.allow_private_network) if has_web or url.strip() else ""
        clean_base = validate_target_url(base_url, settings.allow_private_network) if base_url.strip() else ""
    except UnsafeURLError as exc:
        st.error(str(exc))
        return None
    lines = lambda text: [x.strip() for x in text.splitlines() if x.strip()]  # noqa: E731
    return {
        "name": name.strip(), "url": clean_url, "base_url": clean_base, "environment": environment, "description": description.strip(),
        "coverage": coverage, "custom_categories": custom, "test_data_notes": notes.strip(), "test_scope": scope_text(channels),
        "limits": DiscoveryLimits(max_pages=int(max_pages), max_depth=int(max_depth), allowed_domains=lines(domains), excluded_paths=lines(excluded), include_screenshots=shots, ignore_https_errors=insecure),
        "auth": AuthConfig(mode=mode, username_env=user_env.strip(), password_env=pass_env.strip(), login_url=login_url.strip(), username_selector=user_sel.strip(),
                           password_selector=pass_sel.strip(), submit_selector=submit_sel.strip(), success_url_contains=success.strip(), storage_state_file=state_file.strip()),
    }  # fmt: skip


def project_card(svc: Services, project: Project, active: Project | None, owner: str) -> None:
    is_active = bool(active and active.id == project.id)
    with st.container(border=True):
        a, b, c = st.columns([5, 1.2, 1], vertical_alignment="center")
        tags = theme.tag(project.environment, "info") + theme.tag(scope_label(project.test_scope), "info") + theme.tag(project.coverage.title())
        if "web" in project.channels:
            tags += theme.tag(f"{project.framework} / {project.browser}", "dim")
        if is_active:
            tags = theme.tag("active", "ok") + tags
        where = project.url or project.api_base_url or scope_label(project.test_scope)
        a.markdown(f'<div class="ats-card-title">{escape(project.name)}</div><div class="ats-card-meta">{escape(where)}</div><div style="margin-top:.35rem">{tags}</div>', unsafe_allow_html=True)
        if b.button("Open", key=f"open_{project.id}", type="secondary" if is_active else "primary", width="stretch"):
            select_project(project.id)
            open_next_step(project, compute_workflow(svc.repo, project))
            st.rerun()
        if c.button("Delete", key=f"del_{project.id}", width="stretch"):
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


def create_project_panel(svc: Services, owner: str) -> None:
    values = project_form(None, "new_project")
    if not values:
        return
    project = safe(lambda: svc.repo.create_project(owner, **values))
    if project:
        select_project(project.id)
        target = next_page(compute_workflow(svc.repo, project))
        notify(f"Project '{project.name}' created. {FIRST_STEP.get(target, 'Continue with the next step.')}")
        go_to(target)  # leaves this run, or opens the page on the next run when it only exists for this project; the page shows the notice
        st.rerun()  # only reached when navigation is not registered (isolated page runs)


def settings_panel(svc: Services, active: Project) -> None:
    values = project_form(active, "edit_project")
    if values:
        svc.repo.update_project(active.id, **values)
        svc.repo.audit(active.id, "user", "project.updated", "project", {"name": values["name"]})
        notify("Project settings saved.")
        st.rerun()


def render(svc: Services) -> None:
    theme.page_header("Projects", "Create a project and the studio carries it from discovery to a finished test report.", "STEP 00 // SETUP")
    show_notices()
    storage_status.panel(compact=True)
    owner = owner_id()
    projects = svc.repo.list_projects(owner)
    active = current_project(svc)

    if not projects:
        st.markdown("### Create your first project")
        create_project_panel(svc, owner)
        return

    tabs = ["Your projects", "New project"] + (["Settings"] if active else [])
    views = st.tabs(tabs)
    with views[0]:
        for project in projects:
            project_card(svc, project, active, owner)
    with views[1]:
        create_project_panel(svc, owner)
    if active:
        with views[2]:
            st.markdown(f"### {active.name}")
            settings_panel(svc, active)
