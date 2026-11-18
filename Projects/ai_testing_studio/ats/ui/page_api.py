"""API page: import an API definition (OpenAPI / Swagger / Postman / observed calls / manual), review the endpoints, set the base URL."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ats.services import Services
from ats.ui import jobs_ui, theme
from ats.ui.session import go_to, notify, owner_id, require_project, safe, show_notices


def _import_report(result: dict) -> str:
    text = f"Imported {result.get('count', result.get('endpoints', 0))} endpoint(s)."
    if result.get("warnings"):
        text += " " + " ".join(result["warnings"][:3])
    return text


def render(svc: Services) -> None:
    project = require_project(svc)
    theme.page_header("API", "Import the API definition. Scenarios and test cases for the API are designed from these endpoints.", "STEP 01 // API")
    show_notices()
    if jobs_ui.running_panel(svc, project, ("api_import",), "Importing the API definition"):
        return
    jobs_ui.last_problem(svc, project, ("api_import",))

    with st.container(border=True):
        base = st.text_input("API base URL", value=project.api_base_url, placeholder="https://api.example.com/v1", help="Requests are sent here. Empty = the application's own address.")
        if base.strip() != project.api_base_url and st.button("Save base URL"):
            if safe(lambda: svc.api.set_base_url(project, base) is not None):
                notify("API base URL saved.")
                st.rerun()
        st.caption("Keys, tokens, client id/secret and mail server details are entered on the **Connections** page; tests read them from the environment.")

    url_tab, file_tab, postman_tab, observed_tab, manual_tab = st.tabs(["OpenAPI / Swagger URL", "Upload file", "Postman collection", "Observed calls", "Manual endpoint"])
    with url_tab:
        url = st.text_input("Definition URL", placeholder="https://api.example.com/openapi.json", key="api_url")
        replace = st.checkbox("Replace the endpoints already imported", value=True, key="api_replace_url")
        if st.button("Import from URL", type="primary"):
            if not url.strip():
                st.warning("Enter the address of the API definition first.")
            else:
                jobs_ui.start_job(
                    svc, project, "api_import", "Importing the API definition",
                    lambda ctx: svc.api.import_url(project, url.strip(), replace=replace, progress=ctx.reporter), notice="API definition imported. Generate the scenarios next.",
                )
    with file_tab:
        upload = st.file_uploader("OpenAPI 3.x / Swagger 2.0 (JSON or YAML)", type=["json", "yaml", "yml"], key="api_file")
        replace_file = st.checkbox("Replace the endpoints already imported", value=True, key="api_replace_file")
        if st.button("Import file", disabled=upload is None):
            result = safe(lambda: svc.api.import_document(project, upload.getvalue().decode("utf-8", errors="replace"), replace=replace_file))
            if result:
                notify(_import_report(result))
                st.rerun()
    with postman_tab:
        collection = st.file_uploader("Postman collection v2.1 (JSON)", type=["json"], key="api_postman")
        if st.button("Import collection", disabled=collection is None):
            result = safe(lambda: svc.api.import_document(project, collection.getvalue().decode("utf-8", errors="replace")))
            if result:
                notify(_import_report(result))
                st.rerun()
    with observed_tab:
        seen = safe(lambda: svc.api.observed_preview(project), 0)
        st.caption(f"{seen} API call(s) were seen as fetch/XHR while Web discovery explored the application." if seen else "Run Web discovery first; calls the application makes are listed here.")
        external = st.checkbox("Include calls to other hosts", value=False)
        if st.button("Import observed calls", disabled=not seen):
            result = safe(lambda: svc.api.import_observed(project, include_external=external))
            if result:
                notify(_import_report(result))
                st.rerun()
    with manual_tab:
        with st.form("api_manual"):
            a, b = st.columns([1, 3])
            method = a.selectbox("Method", ["GET", "POST", "PUT", "PATCH", "DELETE"])
            path = b.text_input("Path", placeholder="/users/{id}")
            summary = st.text_input("Summary")
            c, d = st.columns(2)
            query = c.text_input("Query parameters", placeholder="page, limit")
            tags = d.text_input("Tag", placeholder="users")
            body = st.text_area("Sample JSON body (optional)", height=90)
            if st.form_submit_button("Add endpoint") and path.strip():
                if safe(lambda: svc.api.add_manual(project, method=method, path=path.strip(), summary=summary, tags=tags, query=query, body=body)):
                    notify("Endpoint added.")
                    st.rerun()

    groups = svc.api.grouped(project.id)
    if not groups:
        st.info("No endpoints yet. Import a definition above.")
        return
    total = sum(len(items) for items in groups.values())
    a, b = st.columns(2)
    a.metric("Endpoints", total)
    b.metric("Groups", len(groups))
    rows = [{"Group": tag or "(untagged)", "Method": e.method, "Path": e.path, "Summary": e.summary, "Auth": ", ".join(s.scheme for s in e.security), "Source": e.source} for tag, items in groups.items() for e in items]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    left, right = st.columns(2)
    if left.button("Delete all endpoints"):
        svc.api.delete(project.id)
        st.rerun()
    if right.button("Continue to scenarios", type="primary"):
        go_to("scenarios")
