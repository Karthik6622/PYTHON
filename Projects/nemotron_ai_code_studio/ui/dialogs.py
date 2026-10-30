"""Modal dialogs: connect a repository, and settings (API keys)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import streamlit as st

from studio.config import settings
from studio.models import available_models, get_model
from studio.services import folders
from studio.services.github_service import GitHubService

from .state import S, attempt, log, new_window_url, nvidia, open_workspace, repo, repositories


def ask_folder(initial: str, title: str) -> str | None:
    """Opens the operating system's folder window. None when it is cancelled or cannot be shown."""
    ok, chosen = attempt(folders.pick_folder_native, initial, title)
    if ok and not chosen:
        st.toast("No folder was selected.", icon=":material/info:")
    return chosen if ok else None


def ensure_folder() -> bool:
    """Before the first file is saved in a window with no repository, ask where to save it (the OS folder window).

    Returns False when the user cancels, so the caller must not create anything. Once a folder is chosen it is not asked again."""
    current = repo()
    if current is None or not current.scratch or st.session_state.get("_folder_chosen") or not folders.native_picker_available():
        return True
    return _switch_folder(str(current.path))


def _switch_folder(initial: str) -> bool:
    chosen = ask_folder(initial, "Choose the folder where your files will be saved")
    if not chosen:
        return False
    ok, folder = attempt(repositories.open_scratch, chosen)
    if not ok:
        return False
    open_workspace(folder)
    st.session_state["_folder_chosen"] = True
    log(f"Working in {folder.path}")
    return True


def choose_working_folder() -> None:
    current = repo()
    _switch_folder(str(current.path) if current else "")


def _clone(name: str, branch: str, root: Path | None) -> None:
    with st.spinner("Cloning the repository..."):
        ok, result = attempt(repositories.clone_github, name.strip(), branch.strip() or None, root)
    if not ok:
        return
    path, github = result
    log(f"Cloned {github.get('full_name', name)} to {path}")
    st.session_state["cloned"] = {"path": str(path), "url": new_window_url(path, github), "name": github.get("full_name", path.name)}
    st.rerun(scope="fragment")


@st.dialog("Connect a repository", width="large")
def connect_dialog() -> None:
    done = st.session_state.get("cloned")
    if done:
        st.success(f"{done['name']} is ready.")
        st.caption(f"Saved in {done['path']}. It opens in its own window, so the files you have open here are not touched.")
        st.link_button("Open in new window", done["url"], type="primary", icon=":material/open_in_new:")
        return

    native = folders.native_picker_available()
    with st.form("connect_form", border=False):
        left, right = st.columns([3, 2])
        name = left.text_input("Repository", placeholder="owner/repo or https://github.com/owner/repo")
        branch = right.text_input("Branch (optional)", placeholder="default branch")
        if not settings.github_token:
            st.caption("No GitHub token is set. Public repositories work without one; private ones need a token in Settings.")
        if native:
            st.caption("Clone and open asks where to save the repository. The terminal for that repository works in the same folder.")
        else:
            st.caption("The repository is cloned on the server and opens in its own window. There, use Save to folder (top bar) to keep a copy in a folder on your computer, saved as you work.")
        submitted = st.form_submit_button("Clone and open", type="primary", icon=":material/cloud_download:")

    if submitted:
        if len(name.strip()) < 3:
            st.warning("Enter the repository as owner/repo or paste its GitHub link.")
        elif not native:
            _clone(name, branch, None)
        else:
            last = str(settings.workspace_path) if repositories.location_chosen else ""
            chosen = ask_folder(last, "Choose the folder where the repository will be saved")
            if chosen:
                ok, root = attempt(repositories.choose_location, chosen)
                if ok:
                    _clone(name, branch, root)


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
