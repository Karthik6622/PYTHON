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


def _opened(repo, verb: str) -> None:
    _reset_workspace_state()
    log(f"{verb} {repo.name} at {repo.path}")
    st.toast(f"{verb} {repo.path}", icon=":material/folder_open:")
    st.rerun()


def _clone(name: str, branch: str, location: str) -> None:
    ok, _ = attempt(repositories.choose_location, location)
    if not ok:
        return
    with st.spinner("Cloning and indexing the repository..."):
        ok, repo = attempt(repositories.connect_github, name.strip(), branch.strip() or None)
    if ok:
        _opened(repo, "Cloned to")


def _ask_folder(initial: str, title: str) -> str | None:
    """Opens the operating system's folder window. None when it is cancelled or cannot be shown."""
    ok, chosen = attempt(folders.pick_folder_native, initial, title)
    if ok and not chosen:
        st.info("No folder was selected.")
    return chosen if ok else None


@st.dialog("Connect a repository", width="large")
def connect_dialog() -> None:
    native = folders.native_picker_available()
    left, right = st.columns([3, 2])
    name = left.text_input("Repository", placeholder="owner/repo or https://github.com/owner/repo")
    branch = right.text_input("Branch (optional)", placeholder="default branch")
    if not settings.github_token:
        st.caption("No GitHub token is set. Public repositories work without one; private ones need a token in Settings.")
    ready = len(name.strip()) >= 3
    last = str(settings.workspace_path) if repositories.location_chosen else ""

    if native:
        st.caption("A folder window opens so you can choose where the repository is saved. The terminal then opens in that folder.")
        if st.button("Choose folder and clone", type="primary", disabled=not ready, icon=":material/folder_open:", key="clone_native"):
            chosen = _ask_folder(last, "Choose the folder where the repository will be saved")
            if chosen:
                _clone(name, branch, chosen)
        st.divider()
        if st.button("Open a folder that is already on this computer", icon=":material/folder_open:", key="open_native"):
            chosen = _ask_folder(last, "Choose a folder to open")
            if chosen:
                ok, repo = attempt(repositories.open_folder, chosen)
                if ok:
                    _opened(repo, "Opened")
        return

    # Hosted deployment: the app runs on a server and cannot open a window on your computer, so pick a folder on the server.
    if "clone_loc" not in st.session_state:
        st.session_state["clone_loc"] = last
    st.markdown("**Save to**")
    st.caption("RK Studio is running on a server, so this is a folder on that server (your own computer's folders cannot be reached from here).")
    path_col, browse_col = st.columns([5, 1], vertical_alignment="bottom")
    location = path_col.text_input("Save to", key="clone_loc", placeholder="Full folder path, or use Browse", label_visibility="collapsed")
    show = browse_col.toggle("Browse", key="show_browser", value=not last)
    if show:
        with st.container(border=True, key="browser_box"):
            cols = st.columns(len(folders.quick_places()))
            for col, (label, path) in zip(cols, folders.quick_places()):
                col.button(label, key=f"qp:{label}", on_click=_pick, args=(path,), width="stretch")
            _folder_browser()
    if st.button("Clone and open", type="primary", disabled=not (ready and location.strip()), icon=":material/cloud_download:", key="clone_server"):
        _clone(name, branch, location)

    st.divider()
    if st.button("Open the folder above as a workspace", disabled=not location.strip(), icon=":material/folder_open:", key="open_loc"):
        ok, repo = attempt(repositories.open_folder, location)
        if ok:
            _opened(repo, "Opened")
    if repositories.location_chosen:
        for item in repositories.list_workspaces():
            label = f"{item['name']}  ({'git' if item['is_git'] else 'folder'})"
            if st.button(label, key=f"ws:{item['folder']}", width="stretch", icon=":material/folder_open:"):
                ok, repo = attempt(repositories.open_local, item["folder"])
                if ok:
                    _opened(repo, "Opened")


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
