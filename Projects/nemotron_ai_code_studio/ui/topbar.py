"""Title bar: brand, repository and branch, plus GitHub and Settings. Service status lives in the status bar."""

from __future__ import annotations

from html import escape

import streamlit as st

from .dialogs import connect_dialog, settings_dialog
from .state import S, attempt, log, reload_paths, repo


def _checkout(name: str) -> None:
    current = repo()
    if current is None or current.git is None or name == current.git.current_branch():
        return
    ok, _ = attempt(current.git.checkout, name)
    if ok:
        current.reindex()
        S.diff_view = None
        reload_paths(list(S.tabs))
        log(f"Checked out {name}")
        st.toast(f"Switched to {name}", icon=":material/call_split:")


def render_top_bar() -> None:
    current = repo()
    with st.container(key="titlebar"):
        brand, repo_col, branch_col, github_col, settings_col = st.columns([2.6, 3, 1.8, 0.45, 0.45], vertical_alignment="center", gap="small")
        brand.markdown("<div class='brand'><span class='logo'>RK</span><span class='word'>RK<b>STUDIO</b></span></div>", unsafe_allow_html=True)
        label = (escape(current.name) + (" &middot; local folder" if current.scratch else "")) if current else "No folder"
        repo_col.markdown(
            f"<div class='pill{'' if current else ' off'}' title='{escape(str(current.path), quote=True) if current else ''}'><i></i>{label}</div>",
            unsafe_allow_html=True,
        )

        if current and current.git is not None:
            ok, branches = attempt(current.git.branches, quiet=True)
            names = (branches or {}).get("local") or []
            now = current.git.current_branch()
            options = list(dict.fromkeys([now, *names]))
            st.session_state["branch_select"] = now  # always show the real branch, even after a failed switch
            branch_col.selectbox("Branch", options, key="branch_select", label_visibility="collapsed", on_change=lambda: _checkout(st.session_state.branch_select))

        if github_col.button("", icon=":material/hub:", help="Connect a GitHub repository", key="open_connect"):
            st.session_state.pop("cloned", None)
            st.session_state.pop("_clone_wid", None)
            st.session_state.pop("_clone_open", None)
            st.session_state.pop("_clone_job", None)
            connect_dialog()
        if settings_col.button("", icon=":material/tune:", help="Settings", key="open_settings"):
            settings_dialog()
