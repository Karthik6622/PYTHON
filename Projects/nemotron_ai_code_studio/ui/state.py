"""Session state, shared services and small helpers used by every panel."""

from __future__ import annotations

import re
import secrets
import time
from pathlib import Path
from typing import Any, Callable

import streamlit as st

from studio.chat import ChatMessage
from studio.deps import broker, coding_agent, conversations, nvidia, repository_agent, repositories
from studio.models import default_model_id
from studio.runner import AgentRun, CommandRun, friendly_error
from studio.services.repository_service import ActiveRepository, RepositoryError

__all__ = [
    "AgentRun", "CommandRun", "broker", "coding_agent", "conversations", "nvidia", "repository_agent", "repositories",
    "S", "init_state", "repo", "log", "attempt", "friendly_error", "open_file", "close_file", "reload_paths", "sync_after_change",
    "window_id", "open_workspace", "new_window_url",
]

_WINDOW_ID = re.compile(r"[A-Za-z0-9_-]{4,32}")


@st.cache_resource
def _load_prefs_once() -> bool:
    repositories.load_prefs()
    return True


def window_id() -> str:
    """Id of this browser window. It lives in the page address (?w=...), so a reload keeps it and a new window gets its own."""
    if "_window" not in st.session_state:
        wanted = str(st.query_params.get("w", ""))
        if not _WINDOW_ID.fullmatch(wanted):
            wanted = repositories.last_window() or secrets.token_urlsafe(6)
            st.query_params["w"] = wanted
        st.session_state["_window"] = wanted
    return st.session_state["_window"]


def _open_this_window() -> None:
    """Reopen what this window had open; a window with nothing yet starts in the scratch folder (no repository needed)."""
    if "_repo" in st.session_state:
        return
    wid = window_id()
    current = None
    try:
        current = repositories.recall(wid)
        if current is None:
            current = repositories.open_scratch()
            repositories.remember(wid, current.path, scratch=True)
    except RepositoryError as exc:
        st.error(exc.message)
    st.session_state["_repo"] = current


def open_workspace(current: ActiveRepository) -> None:
    """Make `current` the folder of this window and clear everything that belonged to the previous one."""
    for key, value in {
        "tabs": [], "active": None, "saved": {}, "drafts": {}, "notes": {}, "versions": {}, "cwd": "", "messages": [],
        "approvals": {}, "diff_view": None, "terminal": "", "term_cwd": "", "tests_result": None, "lint_result": None,
    }.items():
        st.session_state[key] = value
    conversations.clear(st.session_state["conversation_id"])
    st.session_state["_repo"] = current
    repositories.remember(window_id(), current.path, current.github, current.scratch)


def new_window_url(path: Path, github: dict[str, Any]) -> str:
    """Register `path` under a fresh window id and return the address that opens it in a new browser tab."""
    wid = secrets.token_urlsafe(6)
    repositories.remember(wid, path, github)
    try:
        base = str(st.context.url).split("?")[0]
    except Exception:  # older Streamlit without st.context.url
        base = ""
    return f"{base}?w={wid}"


def init_state() -> None:
    _load_prefs_once()
    wid = window_id()
    _open_this_window()
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
        "model": default_model_id(),
        "conversation_id": wid,
        "output_log": [],
        "terminal": "",
        "term_cwd": "",        # terminal working folder, relative to the repository root
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
    """The folder this browser window works in (a connected repository or the scratch folder)."""
    return st.session_state.get("_repo")


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
