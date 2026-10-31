"""VS Code style status bar pinned to the bottom of the window."""

from __future__ import annotations

from html import escape

import streamlit as st

from studio.config import settings
from studio.models import get_model
from studio.services.git_detect import GitInfo, connection_state

from .dialogs import github_status, github_user
from .state import S, attempt, location_label, repo


def _item(text: str, kind: str = "", title: str = "", style: str = "") -> str:
    dot = f"<span class='dot {kind}'></span>" if kind else ""
    extra = f" style='{style}'" if style else ""
    return f"<span class='it' title='{escape(title, quote=True)}'{extra}>{dot}{text}</span>"


def render_status_bar() -> None:
    current = repo()
    info = current.git_info if current is not None else GitInfo()
    state = connection_state(current is not None, info, github_status())  # A none, B folder, C repo, D repo + GitHub, E error

    left = ["<span class='it remote'>RK STUDIO</span>"]
    if current is not None and st.session_state.get("_link") is None:
        path = location_label(current)  # the real folder on this computer, as the backend reports it
        left.append(_item(escape(path), title=path, style="max-width:42vw;overflow:hidden;text-overflow:ellipsis"))
    if info.error:
        left.append(_item(escape(info.error[:90]), "bad", info.error))
    if current is not None and info.is_repo and current.git is not None:
        left.append(_item(escape(info.display_name or current.name), title=info.remote_slug or "Repository"))
        left.append(_item(f"&#9095; {escape(info.branch_label)}", title="Current branch"))
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
    ]
    if state == "D":
        who = github_user()
        right.append(_item("GitHub Connected", "ok", f"GitHub is connected{' as ' + who if who else ''}"))
    elif state == "C":
        right.append(_item("GitHub Not Connected", "idle", "Use the account button in the top bar to connect GitHub"))
    elif state == "E" and info.is_repo:
        reason = (st.session_state.get("_gh_error") or {}).get("message", "GitHub rejected the credentials.")
        right.append(_item("GitHub Authentication Failed", "bad", reason))
    right.append(_item(f"<span class='mut'>mode</span> {escape(S.mode or 'ASK')}"))
    if S.active:
        right.append(_item(escape(S.active.rsplit(".", 1)[-1].upper() if "." in S.active else "TEXT")))
    right.append(_item("UTF-8"))

    with st.container(key="statusbar"):
        st.markdown(f"<div class='sbar'><div class='grp'>{''.join(left)}</div><div class='grp'>{''.join(right)}</div></div>", unsafe_allow_html=True)
