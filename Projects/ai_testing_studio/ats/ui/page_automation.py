"""Automation page: choose framework and browser, generate the test project, review/edit code, approve, download."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ats.generation.adapters.common import BROWSERS, FRAMEWORKS, browsers_for
from ats.services import Services
from ats.ui.session import notify, require_project, safe, show_notices
from ats.ui.widgets import ModelStream, chip, progress_logger

LANGUAGES = {".py": "python", ".ts": "typescript", ".js": "javascript", ".java": "java", ".json": "json", ".xml": "xml", ".md": "markdown", ".ini": "ini", ".txt": "text", ".toml": "toml", ".yml": "yaml", ".yaml": "yaml"}


def language_for(path: str) -> str:
    for suffix, language in LANGUAGES.items():
        if path.endswith(suffix):
            return language
    return "text"


def render(svc: Services) -> None:
    project = require_project(svc)
    st.header("Automation")
    show_notices()
    approved = [t for t in svc.repo.list_test_cases(project.id, status="approved") if t.automation_candidate]
    if not approved:
        st.info("Approve at least one automatable test case first.")
        return
    if not svc.repo.list_locators(project.id):
        st.info("Run website discovery first so that real locators exist.")
        return

    st.write(f"{len(approved)} approved test case(s) will be converted into runnable tests. Every element comes from the discovered locator repository, so nothing is guessed.")
    frameworks = list(FRAMEWORKS)
    a, b = st.columns(2)
    framework = a.selectbox("Framework", frameworks, index=frameworks.index(project.framework) if project.framework in frameworks else 0, format_func=lambda f: FRAMEWORKS[f]["label"])
    browsers = browsers_for(framework)
    browser = b.selectbox("Browser", browsers, index=browsers.index(project.browser) if project.browser in browsers else 0, format_func=BROWSERS.get)
    if framework == "selenium_java":
        st.caption("Java projects are built and run with Maven inside the runner image (Docker execution mode).")

    bundle = svc.repo.latest_bundle(project.id)
    if st.button("Generate automation project" if not bundle else "Regenerate (creates a new version)", type="primary"):
        with st.status("Generating the automation project...", expanded=True) as status:
            stream = ModelStream()
            bundle_id = safe(lambda: svc.scripts.generate(project, framework, browser, on_event=stream.callback, progress=progress_logger(status)))
            status.update(label="Generated" if bundle_id else "Generation failed", state="complete" if bundle_id else "error")
        if bundle_id:
            notify("Automation project generated. Review it, then approve it.")
            st.rerun()
    if not bundle:
        return

    bundle_id = bundle["id"]
    st.markdown(f"Version {bundle_id}: {chip(bundle['status'])} | {FRAMEWORKS.get(bundle['framework'], {}).get('label', bundle['framework'])} on {bundle['browser']}")
    trace = pd.DataFrame(bundle["traceability"])
    if not trace.empty:
        a, b, c = st.columns(3)
        a.metric("Automated test cases", int(trace["automated"].sum()))
        b.metric("Not automated", int((~trace["automated"]).sum()))
        c.metric("Files", len(svc.store.list_files(project.id, bundle_id)))
        with st.expander("Traceability: scenario -> test case -> script", expanded=False):
            st.dataframe(trace.rename(columns={"scenario_id": "Scenario", "test_case_id": "Test case", "module": "Module", "title": "Title", "file": "Script", "steps": "Steps", "automated": "Automated", "notes": "Notes"}), hide_index=True, width="stretch")
    for item in bundle["plan"].get("skipped", []):
        st.warning(f"{item['test_case_id']} was not automated: {item['reason']}")

    files = svc.store.list_files(project.id, bundle_id)
    left, right = st.columns([1, 3])
    path = left.radio("Files", files, key=f"file_{bundle_id}", label_visibility="visible")
    with right:
        content = safe(lambda: svc.store.read_file(project.id, bundle_id, path), "")
        edited = st.text_area("Content (edit, then save)", value=content, height=420, key=f"editor_{bundle_id}_{path}")
        a, b = st.columns(2)
        if a.button("Save edits", disabled=edited == content):
            if safe(lambda: svc.scripts.save_file(project.id, bundle_id, path, edited) or True):
                notify("File saved. The project needs approval again.")
                st.rerun()
        with b.popover("Edit with AI"):
            instruction = st.text_area("What should change in this file?", key=f"ai_edit_{bundle_id}")
            if st.button("Apply AI edit"):
                explanation = safe(lambda: svc.scripts.ai_edit_file(project.id, bundle_id, path, instruction))
                if explanation is not None:
                    notify(f"AI edit applied: {explanation}")
                    st.rerun()
        st.code(content, language=language_for(path), line_numbers=True, height=300)

    a, b, c = st.columns(3)
    if a.button("Approve for execution", type="primary", disabled=bundle["status"] in {"approved", "committed"}):
        svc.scripts.approve(project.id, bundle_id)
        st.rerun()
    b.download_button("Download project (ZIP)", svc.store.zip_bytes(project.id, bundle_id), file_name=f"{project.name}_automation_v{bundle_id}.zip", mime="application/zip")
    c.caption("Secrets and saved sessions are never included in the ZIP.")
