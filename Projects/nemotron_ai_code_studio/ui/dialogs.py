"""Modal dialogs: connect a repository, and settings (API keys)."""

from __future__ import annotations

import asyncio
import secrets
from pathlib import Path

import streamlit as st

from studio.config import settings
from studio.models import available_models, get_model
from studio.services import folders, local_sync
from studio.services.github_service import GitHubService

from .local_folder import available as browser_folders, picker_supported, render_clone_button
from .state import S, attempt, log, nvidia, open_workspace, repo, repositories, window_id, window_url


def ask_folder(initial: str, title: str) -> str | None:
    """Opens the operating system's folder window. None when it is cancelled or cannot be shown."""
    ok, chosen = attempt(folders.pick_folder_native, initial, title)
    if ok and not chosen:
        st.toast("No folder was selected.", icon=":material/info:")
    return chosen if ok else None


def ensure_folder() -> bool:
    """Before the first file is saved or command is run in a window with no folder, make the user choose one.

    On the user's own computer that is the operating system's folder window; on a hosted deployment it is the Open folder
    button of the Explorer. Returns False while there is no folder, so the caller must not create anything."""
    current = repo()
    if current is None:
        return True
    if browser_folders():
        if st.session_state.get("_link") is None and picker_supported():
            st.toast("Open a folder first: use Open folder in the Explorer.", icon=":material/folder_open:")
            return False
        return True
    if not current.scratch or st.session_state.get("_folder_chosen") or not folders.native_picker_available():
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


def _occupied() -> bool:
    """True when this window already has a folder or files of its own, so a cloned repository must not replace them."""
    current = repo()
    return bool(
        current is None or not current.scratch or st.session_state.get("_link") is not None
        or st.session_state.get("_folder_chosen") or S.tabs
    )


def _clone(name: str, branch: str, root: Path | None, target: str, link: str = "") -> None:
    """Clone, then open the repository in window `target`: this window when it is empty, otherwise a new browser tab.

    `link` is the folder on the user's computer (hosted deployments) that will receive the files."""
    with st.spinner("Cloning the repository..."):
        ok, result = attempt(repositories.clone_github, name.strip(), branch.strip() or None, root)
    if not ok:
        return
    path, github = result
    full = github.get("full_name", path.name)
    log(f"Cloned {full} to {path}")
    repositories.remember(target, path, github, False, link, bool(link))
    if target == window_id():
        ok, current = attempt(repositories.recall, target)
        if ok and current is not None:
            open_workspace(current, local_sync.LocalLink(link, fresh=True) if link else None)
            st.toast(f"Opened {full}.", icon=":material/check:")
            st.rerun()
        return
    st.session_state["cloned"] = {"path": str(path), "url": window_url(target), "name": full, "link": link}
    st.rerun(scope="fragment")


def _clone_hosted(job: dict, target: str) -> None:
    repository, branch = job.get("repo"), job.get("branch")
    if not isinstance(repository, str) or len(repository.strip()) < 3:
        st.warning("Enter the repository as owner/repo or paste its GitHub link.")
        return
    _clone(repository, branch if isinstance(branch, str) else "", settings.workspace_path / "local" / target, target, local_sync.clean_name(job.get("name")))


@st.dialog("Connect a repository", width="large")
def connect_dialog() -> None:
    done = st.session_state.get("cloned")
    if done:
        st.success(f"{done['name']} is ready.")
        if done.get("link"):
            st.caption(f"It is saved to {done['link']} on your computer and opens in its own window, so the files you have open here are not touched. If that window asks you to reconnect, click it once.")
        else:
            st.caption(f"Saved in {done['path']}. It opens in its own window, so the files you have open here are not touched.")
        st.link_button("Open in new window", done["url"], type="primary", icon=":material/open_in_new:")
        return

    if browser_folders():
        target = st.session_state.setdefault("_clone_wid", secrets.token_urlsafe(6) if _occupied() else window_id())
        job = st.session_state.pop("_clone_job", None)
        left, right = st.columns([3, 2])
        name = left.text_input("Repository", placeholder="owner/repo or https://github.com/owner/repo")
        branch = right.text_input("Branch (optional)", placeholder="default branch")
        if not settings.github_token:
            st.caption("No GitHub token is set. Public repositories work without one; private ones need a token in Settings.")
        st.caption(
            "Clone and open asks which folder on your computer should hold the repository. "
            + ("The folders and files you have open here are kept: it opens in a new window." if target != window_id() else "It opens in this window.")
        )
        render_clone_button(target, st.session_state.setdefault("_clone_open", secrets.token_urlsafe(4)))
        if not picker_supported():
            if st.button("Clone on the server only", icon=":material/cloud_download:"):
                job = {"repo": name, "branch": branch, "name": ""}
        if job:
            _clone_hosted(job, target)
        return

    with st.form("connect_form", border=False):
        left, right = st.columns([3, 2])
        name = left.text_input("Repository", placeholder="owner/repo or https://github.com/owner/repo")
        branch = right.text_input("Branch (optional)", placeholder="default branch")
        if not settings.github_token:
            st.caption("No GitHub token is set. Public repositories work without one; private ones need a token in Settings.")
        st.caption("Clone and open asks which folder should hold the repository. The terminal works in that same folder.")
        submitted = st.form_submit_button("Clone and open", type="primary", icon=":material/cloud_download:")

    if submitted:
        if len(name.strip()) < 3:
            st.warning("Enter the repository as owner/repo or paste its GitHub link.")
        else:
            last = str(settings.workspace_path) if repositories.location_chosen else ""
            chosen = ask_folder(last, "Choose the folder where the repository will be saved")
            if chosen:
                ok, root = attempt(repositories.choose_location, chosen)
                if ok:
                    _clone(name, branch, root, secrets.token_urlsafe(6) if _occupied() else window_id())


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
