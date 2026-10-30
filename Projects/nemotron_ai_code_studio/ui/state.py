"""Session state, shared services and small helpers used by every panel."""

from __future__ import annotations

import time
from typing import Any, Callable

import streamlit as st

from studio.chat import ChatMessage
from studio.deps import broker, coding_agent, conversations, nvidia, repository_agent, repositories
from studio.runner import AgentRun, CommandRun, friendly_error
from studio.services.repository_service import ActiveRepository

__all__ = [
    "AgentRun", "CommandRun", "broker", "coding_agent", "conversations", "nvidia", "repository_agent", "repositories",
    "S", "init_state", "repo", "log", "attempt", "friendly_error", "open_file", "close_file", "reload_paths", "sync_after_change",
]


@st.cache_resource
def _restore_once() -> bool:
    """Reopen the repository that was open last time the app ran (once per server process)."""
    if repositories.active is None:
        repositories.restore_last()
    return True


def init_state() -> None:
    _restore_once()
    defaults: dict[str, Any] = {
        "side": "Explorer",
        "cwd": "",
        "tabs": [],            # open file paths, in order
        "active": None,        # active tab path
        "saved": {},           # path -> content as last read from / written to disk
        "drafts": {},          # path -> content currently in the editor
        "versions": {},        # path -> counter, bumped to force the editor to reload from disk
        "notes": {},           # path -> read-only reason (binary / too large)
        "messages": [],        # chat transcript (list[ChatMessage])
        "approvals": {},       # pending approval requests by id
        "run": None,           # AgentRun in progress
        "cursor": 0,           # how many events of the current run were applied
        "mode": "ASK",
        "conversation_id": "main",
        "output_log": [],
        "terminal": "",
        "term_run": None,
        "job_run": None,
        "job_kind": "",
        "tests_result": None,
        "lint_result": None,
        "review": {},          # message id -> show diff
        "diff_view": None,     # path whose Git diff is shown in the editor area
        "goto": None,          # {"path", "line"} chosen from a search result
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


class _State:
    """Attribute access to st.session_state (S.tabs instead of st.session_state['tabs'])."""

    def __getattr__(self, name: str) -> Any:
        return st.session_state[name]

    def __setattr__(self, name: str, value: Any) -> None:
        st.session_state[name] = value


S = _State()


def repo() -> ActiveRepository | None:
    return repositories.active


def log(text: str) -> None:
    S.output_log = (S.output_log + [f"[{time.strftime('%H:%M:%S')}] {text}"])[-500:]


def attempt(action: Callable[..., Any], *args: Any, quiet: bool = False, **kwargs: Any) -> tuple[bool, Any]:
    """Runs a service call; failures become a toast (and a log line) instead of a stack trace."""
    try:
        return True, action(*args, **kwargs)
    except Exception as exc:  # services raise their own error types; all carry a user-facing message
        message = friendly_error(exc)
        log(f"Error: {message}")
        if not quiet:
            st.toast(message, icon=":material/error:")
        return False, None


# ------------------------------------------------------------------ open files
def open_file(path: str) -> None:
    current = repo()
    if current is None:
        return
    S.diff_view = None
    if path in S.tabs:
        S.active = path
        return
    ok, file = attempt(current.workspace.read_text, path)
    if not ok:
        return
    note = ""
    if file["binary"]:
        note = "Binary file: not shown."
    elif file["truncated"]:
        note = "File is too large: showing the first part, read-only."
    S.saved = {**S.saved, path: file["content"]}
    S.drafts = {**S.drafts, path: file["content"]}
    S.notes = {**S.notes, path: note}
    S.tabs = [*S.tabs, path]
    S.active = path


def close_file(path: str) -> None:
    if path not in S.tabs:
        return
    index = S.tabs.index(path)
    S.tabs = [p for p in S.tabs if p != path]
    for name in ("saved", "drafts", "notes"):
        setattr(S, name, {k: v for k, v in getattr(S, name).items() if k != path})
    if S.active == path:
        S.active = S.tabs[max(0, index - 1)] if S.tabs else None


def reload_paths(paths: list[str]) -> list[str]:
    """Re-reads open files that changed on disk. Returns paths with unsaved edits that were left alone."""
    current = repo()
    skipped: list[str] = []
    if current is None:
        return skipped
    for path in paths:
        if path not in S.tabs:
            continue
        if S.drafts.get(path) != S.saved.get(path):
            skipped.append(path)
            continue
        ok, file = attempt(current.workspace.read_text, path, quiet=True)
        if not ok:
            close_file(path)  # the file no longer exists
            continue
        S.saved = {**S.saved, path: file["content"]}
        S.drafts = {**S.drafts, path: file["content"]}
        S.versions = {**S.versions, path: S.versions.get(path, 0) + 1}
    return skipped


def sync_after_change(paths: list[str]) -> None:
    skipped = reload_paths(paths)
    if skipped:
        st.toast("Not reloaded because of unsaved edits: " + ", ".join(skipped), icon=":material/info:")
