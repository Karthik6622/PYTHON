"""Left side panel: file explorer and repository search."""

from __future__ import annotations

import streamlit as st

from studio.security import is_sensitive_path

from .state import S, attempt, close_file, log, open_file, repo


def _join(directory: str, name: str) -> str:
    name = name.strip().strip("/").replace("\\", "/")
    return f"{directory}/{name}" if directory else name


def _close_under(path: str) -> None:
    for tab in list(S.tabs):
        if tab == path or tab.startswith(f"{path}/"):
            close_file(tab)


def _create(kind: str, name: str) -> None:
    current = repo()
    if current is None or not name.strip():
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
        st.info("No repository is open. Use the GitHub button to connect one.")
        return

    st.caption(f"EXPLORER  |  {current.name}")
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

    ok, entries = attempt(current.workspace.list_dir, S.cwd)
    if not ok:
        S.cwd = ""
        return

    with manage.popover("", icon=":material/edit:", help="Rename or delete", width="stretch"):
        if not entries:
            st.caption("Nothing in this folder.")
        else:
            target = st.selectbox("Item", [e["path"] for e in entries], key="manage_target")
            new_name = st.text_input("Rename to (path inside the repository)", value=target, key=f"rename_to:{target}")
            st.button("Rename", key="rename_btn", on_click=_rename, args=(target, new_name), disabled=new_name.strip() == target)
            confirm = st.checkbox("Confirm delete (cannot be undone)", key=f"confirm_del:{target}")
            st.button("Delete", key="delete_btn", on_click=_delete, args=(target,), disabled=not confirm, type="primary")

    crumbs = ["root", *[p for p in S.cwd.split("/") if p]]
    st.markdown(" / ".join(f"`{c}`" for c in crumbs))
    if S.cwd and st.button("..", key="up", icon=":material/arrow_upward:", width="stretch"):
        S.cwd = S.cwd.rsplit("/", 1)[0] if "/" in S.cwd else ""
        st.rerun()

    if not entries:
        st.caption("This folder is empty.")
    for entry in entries[:500]:
        is_dir = entry["type"] == "dir"
        label = entry["name"] + ("  (skipped by indexing)" if entry.get("ignored") else "")
        pressed = st.button(
            label, key=f"entry:{entry['path']}", width="stretch",
            icon=":material/folder:" if is_dir else ":material/description:",
            type="primary" if entry["path"] == S.active else "secondary",
        )
        if pressed:
            if is_dir:
                S.cwd = entry["path"]
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
    st.caption("SEARCH")
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
