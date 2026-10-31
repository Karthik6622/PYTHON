"""Modal dialogs: connect a repository, and settings (API keys)."""

from __future__ import annotations

import asyncio
import secrets
import time
from pathlib import Path

import streamlit as st

from studio.config import settings
from studio.models import available_models, get_model
from studio.security import redact
from studio.services import folders, github_auth, local_sync, secret_store
from studio.services.github_service import GitHubService

from .local_folder import available as browser_folders
from .state import S, attempt, friendly_error, log, nvidia, open_workspace, repo, repositories, window_id, window_url


def ask_folder(initial: str, title: str) -> str | None:
    """Opens the operating system's folder window. None when it is cancelled or cannot be shown."""
    ok, chosen = attempt(folders.pick_folder_native, initial, title)
    if ok and not chosen:
        st.toast("No folder was selected.", icon=":material/info:")
    return chosen if ok else None


def ensure_folder() -> bool:
    """Before the first file is saved or command is run in a window with no folder, make the user choose one.

    On a hosted deployment the folder lives on the server (a cloned repository or the window's own workspace), so nothing is
    asked. On the user's own computer a scratch folder is replaced by the one chosen in the operating system's folder window.
    Returns False while there is no folder, so the caller must not create anything."""
    current = repo()
    if current is None:
        return True
    if browser_folders():
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
    if current is None or current.scratch and not S.tabs and st.session_state.get("_link") is None:
        _switch_folder(str(current.path) if current else "")
        return
    # This window already has a folder (for example a connected GitHub repository): keep it and open the new one in its own window.
    chosen = ask_folder(str(current.path), "Choose the folder to open in a new window")
    if not chosen:
        return
    ok, folder = attempt(repositories.open_scratch, chosen)
    if not ok:
        return
    wid = secrets.token_urlsafe(6)
    repositories.remember(wid, folder.path, {}, folder.scratch)
    st.session_state["_new_window"] = {"name": folder.name, "path": str(folder.path), "url": window_url(wid)}


@st.dialog("Open in new window")
def new_window_dialog(info: dict) -> None:
    st.write(f"**{info.get('name', '')}** opens in its own window, so the folder and files open here are not touched.")
    st.caption(info.get("path", ""))
    st.link_button("Open in new window", info.get("url", "#"), type="primary", icon=":material/open_in_new:")


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

    target = st.session_state.setdefault("_clone_wid", secrets.token_urlsafe(6) if _occupied() else window_id())
    with st.form("connect_form", border=False):
        left, right = st.columns([3, 2])
        name = left.text_input("Repository", placeholder="owner/repo or https://github.com/owner/repo")
        branch = right.text_input("Branch (optional)", placeholder="default branch")
        if not settings.github_token:
            st.caption("GitHub is not connected. Public repositories work without it; for private ones use the Connect GitHub button in the top bar.")
        st.caption(
            "The repository is cloned for you and opens in the IDE. "
            + ("The folders and files you have open here are kept: it opens in a new window." if target != window_id() else "It opens in this window.")
        )
        submitted = st.form_submit_button("Clone and open", type="primary", icon=":material/cloud_download:")

    if submitted:
        if len(name.strip()) < 3:
            st.warning("Enter the repository as owner/repo or paste its GitHub link.")
        else:
            _clone(name, branch, settings.workspace_path / "local" / target, target)


def _store() -> dict[str, str]:
    return settings.session_store(window_id())


def github_user() -> str:
    """Login of the GitHub account connected in this window (empty when unknown)."""
    store = _store()  # first: it ties this thread to the window's own keys (fragments and callbacks run in threads of their own)
    return store.get("github_user", "") if settings.github_token else ""


def github_status() -> str:
    """'connected' only after GitHub accepted the token; 'failed' after it refused one; otherwise 'disconnected'."""
    user = github_user()
    if settings.github_token and user:
        return "connected"
    return "failed" if st.session_state.get("_gh_error") else "disconnected"


