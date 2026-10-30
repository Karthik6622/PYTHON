"""Top bar: repository, branch, connection and model status, Settings, GitHub."""

from __future__ import annotations

import streamlit as st

from studio.config import settings

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


def _chip(ok: bool, text: str) -> str:
    colour = "#76b900" if ok else "#f14c4c"
    return f"<span style='color:{colour}'>&#9679;</span>&nbsp;{text}"


def render_top_bar() -> None:
    current = repo()
    with st.container(border=True):
        title, repo_col, branch_col, status_col, buttons = st.columns([2.2, 2.2, 1.6, 3.4, 1.8], vertical_alignment="center")
        title.markdown("**Nemotron AI Code Studio**")
        repo_col.markdown(f"**Repository:** {current.name if current else 'none'}")

        if current and current.git is not None:
            ok, branches = attempt(current.git.branches, quiet=True)
            names = (branches or {}).get("local") or []
            now = current.git.current_branch()
            options = list(dict.fromkeys([now, *names]))
            st.session_state["branch_select"] = now  # always show the real branch, even after a failed switch
            branch_col.selectbox("Branch", options, key="branch_select", label_visibility="collapsed", on_change=lambda: _checkout(st.session_state.branch_select))
        else:
            branch_col.caption("no branch")

        status_col.markdown(
            "&nbsp;&nbsp;".join([
                _chip(True, "Backend ready"),
                _chip(bool(settings.nvidia_api_key), "Nemotron ready" if settings.nvidia_api_key else "Nemotron: no API key"),
                _chip(bool(settings.github_token), "GitHub token set" if settings.github_token else "GitHub: no token"),
            ]),
            unsafe_allow_html=True,
        )

        github_col, settings_col = buttons.columns(2)
        if github_col.button("GitHub", icon=":material/hub:", width="stretch"):
            connect_dialog()
        if settings_col.button("Settings", icon=":material/settings:", width="stretch"):
            settings_dialog()
