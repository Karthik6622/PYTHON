"""Source control panel: status, stage / unstage / discard, commit, fetch, pull and push."""

from __future__ import annotations

import streamlit as st

from studio.config import settings

from .state import S, attempt, log, reload_paths, repo
from .theme import section_title

LETTERS = {"modified": "M", "added": "A", "deleted": "D", "untracked": "U", "renamed": "R", "conflicted": "C"}


def _selected(prefix: str) -> list[str]:
    return [key.split(":", 2)[2] for key, value in st.session_state.items() if key.startswith(f"sc:{prefix}:") and value]


def _clear_selection() -> None:
    for key in [k for k in st.session_state if k.startswith("sc:")]:
        del st.session_state[key]


def _stage(paths: list[str] | None) -> None:
    current = repo()
    ok, _ = attempt(current.git.stage, paths)
    if ok:
        log("Staged " + (", ".join(paths) if paths else "all changes"))
    _clear_selection()


def _unstage(paths: list[str] | None) -> None:
    current = repo()
    ok, _ = attempt(current.git.unstage, paths)
    if ok:
        log("Unstaged " + (", ".join(paths) if paths else "all changes"))
    _clear_selection()


def _commit() -> None:
    current = repo()
    message = st.session_state.get("commit_message", "")
    ok, result = attempt(current.git.commit, message)
    if ok:
        log(f"Committed {result['short']}: {result['message']}")
        st.toast(f"Committed {result['short']}", icon=":material/check:")
        st.session_state["commit_message"] = ""
        _clear_selection()


def _undo_commit() -> None:
    current = repo()
    ok, info = attempt(current.git.undo_last_commit)
    if ok:
        log(f"Undid commit {info['short']}: {info['message']}")
        st.toast(f"Undid {info['short'][:7]}. Its changes are staged again.", icon=":material/undo:")
        st.session_state["commit_message"] = info["full_message"]  # edit it and commit again
        _clear_selection()


def _remote(action: str) -> None:
    current = repo()
    ok, message = attempt(getattr(current.git, action))
    if not ok:
        if not settings.github_token and "github.com" in current.git.remote_url().lower():
            st.session_state["_ask_github"] = True  # a fetch, pull or push to GitHub needs the account: ask now, and only now
        return
    if ok:
        log(f"git {action}: {message}")
        st.toast(f"{action.capitalize()} complete", icon=":material/check:")
        if action == "pull":
            current.reindex()
            reload_paths(list(S.tabs))


@st.dialog("Discard changes")
def _discard_dialog(paths: list[str]) -> None:
    st.warning("These changes will be lost permanently. Untracked files are deleted.")
    for path in paths:
        st.markdown(f"- `{path}`")
    left, right = st.columns(2)
    if left.button("Cancel", width="stretch"):
        st.rerun()
    if right.button("Discard", type="primary", width="stretch"):
        current = repo()
        ok, done = attempt(current.git.discard, paths)
        if ok:
            with current.lock:
                for path in done:
                    current.index.refresh_file(path)
            log("Discarded " + ", ".join(done))
            reload_paths(done)
        _clear_selection()
        st.rerun()


@st.dialog("Push to remote")
def _push_dialog() -> None:
    current = repo()
    branch = current.git.current_branch()
    st.markdown(f"Push branch `{branch}` to `origin`?")
    if current.github and current.github.get("can_push") is False:
        st.error("Your token does not have push permission on this repository. The push will probably be rejected.")
    st.caption("Nothing is pushed unless you confirm here.")
    left, right = st.columns(2)
    if left.button("Cancel", width="stretch"):
        st.rerun()
    if right.button("Push", type="primary", width="stretch"):
        _remote("push")
        st.rerun()


def _file_rows(files: list[dict], section: str) -> None:
    for entry in files:
        box, label = st.columns([1, 9], vertical_alignment="center")
        box.checkbox(entry["path"], key=f"sc:{section}:{entry['path']}", label_visibility="collapsed")
        if label.button(f"{LETTERS.get(entry['kind'], '?')}   {entry['path']}", key=f"scdiff:{section}:{entry['path']}", width="stretch", help="View diff"):
            S.diff_view = entry["path"]
            st.rerun()


def render_source_control() -> None:
    current = repo()
    if current is None:
        st.info("No repository is open.")
        return
    if current.git is None:
        st.info("This workspace is not a Git repository.")
        return
    ok, status = attempt(current.git.status)
    if not ok:
        return

    sync = f"ahead {status['ahead']}, behind {status['behind']}" if status["upstream"] else "no upstream"
    section_title("Source Control", f"{status['branch']}  |  {sync}")

    a, b, c, d = st.columns(4)
    if a.button("", icon=":material/refresh:", help="Refresh", key="sc_refresh", width="stretch"):
        st.rerun()
    if b.button("", icon=":material/cloud_sync:", help="Fetch", key="sc_fetch", width="stretch"):
        _remote("fetch")
        st.rerun()
    if c.button("", icon=":material/download:", help="Pull (fast-forward only)", key="sc_pull", width="stretch"):
        _remote("pull")
        st.rerun()
    if d.button("", icon=":material/upload:", help="Push", key="sc_push", width="stretch"):
        _push_dialog()

    staged = [f for f in status["files"] if f["staged"]]
    unstaged = [f for f in status["files"] if f["unstaged"]]
    if status["clean"]:
        st.caption("No changes.")

    st.text_area("Message", key="commit_message", placeholder="Commit message", height=80, label_visibility="collapsed")
    message_ok = bool(st.session_state.get("commit_message", "").strip())
    st.button("Commit", icon=":material/check:", type="primary", width="stretch", on_click=_commit, disabled=not (staged and message_ok), help="Commits the staged files")

    ok, last = attempt(current.git.last_commit, quiet=True)
    if ok and last:
        st.caption(f"Last commit {last['short'][:7]}: {last['message'][:60]}" + ("  (pushed)" if last["pushed"] else ""))
        st.button(
            "Undo last commit", icon=":material/undo:", key="sc_undo", width="stretch", on_click=_undo_commit, disabled=last["pushed"],
            help="Already pushed to GitHub: cannot be undone here" if last["pushed"] else "Undo the last commit. Its changes stay staged and its message comes back so you can commit again.",
        )

    if staged:
        st.markdown(f"**Staged changes ({len(staged)})**")
        _file_rows(staged, "staged")
        picked = _selected("staged")
        st.button("Unstage selected" if picked else "Unstage all", key="unstage_btn", width="stretch", on_click=_unstage, args=(picked or None,))
    if unstaged:
        st.markdown(f"**Changes ({len(unstaged)})**")
        _file_rows(unstaged, "unstaged")
        picked = _selected("unstaged")
        x, y = st.columns(2)
        x.button("Stage selected" if picked else "Stage all", key="stage_btn", width="stretch", on_click=_stage, args=(picked or None,))
        if y.button("Discard selected", key="discard_btn", width="stretch", disabled=not picked):
            _discard_dialog(picked)