def _remember_failure(exc: Exception, token: str) -> None:
    detail = redact(f"{type(exc).__name__}: {exc}")
    st.session_state["_gh_error"] = {"message": friendly_error(exc), "detail": detail.replace(token, "[token]") if token else detail}
    log(f"GitHub sign-in failed: {friendly_error(exc)}")


def _connect_token(token: str) -> bool:
    """Check a token with GitHub through the backend. Only a token GitHub accepts is kept (in memory, and in the operating
    system's credential store on the user's own computer); a refused one is dropped and the reason is remembered for the UI."""
    try:
        info = GitHubService(token).validate_token()
    except Exception as exc:  # network errors, a revoked or expired token, missing scopes
        _remember_failure(exc, token)
        return False
    store = _store()
    settings.set_secrets(github_token=token, store=store)
    store["github_user"] = str(info.get("login") or "")
    st.session_state.pop("_gh_error", None)
    secret_store.save(token)
    log(f"GitHub connected as {store['github_user'] or 'unknown user'}")
    return True


def disconnect_github() -> None:
    settings.clear_github()
    secret_store.delete()
    st.session_state.pop("_gh_error", None)
    log("GitHub disconnected")


def sync_github() -> None:
    """Once per opened folder: for a Git repository, bring back the saved token, ask GitHub whether it still works, and decide
    whether to offer the connect window. A folder that is not a repository gets none of this."""
    current = repo()
    ident = str(current.path) if current is not None else ""
    if st.session_state.get("_gh_synced") == ident:
        return
    st.session_state["_gh_synced"] = ident
    st.session_state.pop("_gh_error", None)
    if current is None or current.git is None:
        return
    store = _store()
    if not settings.github_token:
        saved = secret_store.load()
        if saved:
            settings.set_secrets(github_token=saved, store=store)
    if settings.github_token and not store.get("github_user"):
        token = settings.github_token
        with st.spinner("Checking GitHub..."):
            try:
                store["github_user"] = str(GitHubService(token).validate_token().get("login") or "")
            except Exception as exc:  # expired, revoked or offline: the repository stays usable, the indicator says why
                _remember_failure(exc, token)
                if getattr(exc, "status", 0) in {401, 403}:
                    store.pop("github_token", None)  # GitHub refused it; the saved copy is tried again the next time a folder is opened
                else:
                    return  # a timeout or no network says nothing about the token: keep it, and do not ask the user to reconnect
    if github_status() != "connected":
        st.session_state["_ask_github"] = True


def _cancel_signin() -> None:
    st.session_state.pop("_gh_device", None)


def _device_signin(client_id: str) -> None:
    """Sign in with GitHub: the visitor gets a code, approves it on github.com, and this window receives its own token."""
    flow = st.session_state.get("_gh_device")
    if flow is None:
        if st.button("Sign in with GitHub", type="primary", icon=":material/login:", width="stretch", key="gh_signin"):
            ok, started = attempt(github_auth.start, client_id)
            if ok:
                st.session_state["_gh_device"] = {**started, "deadline": time.time() + started["expires_in"]}
                st.rerun(scope="fragment")
        return

    uri = flow["verification_uri"]
    st.markdown(f"Open GitHub, type this code and approve:\n\n## `{flow['user_code']}`")
    left, right = st.columns(2)
    left.link_button("Open GitHub", uri, icon=":material/open_in_new:", type="primary", width="stretch")
    right.button("Cancel", on_click=_cancel_signin, width="stretch", key="gh_cancel")
    interval = flow["interval"]
    until = min(flow["deadline"], time.time() + 90)  # wait in slices, so a closed dialog does not hold the app for long
    with st.spinner("Waiting for you to approve on GitHub..."):
        while time.time() < until:
            time.sleep(interval)
            ok, result = attempt(github_auth.poll, client_id, flow["device_code"], quiet=True)
            if not ok:
                st.session_state.pop("_gh_device", None)
                st.error("GitHub sign-in failed. Start again.")
                return
            status = result["status"]
            if status == "slow_down":
                interval = flow["interval"] = max(interval, int(result.get("interval") or interval))
            elif status == "ok":
                st.session_state.pop("_gh_device", None)
                if _connect_token(result["token"]):
                    st.toast("GitHub connected.", icon=":material/check:")
                    st.rerun()
                return
            elif status in {"expired", "denied"}:
                st.session_state.pop("_gh_device", None)
                st.warning("The code expired." if status == "expired" else "The sign-in was denied on GitHub.")
                st.rerun(scope="fragment")
    if time.time() >= flow["deadline"]:
        st.session_state.pop("_gh_device", None)
        st.rerun(scope="fragment")
    st.button("Check again", key="gh_again")


