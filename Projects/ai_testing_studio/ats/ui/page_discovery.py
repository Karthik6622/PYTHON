"""Discovery page: run website analysis, inspect pages and the locator repository, manage authentication sessions."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from ats.config import get_settings
from ats.services import Services
from ats.ui.session import require_project, safe, show_notices
from ats.ui.widgets import chip, progress_logger


def run_discovery(svc: Services, project) -> None:
    with st.status("Discovering the website...", expanded=True) as status:
        result = safe(lambda: svc.discovery.run(project, on_progress=progress_logger(status)))
        if result:
            status.update(label=f"Discovery complete: {len(result.pages)} pages", state="complete")
        else:
            status.update(label="Discovery failed", state="error")


def authentication_panel(svc: Services, project) -> None:
    auth = project.auth
    with st.expander("Authentication sessions"):
        st.caption(f"Mode: **{auth.mode}**. Sessions are kept in the secure folder and never exported or committed.")
        if auth.mode in {"manual_capture", "storage_state"}:
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
        else:
            st.write("Change the authentication mode in the project settings to use saved sessions.")


def render(svc: Services) -> None:
    project = require_project(svc)
    st.header("Website discovery")
    show_notices()
    st.write(f"Target: **{project.url}**. A real browser opens the site, follows same-site links within your limits and records visible elements, forms, navigation and screenshots.")
    if not get_settings().model.configured:
        st.warning("The AI model is not configured (MODEL_API_KEY). Discovery still works; the AI summary and locator notes are skipped.")
    authentication_panel(svc, project)

    latest = svc.repo.latest_discovery(project.id)
    if st.button("Run discovery" if not latest else "Run discovery again", type="primary"):
        run_discovery(svc, project)
        st.rerun()
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
    a, b, c, d = st.columns(4)
    a.metric("Pages", len(result.pages))
    b.metric("Elements", sum(len(p.elements) for p in result.pages))
    c.metric("Locators", len(locators))
    d.metric("Forms", sum(len(p.forms) for p in result.pages))
    for warning in result.warnings:
        st.warning(warning)
    if result.summary:
        st.subheader("Application understanding")
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

    st.subheader("Pages")
    pages = pd.DataFrame(
        [{"Key": p.page_key, "URL": p.final_url or p.url, "Title": p.title, "Depth": p.depth, "Elements": len(p.elements), "Forms": len(p.forms),
          "Needs sign-in": p.requires_auth, "Console errors": len(p.console_errors)} for p in result.pages]
    )  # fmt: skip
    st.dataframe(pages, hide_index=True, width="stretch")
    if result.skipped:
        with st.expander(f"Skipped URLs ({len(result.skipped)})"):
            st.dataframe(pd.DataFrame(result.skipped), hide_index=True, width="stretch")

    keys = [p.page_key for p in result.pages]
    chosen = st.selectbox("Inspect a page", keys)
    page = next(p for p in result.pages if p.page_key == chosen)
    left, right = st.columns([2, 3])
    with left:
        if page.screenshot and Path(page.screenshot).is_file():
            st.image(page.screenshot, caption=page.title or page.url)
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

    st.subheader("Locator repository")
    query = st.text_input("Filter locators", placeholder="login, button, email...")
    rows = [
        {"Element": s.element_key, "Page": s.page_key, "Role": s.role or s.tag, "Name": s.name, "Preferred": s.preferred.display(), "Alternatives": len(s.alternatives),
         "Stability": round(s.stability, 2), "Intent": s.intent}
        for s in locators if not query or query.lower() in f"{s.element_key} {s.name} {s.intent}".lower()
    ]  # fmt: skip
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", height=380)
    st.caption("Stability is a heuristic: test ids and unique accessible names score highest; positional CSS and XPath score lowest.")
