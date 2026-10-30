"""Modal dialogs: connect a repository, and settings (API keys)."""

from __future__ import annotations

import asyncio

import streamlit as st

from studio.config import settings
from studio.models import available_models, get_model
from studio.services import folders
from studio.services.github_service import GitHubService

from .state import S, attempt, log, nvidia, repositories


def _reset_workspace_state() -> None:
    S.tabs, S.active, S.saved, S.drafts, S.notes, S.versions = [], None, {}, {}, {}, {}
    S.cwd, S.messages, S.approvals, S.diff_view = "", [], {}, None
    S.terminal, S.term_cwd = "", ""
    S.tests_result = S.lint_result = None


def _pick(path: str) -> None:
    st.session_state["clone_loc"] = path
    st.session_state["browse_dir"] = path


def _browse(path: str) -> None:
    st.session_state["browse_dir"] = path


def _folder_browser() -> None:
    """Server-side folder browser (a web app cannot open the visitor's own file dialog)."""
    start = st.session_state.get("browse_dir") or st.session_state.get("clone_loc") or str(folders.quick_places()[0][1])
    try:
        listing = folders.list_folders(start)
    except folders.FolderError as exc:
        st.error(str(exc))
        return
    here = listing["path"]
    st.caption(f"Browsing: {here or 'drives'}")
    top = st.columns([1, 1, 2])
    top[0].button("Up", icon=":material/arrow_upward:", key="br_up", disabled=listing["parent"] is None, on_click=_browse, args=(listing["parent"] or "",), width="stretch")
    top[1].button("Use this folder", icon=":material/check:", key="br_use", type="primary", disabled=not here, on_click=_pick, args=(here,), width="stretch")
    with st.container(height=180, key="br_list"):
        if not listing["folders"]:
            st.caption("No sub-folders here.")
        for index, item in enumerate(listing["folders"][:200]):
            st.button(item["name"], key=f"br:{index}", icon=":material/folder:", on_click=_browse, args=(item["path"],), width="stretch")
    if here:
        new_name, create = st.columns([3, 1], vertical_alignment="bottom")
        name = new_name.text_input("New folder", key="br_new", placeholder="New folder name", label_visibility="collapsed")
        if create.button("Create", key="br_make", disabled=not name.strip(), width="stretch", icon=":material/create_new_folder:"):
            try:
                created = folders.make_folder(here, name)
            except folders.FolderError as exc:
                st.error(str(exc))
            else:
                _browse(str(created))
                st.rerun(scope="fragment")


@st.dialog("Connect a repository", width="large")
def connect_dialog() -> None:
    if "clone_loc" not in st.session_state:
        st.session_state["clone_loc"] = str(settings.workspace_path) if repositories.location_chosen else ""
    st.markdown("**1. Where should it be saved?**")
    st.caption("A folder on the machine that runs RK Studio. The repository is cloned inside it, and the terminal opens in the cloned folder.")
    places = folders.quick_places()
    cols = st.columns(len(places))
    for col, (label, path) in zip(cols, places):
        col.button(label, key=f"qp:{label}", on_click=_pick, args=(path,), width="stretch")
    location = st.text_input("Clone location", key="clone_loc", placeholder="Full folder path, for example C:\\Users\\you\\projects", label_visibility="collapsed")
    with st.expander("Browse folders", icon=":material/folder_open:"):
        _folder_browser()

    st.markdown("**2. Which repository?**")
    name = st.text_input("Repository", placeholder="owner/repo or https://github.com/owner/repo", label_visibility="collapsed")
    branch = st.text_input("Branch (optional)", placeholder="default branch")
    if not settings.github_token:
        st.caption("No GitHub token is set. Public repositories work without one; private ones need a token in Settings.")
    if st.button("Clone and open", type="primary", disabled=len(name.strip()) < 3 or not location.strip(), icon=":material/cloud_download:"):
        ok, _ = attempt(repositories.choose_location, location)
        if ok:
            with st.spinner("Cloning and indexing the repository..."):
                ok, repo = attempt(repositories.connect_github, name.strip(), branch.strip() or None)
            if ok:
                _reset_workspace_state()
                log(f"Cloned {repo.name} to {repo.path}")
                st.toast(f"Cloned to {repo.path}", icon=":material/folder_open:")
                st.rerun()

    st.divider()
    st.markdown("**Or open a folder that is already there**")
    if st.button("Open the folder above as a workspace", disabled=not location.strip(), icon=":material/folder_open:", key="open_loc"):
        ok, repo = attempt(repositories.open_folder, location)
        if ok:
            _reset_workspace_state()
            log(f"Opened {repo.name} at {repo.path}")
            st.rerun()
    if repositories.location_chosen:
        workspaces = repositories.list_workspaces()
        st.caption(f"Folders inside {settings.workspace_path}")
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
