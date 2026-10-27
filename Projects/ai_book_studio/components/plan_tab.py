"""Tab 2: review and edit the plan, then generate the complete book."""

from __future__ import annotations

import streamlit as st

from components.state import current_project, flash, get_storage, guarded, make_pipeline, refresh, set_project
from models.book_models import BookProject
from utils.retry_utils import AIBookError
from utils.text_utils import compute_budget
from utils.validation_utils import validate_plan


def _key(name: str, *parts: object) -> str:
    return "_".join([name, str(st.session_state["plan_version"]), *map(str, parts)])


def render() -> None:
    project = current_project()
    if project is None or project.plan is None:
        st.info("Create a book plan on the **Create** tab first.")
        return
    plan = project.plan
    budget = compute_budget(project.book_input)

    st.subheader("Book plan")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Chapters", len(plan.chapters))
    m2.metric("Planned words", f"{plan.total_target_words:,}")
    m3.metric("Target pages", project.book_input.pages)
    m4.metric("Language", plan.language)
    if project.chapters:
        st.warning("Chapters have already been written. Edits to the plan do not rewrite them; use the Chapters tab to regenerate a chapter.")

    st.text_input("Title", plan.title, key=_key("p_title"), max_chars=200)
    st.text_input("Subtitle", plan.subtitle, key=_key("p_subtitle"), max_chars=250)
    st.text_area("Description", plan.description, key=_key("p_desc"), height=100)
    a, b, c = st.columns(3)
    a.text_input("Main theme", plan.main_theme, key=_key("p_theme"))
    b.text_input("Tone", plan.tone, key=_key("p_tone"))
    c.text_input("Visual style", plan.visual_style, key=_key("p_visual"))

    st.markdown("##### Chapters")
    for chapter in plan.chapters:
        n = chapter.chapter_number
        with st.expander(f"Chapter {n}: {chapter.title}", expanded=False):
            st.text_input("Chapter title", chapter.title, key=_key("ct", n), max_chars=200)
            st.text_area("Objective", chapter.objective, key=_key("co", n), height=70)
            st.text_area("Summary", chapter.summary, key=_key("cs", n), height=90)
            st.text_input("Key topics (comma separated)", ", ".join(chapter.key_topics), key=_key("ck", n))
            x, y = st.columns(2)
            x.number_input("Target words", min_value=50, max_value=8000, value=max(50, chapter.target_words), step=50, key=_key("cw", n))
            y.checkbox("Illustrate this chapter", chapter.requires_image, key=_key("ci", n))
            st.text_area("Illustration idea", chapter.image_concept, key=_key("cc", n), height=70)

    save_col, regen_col = st.columns(2)
    if save_col.button("💾 Save Plan Changes", width="stretch"):
        _save_plan(project, budget.target_words)
    with regen_col:
        confirmed = True
        if project.chapters:
            confirmed = st.checkbox("Discard generated chapters and images when regenerating", key="plan_regen_confirm")
        if st.button("🔄 Regenerate Plan", width="stretch", disabled=not confirmed):
            _regenerate_plan(project)

    st.divider()
    _generation_section(project)


def _save_plan(project: BookProject, target_words: int) -> None:
    state = st.session_state
    edited = project.plan.model_copy(deep=True)
    edited.title = state[_key("p_title")].strip()
    edited.subtitle = state[_key("p_subtitle")].strip()
    edited.description = state[_key("p_desc")].strip()
    edited.main_theme = state[_key("p_theme")].strip()
    edited.tone = state[_key("p_tone")].strip()
    edited.visual_style = state[_key("p_visual")].strip()
    for chapter in edited.chapters:
        n = chapter.chapter_number
        chapter.title = state[_key("ct", n)].strip()
        chapter.objective = state[_key("co", n)].strip()
        chapter.summary = state[_key("cs", n)].strip()
        chapter.key_topics = [topic.strip() for topic in state[_key("ck", n)].split(",") if topic.strip()]
        chapter.target_words = int(state[_key("cw", n)])
        chapter.requires_image = bool(state[_key("ci", n)])
        chapter.image_concept = state[_key("cc", n)].strip()
    edited.estimated_words = edited.total_target_words
    report = validate_plan(edited, target_words)
    if not report.ok:
        for error in report.errors:
            st.error(error)
        return
    project.plan = edited
    with guarded("Saving the plan"):
        get_storage().save_plan(project)
        for warning in report.warnings:
            flash(warning, "warning")
        flash("Plan saved.", "success")
        refresh()


def _regenerate_plan(project: BookProject) -> None:
    storage = get_storage()
    done = False
    with guarded("Regenerating the plan"):
        if project.chapters or project.images or project.bible:
            storage.clear_generated(project)
        with st.spinner("Nemotron is designing a new plan..."):
            make_pipeline(project).create_plan()
        done = True
    if done:
        set_project(project)
        flash("A new plan was created.", "success")
        st.rerun()


def _generation_section(project: BookProject) -> None:
    st.markdown("##### Generate the book")
    st.markdown(
        '<p class="section-note">Bible, front matter, every chapter (written, reviewed, revised and summarised), illustrations, '
        "cover and the PDF and DOCX files. Progress is saved after every step, so you can resume at any time.</p>",
        unsafe_allow_html=True,
    )
    status = project.status
    if status.stage == "failed" and status.error:
        st.error(f"The last run stopped: {status.error}")
    if status.stage == "completed":
        st.success("The book has been generated. Open the Preview and Export tabs.")
    elif status.stage in {"running", "failed"}:
        st.progress(min(max(status.progress, 0.0), 1.0), text=status.message or "Paused")

    label = "▶️ Resume Generation" if status.stage in {"running", "failed"} else "🚀 Generate Complete Book"
    if not st.button(label, type="primary", width="stretch"):
        return

    bar = st.progress(0.0, text="Starting...")

    def on_progress(fraction: float, message: str) -> None:
        bar.progress(min(max(fraction, 0.0), 1.0), text=message)

    try:
        summary = make_pipeline(project, on_progress).generate_complete_book()
    except AIBookError as exc:
        flash(f"{exc.user_message} Your progress is saved; press Resume to continue.", "error")
    else:
        st.session_state["export_summary"] = summary
        flash(
            f"Your book is ready ({summary.pages} PDF pages)."
            + (f" {len(summary.warnings)} warning(s) need your attention." if summary.warnings else ""),
            "success",
        )
    refresh()
