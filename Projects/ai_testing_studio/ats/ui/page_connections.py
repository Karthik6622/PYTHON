"""Connections page: keys, tokens, client credentials, mail servers and test accounts the tests need. Values are stored encrypted."""

from __future__ import annotations

import streamlit as st

from ats.connections.service import KINDS, TEMPLATES
from ats.services import Services
from ats.ui import theme
from ats.ui.session import go_to, notify, owner_id, require_project, safe, show_notices


def _preselect(kind: str) -> None:
    """Button callback: the template selectbox of the form below starts on the template of this kind."""
    template = next((t for t in TEMPLATES if t["kind"] == kind), None)
    if template:
        st.session_state["conn_template"] = template["label"]


def _continue_button(svc: Services, project, discovery_id: int, missing: int) -> None:  # noqa: ANN001
    """Record that the connections were checked for this discovery, then open the scenarios."""
    if st.button("Continue to scenarios", type="primary", key="conn_continue"):
        svc.repo.audit(project.id, "user", "connections.confirmed", "connections", {"discovery_id": discovery_id, "missing": missing})
        if missing:
            notify(f"{missing} required connection(s) are still missing. Tests that use them will fail until they are saved.", "warning")
        go_to("scenarios")


def _sign_in_panel(svc: Services, project, connections: list) -> None:  # noqa: ANN001
    """Top of the page for web projects: what discovery found about sign-in, what is saved and what is still missing."""
    if "web" not in project.channels:
        return
    latest = svc.repo.latest_discovery(project.id)
    if not latest or latest[0]["status"] != "completed":
        with st.container(border=True):
            st.info("Run website discovery first. It also checks whether the application needs sign-in details.")
            if st.button("Go to Discovery", key="conn_to_discovery"):
                go_to("discovery")
        return
    row, result = latest
    auth = (result.analysis if result else {}).get("authentication")
    if not isinstance(auth, dict):
        with st.container(border=True):
            st.info("Run discovery again to check whether this application needs sign-in details.")
            if st.button("Run discovery again", key="conn_rerun_discovery"):
                go_to("discovery")
        _continue_button(svc, project, row["id"], 0)
        return
    saved = {connection.kind for connection in connections if connection.env_names}
    requirements = [item for item in auth.get("requirements") or [] if isinstance(item, dict)]
    missing = sum(1 for item in requirements if item.get("kind", "custom") not in saved)
    with st.container(border=True):
        if auth.get("requires_authentication"):
            st.warning(f"**This application needs sign-in details.** {auth.get('summary') or ''}")
            for index, item in enumerate(requirements):
                kind = item.get("kind", "custom")
                spec = KINDS.get(kind, KINDS["custom"])
                is_saved = kind in saved
                left, right = st.columns([5, 1])
                state = ":green[Saved]" if is_saved else ":orange[Missing]"
                left.markdown(
                    f"**{spec.label}** for {item.get('where') or 'the application'}: {state}  \n"
                    f"{item.get('evidence') or ''} (confidence: {item.get('confidence') or 'medium'})"
                )
                if not is_saved:
                    right.button("Set up", key=f"setup_{index}_{kind}", on_click=_preselect, args=(kind,))
        else:
            st.success("No sign-in details are needed for this application (based on discovery).")
    _continue_button(svc, project, row["id"], missing)


def _form(svc: Services, project, existing=None) -> None:  # noqa: ANN001
    """Create a connection, or edit one (blank secret fields keep the stored value)."""
    owner = owner_id()
    key = existing.name if existing else "new"
    labels = {t["label"]: t for t in TEMPLATES}
    kind, name = (existing.kind, existing.name) if existing else (None, "")
    if not existing:
        picked = st.selectbox("Start from a template", list(labels), key="conn_template")
        kind, name = labels[picked]["kind"], labels[picked]["name"]
    spec = KINDS[kind]
    st.caption(spec.description)
    with st.form(f"conn_{key}_{kind}", border=False):
        name_value = st.text_input("Connection name", value=name, disabled=bool(existing))
        values, envs, secrets = {}, {}, {}
        by_part = {p.part: p for p in existing.parts} if existing else {}
        for part in spec.parts:
            current = by_part.get(part.part)
            cols = st.columns([2, 1])
            hint = "Saved. Leave blank to keep it." if current and current.configured and part.secret else ""
            values[part.part] = cols[0].text_input(
                part.label, value="" if part.secret else (current.value if current else ""), type="password" if part.secret else "default",
                placeholder=hint, key=f"conn_{key}_{kind}_{part.part}",
            )
            envs[part.part] = cols[1].text_input("Variable name", value=current.env_name if current else part.env, key=f"conn_{key}_{kind}_{part.part}_env")
            secrets[part.part] = part.secret
        meta = {m.key: st.selectbox(m.label, list(m.options), index=list(m.options).index((existing.meta if existing else {}).get(m.key, m.default)) if m.options else 0, key=f"conn_{key}_{kind}_{m.key}") if m.options else st.text_input(m.label, value=(existing.meta if existing else {}).get(m.key, m.default), key=f"conn_{key}_{kind}_{m.key}") for m in spec.meta}
        if st.form_submit_button("Save connection", type="primary"):
            saved = safe(lambda: svc.connections.save(project.id, owner, name_value, kind, values=values, envs=envs, secrets=secrets, meta=meta))
            if saved:
                notify(f"Connection '{saved.name}' saved. Tests read it from: {', '.join(saved.env_names) or 'no variables yet'}.")
                st.rerun()


def render(svc: Services) -> None:
    project = require_project(svc)
    theme.page_header("Connections", "Keys, tokens, client credentials, mail servers and test accounts. Stored encrypted; tests read them as environment variables.", "SETUP // CONNECTIONS")
    show_notices()
    owner = owner_id()
    connections = safe(lambda: svc.connections.list_connections(project.id, owner), [])
    _sign_in_panel(svc, project, connections)
    if connections:
        st.subheader("Saved connections")
    for connection in connections:
        with st.expander(f"{connection.name} | {connection.label}"):
            for part in connection.parts:
                st.markdown(f"`{part.env_name}`: {part.shown or '(not set)'}")
            a, b, c = st.columns(3)
            if connection.kind in {"api_key", "bearer", "basic", "oauth2"} and a.button("Test connection", key=f"test_{connection.name}"):
                with st.spinner("Calling the API..."):
                    st.info(safe(lambda: svc.connections.test_api(project, owner, connection.name), "Could not test."))
            if connection.kind in {"smtp", "imap"} and a.button("Test mail server", key=f"mail_{connection.name}"):
                with st.spinner("Connecting..."):
                    st.info(safe(lambda: svc.connections.test_mail(project.id, owner, connection.name), "Could not test."))
            if b.button("Delete", key=f"del_{connection.name}"):
                safe(lambda: svc.connections.delete(project.id, owner, connection.name))
                st.rerun()
            _form(svc, project, connection)
    with st.container(border=True):
        st.subheader("Add a connection")
        _form(svc, project)
    st.caption("Secrets are encrypted before they are stored (set ATS_SECRET_KEY for a key you control) and never shown again, logged or committed.")
