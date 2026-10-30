"""Centre panel: open-file tabs, the code editor and the Git diff viewer."""

from __future__ import annotations

from html import escape

import streamlit as st

try:
    from streamlit_ace import st_ace
except ImportError:  # the editor package is optional: fall back to a plain text area
    st_ace = None

from studio.services.workspace_service import language_for

from .state import S, attempt, close_file, log, open_file, repo

ACE_LANGUAGES = {
    "python": "python", "javascript": "javascript", "typescript": "typescript", "json": "json", "markdown": "markdown",
    "html": "html", "css": "css", "yaml": "yaml", "shell": "sh", "bash": "sh", "java": "java", "go": "golang", "rust": "rust",
    "c": "c_cpp", "cpp": "c_cpp", "csharp": "csharp", "sql": "sql", "xml": "xml", "toml": "toml", "ini": "ini",
    "plaintext": "text", "powershell": "powershell", "dockerfile": "dockerfile", "php": "php", "ruby": "ruby",
}


def _dirty(path: str) -> bool:
    return S.drafts.get(path) != S.saved.get(path)


def _select_tab() -> None:
    chosen = st.session_state.get("tab_select")
    if chosen and chosen in S.tabs:
        S.active = chosen
        S.diff_view = None


def _label(path: str) -> str:
    mark = "\u25cf " if _dirty(path) else ""
    return mark + path.rsplit("/", 1)[-1]


def _save(path: str) -> bool:
    current = repo()
    if current is None or S.notes.get(path):
        return False
    content = S.drafts.get(path, "")
    with current.lock:
        ok, _ = attempt(current.workspace.write_text, path, content)
        if ok:
            current.index.refresh_file(path)
    if ok:
        S.saved = {**S.saved, path: content}
        log(f"Saved {path}")
    return ok


@st.fragment
def _editor(path: str) -> None:
    """A fragment, so typing re-runs only this block and not the whole page."""
    note = S.notes.get(path, "")
    toolbar = st.container(key="toolbar")  # filled after the editor runs, so it sees the latest text

    if note:
        st.warning(note)
    if not note.startswith("Binary"):
        key = f"ace:{path}:{S.versions.get(path, 0)}:{st.session_state.get('epoch', 0)}"
        initial = st.session_state.setdefault("ace_init", {}).setdefault(key, S.drafts.get(path, ""))  # constant per mount, so typing never fights the component
        language = ACE_LANGUAGES.get(_language_of(path), "text")
        if st_ace is not None:
            content = st_ace(
                value=initial, language=language, theme="tomorrow_night_bright", keybinding="vscode", font_size=13, tab_size=4,
                show_gutter=True, wrap=False, auto_update=True, height="calc(100vh - 4px)", min_lines=None, max_lines=None,
                readonly=bool(note), key=key,
            )  # the iframe height is set in theme.py; 100vh inside the frame is that height
        else:
            content = st.text_area("Editor", value=initial, height=560, key=key, disabled=bool(note), label_visibility="collapsed")
        if content is not None and not note:
            S.drafts = {**S.drafts, path: content}

    with toolbar:
        top = st.columns([2.4, 1, 1.15, 1], vertical_alignment="center")
        dirty = _dirty(path)
        parent, _, name = path.rpartition("/")
        crumb = (f"{escape(parent)} / " if parent else "") + f"<b>{escape(name)}</b>"
        top[0].markdown(f"<div class='crumb'>{crumb}{'<em>UNSAVED</em>' if dirty else ''}</div>", unsafe_allow_html=True)
        if top[1].button("Save", icon=":material/save:", type="primary", disabled=bool(note) or not dirty, key=f"save:{path}", width="stretch"):
            if _save(path):
                st.toast(f"Saved {path}", icon=":material/check:")
                st.rerun()
        if top[2].button("Revert", icon=":material/undo:", disabled=not dirty, key=f"revert:{path}", width="stretch"):
            S.drafts = {**S.drafts, path: S.saved.get(path, "")}
            S.versions = {**S.versions, path: S.versions.get(path, 0) + 1}
            st.rerun()
        if top[3].button("Close", icon=":material/close:", key=f"close:{path}", width="stretch"):
            close_file(path)
            st.rerun()

    goto = S.goto
    if goto and goto["path"] == path:
        lines = S.drafts.get(path, "").splitlines()
        line = goto["line"]
        start = max(0, line - 4)
        st.caption(f"Search result at line {line}")
        st.code("\n".join(f"{n + 1:>5}  {text}" for n, text in enumerate(lines[start:line + 3], start)), language=None)


def _language_of(path: str) -> str:
    return language_for(path)


def _diff_view(path: str) -> None:
    current = repo()
    top = st.columns([7, 1.5], vertical_alignment="center")
    top[0].markdown(f"**Git diff:** {path}")
    if top[1].button("Close diff", key="close_diff", width="stretch"):
        S.diff_view = None
        st.rerun()
    if current is None or current.git is None:
        st.info("This workspace is not a Git repository.")
        return
    ok, unstaged = attempt(current.git.diff, path, False)
    ok2, staged = attempt(current.git.diff, path, True)
    if not (ok and ok2):
        return
    if staged.strip():
        st.caption("Staged changes")
        st.code(staged, language="diff", line_numbers=False)
    if unstaged.strip():
        st.caption("Unstaged changes")
        st.code(unstaged, language="diff", line_numbers=False)
    if not staged.strip() and not unstaged.strip():
        st.info("No differences for this file.")


def _hero(message: str) -> None:
    st.markdown(
        "<div class='hero'><div class='orb'>RK</div><h2>RK STUDIO</h2>"
        f"<p>{escape(message)}</p>"
        "<div class='keys'><span>Explorer: open a file</span><span>Agent: ask, plan or build</span><span>Source Control: review and commit</span></div></div>",
        unsafe_allow_html=True,
    )


def render_editor() -> None:
    with st.container(key="editorarea"):
        _render_editor_area()


def _render_editor_area() -> None:
    if repo() is None:
        _hero("Connect a repository with the GitHub button in the title bar to start.")
        return

    if S.diff_view:
        with st.container(key="diffarea"):
            _diff_view(S.diff_view)
        return

    if not S.tabs:
        _hero("Pick a file in the Explorer, or ask the agent about your repository. Edits apply as you type; press Save to write them to disk.")
        return

    if S.active not in S.tabs:
        S.active = S.tabs[0]
    if st.session_state.get("last_active") != S.active:
        st.session_state["epoch"] = st.session_state.get("epoch", 0) + 1
        st.session_state["last_active"] = S.active

    st.session_state["tab_select"] = S.active
    with st.container(key="tabs"):
        st.segmented_control(
            "Open files", options=S.tabs, format_func=_label, selection_mode="single", key="tab_select",
            on_change=_select_tab, label_visibility="collapsed", width="content",
        )
    _editor(S.active)
