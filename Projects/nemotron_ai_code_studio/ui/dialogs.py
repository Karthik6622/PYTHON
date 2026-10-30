"""Modal dialogs: connect a repository, and settings (API keys)."""

from __future__ import annotations

import asyncio

import streamlit as st

from studio.config import settings
from studio.models import available_models, get_model
from studio.services.github_service import GitHubService

from .state import S, attempt, log, nvidia, repositories


def _reset_workspace_state() -> None:
    S.tabs, S.active, S.saved, S.drafts, S.notes, S.versions = [], None, {}, {}, {}, {}
    S.cwd, S.messages, S.approvals, S.diff_view = "", [], {}, None
    S.terminal, S.term_cwd = "", ""
    S.tests_result = S.lint_result = None


@st.dialog("Connect a repository", width="large")
def connect_dialog() -> None:
    st.markdown("**GitHub repository**")
    name = st.text_input("Repository", placeholder="owner/repo or https://github.com/owner/repo", label_visibility="collapsed")
    branch = st.text_input("Branch (optional)", placeholder="default branch")
    if not settings.github_token:
        st.caption("No GitHub token is set. Public repositories work without one; private ones need a token in Settings.")
    st.caption(f"The repository is cloned into {settings.workspace_path}. The terminal opens in the cloned folder.")
    if st.button("Clone and open", type="primary", disabled=len(name.strip()) < 3, icon=":material/cloud_download:"):
        with st.spinner("Cloning and indexing the repository..."):
            ok, repo = attempt(repositories.connect_github, name.strip(), branch.strip() or None)
        if ok:
            _reset_workspace_state()
            log(f"Cloned {repo.name} to {repo.path}")
            st.toast(f"Cloned to {repo.path}", icon=":material/folder_open:")
            st.rerun()

    st.divider()
    st.markdown("**Existing workspaces**")
    st.caption(f"Folders inside {settings.workspace_path}")
    workspaces = repositories.list_workspaces()
    if not workspaces:
        st.info("No workspaces yet. Clone a repository above, or put a folder inside the workspace path.")
    for item in workspaces:
        label = f"{item['name']}  ({'git' if item['is_git'] else 'folder'})"
        if st.button(label, key=f"ws:{item['folder']}", width="stretch", icon=":material/folder_open:"):
            ok, repo = attempt(repositories.open_local, item["folder"])
            if ok:
                _reset_workspace_state()
                log(f"Opened {repo.name} at {repo.path}")
                st.rerun()


@st.dialog("Settings", width="large")
def settings_dialog() -> None:
    st.markdown(f"**NVIDIA API key** {'(configured)' if settings.nvidia_api_key else '(not set)'}")
    nvidia_key = st.text_input("NVIDIA API key", type="password", autocomplete="off", placeholder="nvapi-...", label_visibility="collapsed")
    models = available_models()
    st.markdown("**Models**")
    for model in models:
        st.caption(f"{model.label}: {model.note}  `{model.id}`")
    test_id = st.selectbox("Model to test", [m.id for m in models], index=[m.id for m in models].index(S.model) if S.model in [m.id for m in models] else 0, format_func=lambda i: get_model(i).label)
    st.markdown(f"**GitHub personal access token** {'(configured)' if settings.github_token else '(not set)'}")
    github_token = st.text_input("GitHub token", type="password", autocomplete="off", placeholder="ghp_... or github_pat_...", label_visibility="collapsed")

    if st.button("Save", type="primary", disabled=not (nvidia_key.strip() or github_token.strip()), icon=":material/save:"):
        settings.set_secrets(nvidia_api_key=nvidia_key.strip() or None, github_token=github_token.strip() or None)
        st.toast("Settings saved for this session.", icon=":material/check:")
        st.rerun()

    st.divider()
    left, right = st.columns(2)
    if left.button("Test NVIDIA connection", disabled=not settings.nvidia_api_key, width="stretch"):
        with st.spinner("Contacting NVIDIA..."):
            ok, result = attempt(lambda: asyncio.run(nvidia.ping(model=test_id)))
        if ok:
            (st.success if result.get("ok") else st.error)(result.get("message") or ("NVIDIA connection works." if result.get("ok") else "The check failed."))
    if right.button("Validate GitHub token", disabled=not settings.github_token, width="stretch"):
        with st.spinner("Contacting GitHub..."):
            ok, result = attempt(GitHubService().validate_token)
        if ok:
            st.success(f"GitHub token works (user {result.get('login', '?')}).")

    st.info(
        "Keys entered here are kept in this server's memory only and are lost when it restarts. "
        "To keep them, put them in the .env file. They are never shown again and never sent to the repository."
    )
