"""Discovery page: run website analysis, inspect pages and the locator repository, manage authentication sessions."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from ats.config import get_settings
from ats.services import Services
from ats.ui import jobs_ui, theme
from ats.ui.session import go_to, require_project, show_notices
from ats.ui.widgets import chip


def start_discovery(svc: Services, project) -> None:  # noqa: ANN001
    """Discovery runs in the background: it keeps going when the browser tab closes or the screen locks."""

    def work(ctx):  # noqa: ANN001, ANN202
        result = svc.discovery.run(project, on_progress=ctx.reporter, cancel=ctx.cancel_event)
        return {"pages": len(result.pages)}

    jobs_ui.start_job(
        svc, project, "discovery", "Website discovery", work, next_page="connections",
        notice="Discovery finished: {pages} views found. Next: check the connections (sign-in details).",
    )  # fmt: skip


def authentication_panel(svc: Services, project) -> None:  # noqa: ANN001
    auth = project.auth
    if auth.mode not in {"manual_capture", "storage_state"}:
        return
    with st.expander("Saved sign-in session"):
        st.caption("Sessions are kept in the secure folder and never exported or committed.")
        login_url = st.text_input("Login URL to open", value=auth.login_url or project.url, key="capture_url")
        if st.button("Open a browser window and capture my session", help="Works when the studio runs on your own computer."):
            with st.spinner("A browser window opened. Sign in, then close it..."):
                name = safe(lambda: svc.discovery.capture_session(project, login_url))
            if name:
                auth.mode, auth.storage_state_file = "storage_state", name
                svc.repo.update_project(project.id, auth=auth)
                st.success(f"Session saved as {name}.")
        upload = st.file_uploader("...or upload a Playwright storage-state JSON file", type=["json"], key="state_upload")
        if upload is not None and st.button("Save uploaded session"):
            try:
                data = json.loads(upload.getvalue())
                if not isinstance(data, dict) or "cookies" not in data:
                    raise ValueError
            except ValueError:
                st.error("That file is not a Playwright storage-state file.")
            else:
                target = get_settings().secure_dir / f"{project.id}_state.json"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps(data), encoding="utf-8")
                auth.mode, auth.storage_state_file = "storage_state", target.name
                svc.repo.update_project(project.id, auth=auth)
                st.success("Session saved.")


def overview_tab(result, locators) -> None:  # noqa: ANN001
    a, b, c, d = st.columns(4)
    a.metric("Pages", len(result.pages))
    b.metric("Elements", sum(len(p.elements) for p in result.pages))
    c.metric("Locators", len(locators))
    d.metric("Forms", sum(len(p.forms) for p in result.pages))
    if result.summary:
        st.markdown("### Application understanding")
        st.write(result.summary)
        modules, workflows = result.analysis.get("modules", []), result.analysis.get("workflows", [])
        left, right = st.columns(2)
        if modules:
            left.markdown("**Modules**")
            for module in modules:
                left.markdown(f"- {module if isinstance(module, str) else module.get('name', module)}")
        if workflows:
            right.markdown("**Workflows**")
            for workflow in workflows:
                right.markdown(f"- {workflow if isinstance(workflow, str) else workflow.get('name', workflow)}")
        risks = result.analysis.get("risks", [])
        if risks:
            st.markdown("**Risks**")
            for risk in risks:
                st.markdown(f"- {risk}")
    if result.warnings:
        with st.expander(f"Notes from discovery ({len(result.warnings)})"):
            for warning in result.warnings:
                st.markdown(f"- {warning}")


def pages_tab(result) -> None:  # noqa: ANN001
    pages = pd.DataFrame(
        [{"Key": p.page_key, "View": p.view_name or p.title, "Signed in": p.signed_in, "How to reach": " > ".join(p.reached_by) or "Open the URL",
          "URL": p.final_url or p.url, "Elements": len(p.elements), "Forms": len(p.forms), "Console errors": len(p.console_errors)} for p in result.pages]
    )  # fmt: skip
    st.dataframe(pages, hide_index=True, width="stretch")
    if result.skipped:
        with st.expander(f"Skipped URLs ({len(result.skipped)})"):
            st.dataframe(pd.DataFrame(result.skipped), hide_index=True, width="stretch")
    chosen = st.selectbox("Inspect a page", [p.page_key for p in result.pages])
    page = next(p for p in result.pages if p.page_key == chosen)
    left, right = st.columns([2, 3])
    with left:
        if page.screenshot and Path(page.screenshot).is_file():
            st.image(page.screenshot, caption=page.view_name or page.title or page.url)
        if page.reached_by:
            st.markdown("**How to reach**: " + " → ".join(page.reached_by))
        if page.headings:
            st.markdown("**Headings**: " + " | ".join(page.headings[:6]))
        if page.console_errors:
            st.markdown("**Console errors**")
            st.code("\n".join(page.console_errors[:5]))
    with right:
        elements = pd.DataFrame(
            [{"Role": e.get("role") or e.get("tag"), "Name": e.get("name") or e.get("label") or e.get("text") or e.get("placeholder"), "Type": e.get("type"),
              "Required": e.get("required"), "Test id": e.get("testid")} for e in page.elements if e.get("visible")]
        )  # fmt: skip
        st.dataframe(elements, hide_index=True, width="stretch", height=360)


def locators_tab(locators) -> None:  # noqa: ANN001
    query = st.text_input("Filter locators", placeholder="login, button, email...")
    rows = [
        {"Element": s.element_key, "Page": s.page_key, "Role": s.role or s.tag, "Name": s.name, "Preferred": s.preferred.display(), "Alternatives": len(s.alternatives),
         "Stability": round(s.stability, 2), "Intent": s.intent}
        for s in locators if not query or query.lower() in f"{s.element_key} {s.name} {s.intent}".lower()
    ]  # fmt: skip
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", height=420)
    st.caption("Stability is a heuristic: test ids and unique accessible names score highest; positional CSS and XPath score lowest.")


def render(svc: Services) -> None:
    project = require_project(svc)
    theme.page_header(
        "Discovery",
        "A real browser signs in, clicks through every menu, tab and view (signed-in and public) and records elements, forms and screenshots.",
        "STEP 01 // DISCOVER",
    )
    show_notices()
    auth_note = "" if project.auth.mode == "none" else theme.tag(f"auth: {project.auth.mode}", "info")
    ai_note = theme.tag("AI ready", "ok") if get_settings().model.configured else theme.tag("AI key missing", "bad")
    st.markdown(f'{theme.tag(project.url, "dim")}{auth_note}{ai_note}', unsafe_allow_html=True)
    if not get_settings().model.configured:
        st.caption("Discovery works without the AI model; only the application summary and locator notes are skipped.")
    if jobs_ui.running_panel(svc, project, ("discovery",), "Discovery in progress"):
        return
    jobs_ui.last_problem(svc, project, ("discovery",))
    authentication_panel(svc, project)

    latest = svc.repo.latest_discovery(project.id)
    if st.button("Run discovery again" if latest else "Run discovery", type="primary"):
        start_discovery(svc, project)

    if not latest:
        st.info("No discovery has been run yet.")
        return
    row, result = latest
    st.markdown(f"Last run: {chip(row['status'])} started {row['started_at']}")
    if row["status"] == "failed":
        st.error(row.get("error") or "Discovery failed.")
    if result is None or not result.pages:
        return

    locators = svc.repo.list_locators(project.id)
    overview, pages, locator_view = st.tabs(["Overview", "Pages", "Locators"])
    with overview:
        overview_tab(result, locators)
        if st.button("Continue to connections", type="primary", key="to_connections"):
            go_to("connections")
    with pages:
        pages_tab(result)
    with locator_view:
        locators_tab(locators)