@st.dialog("Connect GitHub", width="medium")
def github_dialog() -> None:
    store = _store()
    if github_status() == "connected":
        user = github_user()
        st.success(f"GitHub Connected{' as ' + user if user else ''}.")
        where = {
            "keyring": "in your operating system's credential manager",
            "dpapi": "encrypted for your Windows account",
        }.get(secret_store.backend())
        st.caption(
            "You can clone private repositories, pull, push, and use git push in the terminal. "
            + (f"The token is stored {where}; it is never shown again and never written to the repository." if where else
               "The token is kept in the server's memory only and is never written to disk.")
        )
        left, right = st.columns(2)
        if store.get("github_token"):
            if left.button("Disconnect", icon=":material/link_off:", width="stretch"):
                disconnect_github()
                st.rerun()
        else:
            st.caption("This token comes from the server's own environment.")
        if right.button("Close", width="stretch", key="gh_close"):
            st.rerun()
        return

    failure = st.session_state.get("_gh_error")
    if failure:
        st.error(f"GitHub could not be connected. {failure['message']}")
        with st.expander("Technical details"):
            st.code(failure["detail"], language=None)
    else:
        st.markdown("Connect your GitHub account to use **your own** repositories (including private ones) and to push your commits.")
        st.caption("Optional: the editor, the terminal and local Git commands work without it.")
    client_id = settings.github_client_id
    if client_id:
        _device_signin(client_id)
        st.markdown("<div style='text-align:center;opacity:.6;margin:.4rem 0'>or use a personal access token</div>", unsafe_allow_html=True)
    with st.form("gh_token_form", border=False):
        value = st.text_input("Personal access token", type="password", autocomplete="off", placeholder="ghp_... or github_pat_...")
        connect, cancel = st.columns(2)
        go = connect.form_submit_button("Connect", type="primary", icon=":material/key:", width="stretch")
        dismissed = cancel.form_submit_button("Cancel", width="stretch")
    st.link_button(
        "Create a token on GitHub", "https://github.com/settings/tokens/new?scopes=repo&description=RK%20Studio",
        icon=":material/open_in_new:", help="Opens GitHub with the repo permission already selected",
    )
    if dismissed:
        st.rerun()
    if go:
        if len(value.strip()) < 8:
            st.warning("Paste the token you created on GitHub.")
        elif _connect_token(value.strip()):
            st.toast("GitHub connected.", icon=":material/check:")
            st.rerun()
        else:
            st.rerun(scope="fragment")  # redraw the dialog with the reason


def prompt_github_if_needed() -> None:
    """Open the Connect GitHub window for a detected Git repository that is not connected yet (when the folder is opened, or when a
    fetch, pull or push needs the account). A folder that is not a Git repository never opens it."""
    current = repo()
    if not st.session_state.pop("_ask_github", False) or github_status() == "connected":
        return
    if current is None or current.git is None:
        return
    github_dialog()


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
    st.caption("The Connect GitHub button in the top bar signs in without pasting a token. You can also paste one here.")
    github_token = st.text_input("GitHub token", type="password", autocomplete="off", placeholder="ghp_... or github_pat_...", label_visibility="collapsed")

    if st.button("Save", type="primary", disabled=not (nvidia_key.strip() or github_token.strip()), icon=":material/save:"):
        settings.set_secrets(nvidia_api_key=nvidia_key.strip() or None)
        if github_token.strip() and not _connect_token(github_token.strip()):
            st.error("GitHub did not accept that token. See Connect GitHub for the details.")  # nothing is kept for a refused token
        else:
            st.toast("Settings saved.", icon=":material/check:")
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
