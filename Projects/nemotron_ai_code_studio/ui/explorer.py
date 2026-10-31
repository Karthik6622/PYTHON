"""Left side panel: file explorer and repository search."""

from __future__ import annotations

from html import escape

import streamlit as st

from studio.security import is_sensitive_path
from studio.services import folders, local_sync

from .dialogs import choose_working_folder, ensure_folder
from .state import S, attempt, close_file, log, open_file, recent_edits, repo
from .theme import section_title


def _join(directory: str, name: str) -> str:
    name = name.strip().strip("/").replace("\\", "/")
    return f"{directory}/{name}" if directory else name


def _close_under(path: str) -> None:
    for tab in list(S.tabs):
        if tab == path or tab.startswith(f"{path}/"):
            close_file(tab)


def _create(kind: str, name: str) -> None:
    if not name.strip() or not ensure_folder():
        return
    current = repo()
    if current is None:
        return
    path = _join(S.cwd, name)
    with current.lock:
        ok, result = attempt(current.workspace.create, path, kind)
        if ok:
            current.index.refresh_file(result["path"])
    if ok:
        log(f"Created {result['path']}")
        if kind == "file":
            open_file(result["path"])


def _rename(old: str, new: str) -> None:
    current = repo()
    if current is None or not new.strip() or new.strip() == old:
        return
    with current.lock:
        ok, result = attempt(current.workspace.rename, old, new.strip().replace("\\", "/"))
        if ok:
            current.index.refresh_file(result["from"])
            current.index.refresh_file(result["to"])
    if ok:
        _close_under(old)
        log(f"Renamed {old} to {result['to']}")


def _delete(path: str) -> None:
    current = repo()
    if current is None:
        return
    with current.lock:
        ok, _ = attempt(current.workspace.delete, path)
        if ok:
            current.index.refresh_file(path)
    if ok:
        _close_under(path)
        log(f"Deleted {path}")


