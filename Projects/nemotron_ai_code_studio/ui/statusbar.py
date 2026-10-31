"""VS Code style status bar pinned to the bottom of the window."""

from __future__ import annotations

from html import escape

import streamlit as st

from studio.config import settings
from studio.models import get_model

from .dialogs import github_user
from .state import S, attempt, repo, repo_label


def _item(text: str, kind: str = "", title: str = "") -> str:
    dot = f"<span class='dot {kind}'></span>" if kind else ""
    return f"<span class='it' title='{escape(title, quote=True)}'>{dot}{text}</span>"


def render_status_bar() -> None:
    current = repo()
    left = ["<span class='it remote'>RK STUDIO</span>"]
    if current is not None:
        left.append(_item(escape(repo_label(current)), title="Repository"))
    if current is not None and current.git is not None:
        branch = current.git.current_branch()
        left.append(_item(f"&#9095; {escape(branch)}", title="Current branch"))
        ok, status = attempt(current.git.cached_status, current.workspace.version, quiet=True)
        if ok and status:
            if status.get("upstream"):
                left.append(_item(f"&uarr;{status['ahead']} &darr;{status['behind']}", title="Commits ahead / behind upstream"))
            changes = len(status.get("files", []))
            left.append(_item(f"{changes} change{'s' if changes != 1 else ''}", "warn" if changes else "ok", "Uncommitted changes"))
    lint = S.lint_result
    if lint is not None:
        count = len(lint["problems"])
        left.append(_item(f"{count} problem{'s' if count != 1 else ''}", "bad" if count else "ok"))

    right = [
        _item(escape(get_model(S.model).label), "ok" if settings.nvidia_api_key else "bad", "Selected model. " + ("NVIDIA API key is set" if settings.nvidia_api_key else "NVIDIA_API_KEY is missing")),
        _item(
            f"GitHub &middot; {escape(github_user())}" if settings.github_token and github_user() else "GitHub", "ok" if settings.github_token else "bad",
            "GitHub is connected" if settings.github_token else "GitHub is not connected: use the account button in the top bar",
        ),
        _item(f"<span class='mut'>mode</span> {escape(S.mode or 'ASK')}"),
    ]
    if S.active:
        right.append(_item(escape(S.active.rsplit(".", 1)[-1].upper() if "." in S.active else "TEXT")))
    right.append(_item("UTF-8"))

    with st.container(key="statusbar"):
        st.markdown(f"<div class='sbar'><div class='grp'>{''.join(left)}</div><div class='grp'>{''.join(right)}</div></div>", unsafe_allow_html=True)
