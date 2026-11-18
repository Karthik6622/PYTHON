"""Connections page: keys, tokens, client credentials, mail servers and test accounts the tests need. Values are stored encrypted."""

from __future__ import annotations

import streamlit as st

from ats.connections.service import KINDS, TEMPLATES
from ats.services import Services
from ats.ui import theme
from ats.ui.session import notify, owner_id, require_project, safe, show_notices


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
