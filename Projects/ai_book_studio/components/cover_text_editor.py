"""Cover-only text editor shared by the eBook and coloring Pages tabs.

Changing the text here only changes the front cover. The plan, chapters and other exports keep their own title and author.
"""

from __future__ import annotations

import streamlit as st

from components.state import bump_content, flash, guarded, make_pipeline, refresh
from models.book_models import BookProject

_OPEN_KEY = "cover_text_open"  # project id whose editor is open, or None
_ROUND_KEY = "cover_text_round"  # counts openings so each opening starts from the saved text
_LABELS = {"title": "Title", "subtitle": "Subtitle", "author": "Author"}


def _current(project: BookProject) -> dict[str, str]:
    plan = project.plan
    title, subtitle, author = project.cover_words(plan.title, plan.subtitle, plan.author)
    return {"title": title, "subtitle": subtitle, "author": author}


def _as_text(values: dict[str, str]) -> str:
    return "\n".join(f"{label}: {values[key]}" for key, label in _LABELS.items())


def _from_text(text: str, fallback: dict[str, str]) -> dict[str, str]:
    """Read the three labelled lines back. A label that is missing keeps its current value."""
    values = dict(fallback)
    lookup = {label.lower(): key for key, label in _LABELS.items()}
    for line in text.splitlines():
        label, separator, value = line.partition(":")
        key = lookup.get(label.strip().lower())
        if separator and key:
            values[key] = value.strip()
    return values


def open_cover_text_editor(project: BookProject) -> None:
    st.session_state[_OPEN_KEY] = project.project_id
    st.session_state[_ROUND_KEY] = st.session_state.get(_ROUND_KEY, 0) + 1


def render_cover_text_editor(project: BookProject, version: int) -> None:
    """Show the editor under the cover buttons while it is open for this project."""
    if st.session_state.get(_OPEN_KEY) != project.project_id or project.plan is None:
        return
    current = _current(project)
    round_no = st.session_state.get(_ROUND_KEY, 0)

    st.markdown("**Text on the front cover**")
    st.caption("Keep each label on its own line. Subtitle and Author may be left empty. This changes the front cover only.")
    text = st.text_area(
        "Text on the front cover",
        _as_text(current),
        height=120,
        key=f"cover_text_edit_{version}_{round_no}",
        label_visibility="collapsed",
    )
    save, cancel = st.columns(2)
    if save.button("💾 Save", type="primary", width="stretch", key="cover_text_save"):
        values = _from_text(text, current)
        if not values["title"]:
            st.error("The title cannot be empty.")
        else:
            with guarded("Updating the cover text"):
                previous = dict(project.cover_text)
                project.cover_text = values
                pipeline = make_pipeline(project)
                try:
                    pipeline.recompose_cover()
                except BaseException:
                    project.cover_text = previous
                    raise
                pipeline.storage.save_project_meta(project)
                st.session_state[_OPEN_KEY] = None
                flash("The cover text was updated.", "success")
                bump_content()
                refresh()
    if cancel.button("✖ Cancel", width="stretch", key="cover_text_cancel"):
        st.session_state[_OPEN_KEY] = None
        refresh()
