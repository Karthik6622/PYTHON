"""Tab 3: read, edit, regenerate and review chapters."""

from __future__ import annotations

import streamlit as st

from components.progress_panel import render_live
from components.state import bump_content, current_project, flash, get_storage, guarded, job_running, make_pipeline, refresh
from models.book_models import BookProject
from utils.text_utils import count_words


def render() -> None:
    project = current_project()
    if project is None or project.plan is None:
        st.info("Create a book plan first.")
        return
    plan = project.plan
    st.subheader("Chapters")
    render_live()
    if not project.chapters:
        return

    numbers = [c.chapter_number for c in plan.chapters]
    chosen = st.selectbox(
        "Open chapter",
        numbers,
        format_func=lambda n: f"Chapter {n}: {plan.chapter(n).title}",
        key="chapters_selected",
    )
    _chapter_editor(project, chosen)


def _chapter_editor(project: BookProject, number: int) -> None:
    storage = get_storage()
    version = st.session_state["content_version"]
    text = project.chapters.get(number, "")
    review = project.reviews.get(number)

    if review:
        pill = "✅ Passed" if review.passed else "⚠️ Needs attention"
        st.markdown(f"**Quality check:** {pill} · score {review.score}/100 · {review.revisions} automatic revision(s)")
        if review.editor_summary:
            st.caption(review.editor_summary)
        if review.issues:
            with st.expander("Editor notes"):
                for issue in review.issues:
                    st.markdown(f"- {issue}")
                for fix in review.corrections_required:
                    st.markdown(f"- *Fix:* {fix}")

    edited = st.text_area(
        "Chapter text (Markdown)",
        text,
        height=480,
        key=f"chapter_text_{number}_{version}",
        disabled=not text,
        help="Use ## for subheadings, - for bullets and *italic* or **bold** for emphasis.",
    )
    st.caption(f"{count_words(edited):,} words")

    a, b, c = st.columns(3)
    locked = job_running(project)
    if locked:
        st.caption("Editing is locked while the book is being generated.")
    if a.button("💾 Save Edits", key=f"save_{number}", width="stretch", disabled=locked or not text or edited == text):
        project.chapters[number] = edited.strip()
        storage.save_chapter(project, number)
        bump_content()
        flash(f"Chapter {number} saved. Use “Review Chapter Again” to refresh the quality check.", "success")
        refresh()
    if b.button("🔁 Regenerate Chapter", key=f"regen_{number}", width="stretch", disabled=locked):
        with guarded(f"Regenerating chapter {number}"):
            with st.spinner(f"Rewriting chapter {number}..."):
                make_pipeline(project).regenerate_chapter(number)
            bump_content()
            flash(f"Chapter {number} was rewritten, reviewed and summarised.", "success")
            refresh()
    if c.button("🔍 Review Chapter Again", key=f"review_{number}", width="stretch", disabled=locked or not text):
        with guarded(f"Reviewing chapter {number}"):
            with st.spinner("The editor is reading the chapter..."):
                make_pipeline(project).review_again(number)
            bump_content()
            flash(f"Chapter {number} was reviewed again.", "success")
            refresh()

    summary = project.summaries.get(number)
    if summary:
        with st.expander("Continuity summary (used by the following chapters)"):
            for title, values in (
                ("Key events or points", summary.important_events_or_points),
                ("Character changes", summary.character_changes),
                ("New locations", summary.new_locations),
                ("New terms", summary.new_terms),
                ("Unresolved items", summary.unresolved_items),
                ("Notes for the next chapter", summary.continuity_notes_for_next_chapter),
            ):
                if values:
                    st.markdown(f"**{title}**")
                    for value in values:
                        st.markdown(f"- {value}")