def render_explorer() -> None:
    current = repo()
    if current is None:
        st.info("No folder is open.")
        return
    link = st.session_state.get("_link")

    section_title("Explorer", current.name)
    native = folders.native_picker_available()
    if native:
        # Running on the user's computer: the operating system's own folder window, and the chosen folder is used in place (no copy).
        st.button("Connect Local folder", icon=":material/folder_open:", key="pick_work_folder", on_click=choose_working_folder, width="stretch")
    else:
        if link is None:
            st.caption("Open a folder from your computer to start. The real path of that folder is only available when RK Studio runs on your computer.")
        else:
            listed_note = f" {len(link.listed)} file(s) are listed but not copied." if link.listed else ""
            st.caption(
                f"Connected to {link.name} on your computer.{listed_note} "
                "The path below is the hosted working copy: a browser never discloses the original local path. "
                "Run RK Studio on your computer to work in the folder itself."
            )
    lost = st.session_state.get("_folder_missing")
    if lost:
        st.warning(f"The folder {lost} was moved or deleted. Use Connect Local folder to choose it again.")
    if current.git_info.error:
        st.warning(current.git_info.error)
        if current.git_info.detail:
            with st.expander("Technical details"):
                st.code(current.git_info.detail, language=None)
    new_file, new_dir, manage, refresh = st.columns(4)
    with new_file.popover("", icon=":material/note_add:", help="New file", width="stretch"):
        name = st.text_input("File name", key="new_file_name", placeholder="src/example.py")
        st.button("Create file", key="create_file_btn", on_click=_create, args=("file", name), disabled=not name.strip())
    with new_dir.popover("", icon=":material/create_new_folder:", help="New folder", width="stretch"):
        name = st.text_input("Folder name", key="new_dir_name", placeholder="src/utils")
        st.button("Create folder", key="create_dir_btn", on_click=_create, args=("dir", name), disabled=not name.strip())
    if refresh.button("", icon=":material/refresh:", help="Refresh", width="stretch", key="refresh_tree"):
        current.reindex()
        st.rerun()

    # Files the browser found but did not copy are listed too (with the reason); they can be seen but not changed here.
    listed = link.listed if link is not None else []
    ok, found = attempt(current.workspace.list_dir, S.cwd, quiet=bool(listed))
    extra = local_sync.listed_entries(listed, S.cwd) if listed else []
    if not ok and not extra:
        S.cwd = ""
        return
    real = found if ok else []
    names = {e["name"] for e in real}
    entries = [*real, *(e for e in extra if e["name"] not in names)]
    entries.sort(key=lambda e: (e["type"] != "dir", e["name"].lower()))
    editable = [e for e in entries if not e.get("listed")]

    with manage.popover("", icon=":material/edit:", help="Rename or delete", width="stretch"):
        if not editable:
            st.caption("Nothing in this folder that can be changed.")
        else:
            target = st.selectbox("Item", [e["path"] for e in editable], key="manage_target")
            new_name = st.text_input("Rename to (path inside the repository)", value=target, key=f"rename_to:{target}")
            st.button("Rename", key="rename_btn", on_click=_rename, args=(target, new_name), disabled=new_name.strip() == target)
            confirm = st.checkbox("Confirm delete (cannot be undone)", key=f"confirm_del:{target}")
            st.button("Delete", key="delete_btn", on_click=_delete, args=(target,), disabled=not confirm, type="primary")

    full_path = str(current.path.joinpath(*[p for p in S.cwd.split("/") if p])) if current.path else ""
    st.markdown(
        f"<div class='explorer-path' title='{escape(full_path, quote=True)}'>{escape(full_path)}</div>",
        unsafe_allow_html=True,
    )
    if S.cwd and st.button("..", key="up", icon=":material/arrow_upward:", width="stretch"):
        S.cwd = S.cwd.rsplit("/", 1)[0] if "/" in S.cwd else ""
        st.rerun()

    if not entries:
        st.caption("This folder is empty.")
    hot = recent_edits()  # files (and their folders) the agent changed a moment ago glow, then fade back to normal
    for entry in entries[:500]:
        is_dir = entry["type"] == "dir"
        label = entry["name"] + ("  (skipped by indexing)" if entry.get("ignored") else "")
        if entry.get("listed") and not is_dir:
            label = f"{entry['name']}  (not copied: {entry['why']})"
        pressed = st.button(
            label, key=f"entry:{entry['path']}{'__hot__' if entry['path'] in hot else ''}", width="stretch",
            icon=":material/folder:" if is_dir else ":material/description:",
            type="primary" if entry["path"] == S.active else "secondary",
        )
        if pressed:
            if is_dir:
                S.cwd = entry["path"]
                st.rerun()
            elif entry.get("listed"):
                st.toast(
                    f"{entry['name']} is not copied to the hosted copy ({entry['why']}). Run the Studio on your computer to open it.",
                    icon=":material/info:",
                )
            else:
                open_file(entry["path"])
                st.rerun()
    if len(entries) > 500:
        st.caption(f"Showing the first 500 of {len(entries)} entries.")


def render_search() -> None:
    current = repo()
    if current is None:
        st.info("No repository is open.")
        return
    section_title("Search")
    with st.form("search_form", border=False):
        query = st.text_input("Search text", placeholder="Search in repository", label_visibility="collapsed")
        left, right = st.columns(2)
        regex = left.checkbox("Regex")
        case = right.checkbox("Match case")
        submitted = st.form_submit_button("Search", icon=":material/search:", width="stretch")
    if submitted and query.strip():
        ok, hits = attempt(current.search.search_text, query.strip(), regex=regex, case_sensitive=case, max_results=200)
        st.session_state["search_hits"] = [h for h in hits if not is_sensitive_path(h["path"])] if ok else []
        st.session_state["search_query"] = query.strip()

    hits = st.session_state.get("search_hits")
    if hits is None:
        return
    if not hits:
        st.caption("No results.")
        return
    st.caption(f"{len(hits)} result(s) for '{st.session_state.get('search_query', '')}'")
    for index, hit in enumerate(hits[:100]):
        if st.button(f"{hit['path']}:{hit['line']}  {hit['text'][:60]}", key=f"hit:{index}", width="stretch"):
            open_file(hit["path"])
            S.goto = {"path": hit["path"], "line": hit["line"]}
            st.rerun()
