"""Session state, shared services and small helpers used by every panel."""

from __future__ import annotations

import re
import secrets
import time
from pathlib import Path
from typing import Any, Callable

import streamlit as st

from studio import chat_store
from studio.chat import ChangeSet, ChatMessage
from studio.config import is_hosted, settings
from studio.deps import broker, coding_agent, conversations, nvidia, repository_agent, repositories
from studio.models import default_model_id, get_model
from studio.runner import AgentRun, CommandRun, active_run, friendly_error
from studio.services import local_sync
from studio.services.repository_service import ActiveRepository, RepositoryError

__all__ = [
    "AgentRun", "CommandRun", "broker", "coding_agent", "conversations", "nvidia", "repository_agent", "repositories",
    "S", "init_state", "repo", "log", "attempt", "friendly_error", "open_file", "close_file", "reload_paths", "sync_after_change",
    "window_id", "open_workspace", "new_window_url", "window_url", "location_label", "repo_label",
]

_WINDOW_ID = re.compile(r"[A-Za-z0-9_-]{4,32}")


@st.cache_resource
def _load_prefs_once() -> bool:
    repositories.load_prefs()
    return True


def _bind_secrets() -> None:
    """Tie this thread to the keys of this window's visitor (Streamlit runs fragments and callbacks in threads of their own)."""
    wid = st.session_state.get("_window")
    if wid:
        settings.bind_session(settings.session_store(wid))


def window_id() -> str:
    """Id of this browser window. It lives in the page address (?w=...), so a reload keeps it and a new window gets its own.

    A visitor without one always gets a new id on a shared deployment; only on the user's own computer is the last window reopened."""
    if "_window" not in st.session_state:
        wanted = str(st.query_params.get("w", ""))
        if not _WINDOW_ID.fullmatch(wanted):
            wanted = (None if is_hosted() else repositories.last_window()) or secrets.token_urlsafe(6)
            st.query_params["w"] = wanted
        st.session_state["_window"] = wanted
    _bind_secrets()
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
            current = repositories.open_scratch(window=wid)
            repositories.remember(wid, current.path, scratch=True)
        repositories.adopt_tracker(wid, current)
    except RepositoryError as exc:
        st.error(exc.message)
    st.session_state["_repo"] = current
    if current is not None:
        name, fresh = repositories.window_link(wid)
        if name:  # this window mirrors a folder on the user's computer: keep mirroring it after a reload
            known = {} if fresh else local_sync.snapshot(current.path)
            sidecar = local_sync.load_sidecar(current.path)
            st.session_state["_link"] = local_sync.LocalLink(
                name, known=known, fresh=fresh,
                location=local_sync.clean_location(sidecar.get("location")),
                listed=local_sync.clean_listing(sidecar.get("listed")),
            )


def open_workspace(current: ActiveRepository, link: local_sync.LocalLink | None = None) -> None:
    """Make `current` the folder of this window and clear everything that belonged to the previous one.

    `link` is the folder on the user's computer that mirrors it (hosted deployments)."""
    for key, value in {
        "tabs": [], "active": None, "saved": {}, "drafts": {}, "notes": {}, "versions": {}, "cwd": "", "messages": [],
        "approvals": {}, "diff_view": None, "terminal": "", "term_cwd": "", "tests_result": None, "lint_result": None,
    }.items():
        st.session_state[key] = value
    conversations.clear(st.session_state["conversation_id"])
    repositories.adopt_tracker(window_id(), current)
    st.session_state["_repo"] = current
    if link is not None:
        st.session_state["_link"] = link
    else:
        st.session_state.pop("_link", None)
    repositories.remember(
        window_id(), current.path, current.github, current.scratch, link.name if link else "", bool(link and link.fresh),
    )


def location_label(current: ActiveRepository | None) -> str:
    """The absolute path of the workspace the IDE and terminal are actually using."""
    if current is None:
        return ""
    return current.path.as_posix()


_REMOTE_NAME = re.compile(r"[:/]([\w.-]+)/([\w.-]+?)(?:\.git)?/?$")


def repo_label(current: ActiveRepository | None) -> str:
    """owner/repo of the repository when it is known (GitHub or the Git remote), otherwise the folder name."""
    if current is None:
        return ""
    full = (current.github or {}).get("full_name")
    if full:
        return str(full)
    if current.git is not None:
        try:
            url = current.git.remote_url()
        except Exception:  # an unreadable repository must not break the status bar
            url = ""
        match = _REMOTE_NAME.search(url or "")
        if match:
            return f"{match.group(1)}/{match.group(2)}"
    return current.name


def window_url(wid: str) -> str:
    """Address that opens window `wid` in a new browser tab."""
    try:
        base = str(st.context.url).split("?")[0]
    except Exception:  # older Streamlit without st.context.url
        base = ""
    return f"{base}?w={wid}"


def new_window_url(path: Path, github: dict[str, Any]) -> str:
    """Register `path` under a fresh window id and return the address that opens it in a new browser tab."""
    wid = secrets.token_urlsafe(6)
    repositories.remember(wid, path, github)
    return window_url(wid)


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
    _restore_chat(wid)


def _restore_chat(wid: str) -> None:
    """After a page reload: bring back this window's conversation, and re-attach to an agent run that is still going."""
    if st.session_state.get("_chat_restored"):
        return
    st.session_state["_chat_restored"] = True
    if st.session_state.get("messages"):
        return
    messages = chat_store.load_chat(wid)
    current = repo()
    for message in messages:
        changes = message.changes
        if isinstance(changes, ChangeSet) and changes.state == "pending" and (current is None or current.tracker.get(changes.change_id) is None):
            changes.kept = [item["path"] for item in changes.files if item["path"] not in changes.reverted]  # the originals are gone: the edits stay
            changes.state = "accepted" if not changes.reverted else "mixed"
    run = active_run(wid)
    if run is not None:
        messages += [
            ChatMessage(role="user", text=run.request, mode=run.mode),
            ChatMessage(role="assistant", mode=run.mode, model=get_model(run.model).label, streaming=True, status="Reconnecting to the running agent"),
        ]
        st.session_state["run"], st.session_state["cursor"] = run, 0
    st.session_state["messages"] = messages


class _State:
    """Attribute access to st.session_state (S.tabs instead of st.session_state['tabs'])."""

    def __getattr__(self, name: str) -> Any:
        return st.session_state[name]

    def __setattr__(self, name: str, value: Any) -> None:
        st.session_state[name] = value


S = _State()


def repo() -> ActiveRepository | None:
    """The folder this browser window works in (a connected repository or the scratch folder)."""
    _bind_secrets()
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
