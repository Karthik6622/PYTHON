"""Tab 1: collect the book idea and settings, then create the plan."""

from __future__ import annotations

import streamlit as st

from components.identity import owner_id
from components.state import current_project, get_storage, guarded, plan_job_here, start_plan
from config import (
    AUDIENCES,
    BOOK_TYPES,
    CONTENT_OPTIONS,
    ILLUSTRATION_FREQUENCIES,
    IMAGE_STYLES,
    LANGUAGES,
    MAX_PAGES,
    MIN_PAGES,
    WRITING_STYLES,
)
from models.book_models import BookInput
from utils.text_utils import compute_budget
from utils.validation_utils import validate_book_input

_LANGUAGE_NOTES = {
    "Tamil": "Tamil and Hindi text is exported with a Unicode font, but the PDF engine does not shape complex scripts perfectly. The DOCX export is the most faithful for these languages.",
    "Hindi": "Tamil and Hindi text is exported with a Unicode font, but the PDF engine does not shape complex scripts perfectly. The DOCX export is the most faithful for these languages.",
    "Japanese": "Japanese PDFs need a Japanese font installed (see the README). Without one, the PDF may show missing characters.",
}


def collect_input() -> BookInput:
    """Build a ``BookInput`` from the Create tab widgets."""
    state = st.session_state
    return BookInput(
        book_idea=state["in_idea"].strip(),
        preferred_title=state["in_title"].strip(),
        author_name=state["in_author"].strip(),
        author_bio=state["in_bio"].strip(),
        book_type=state["in_type"],
        custom_book_type=state["in_custom_type"].strip(),
        audience=state["in_audience"],
        writing_style=state["in_style"],
        language=state["in_language"],
        pages=state["in_pages"],
        illustration_frequency=state["in_frequency"],
        image_style=state["in_image_style"],
        content_options=[CONTENT_OPTIONS[label] for label in CONTENT_OPTIONS if label in state["in_options"]],
    )


def render() -> None:
    st.subheader("Describe your book")
    st.markdown('<p class="section-note">Tell us the idea; the app plans, writes, reviews and illustrates the book.</p>', unsafe_allow_html=True)

    job = plan_job_here()
    if job is not None and job.running:
        st.info("Your book plan is being created. Watch the live status on the **Plan** tab or in the sidebar.")

    left, right = st.columns([3, 2], gap="large")
    with left:
        st.text_area(
            "Book idea *",
            key="in_idea",
            height=190,
            max_chars=6000,
            placeholder="Example: A retired lighthouse keeper discovers that her lantern can guide lost ships through time.",
        )
        st.text_input("Preferred book title (optional)", key="in_title", max_chars=150, help="Leave empty to let the AI suggest a title.")
        st.text_input("Author name *", key="in_author", max_chars=100)
        st.text_area(
            "Author bio (optional)",
            key="in_bio",
            height=90,
            max_chars=1200,
            help="Used on the 'About the Author' page. Nothing is invented if you leave it empty.",
        )
    with right:
        st.selectbox("Book type", BOOK_TYPES, key="in_type")
        if st.session_state["in_type"] == "Custom":
            st.text_input("Custom book type *", key="in_custom_type", max_chars=80)
        st.selectbox("Target audience", AUDIENCES, key="in_audience")
        st.selectbox("Writing style", WRITING_STYLES, key="in_style")
        st.selectbox("Language", LANGUAGES, key="in_language")

    note = _LANGUAGE_NOTES.get(st.session_state["in_language"])
    if note:
        st.info(note)

    c1, c2, c3 = st.columns(3)
    c1.number_input("Number of pages", min_value=MIN_PAGES, max_value=MAX_PAGES, step=5, key="in_pages", help="Approximate. Final page counts vary with fonts, images and spacing.")
    c2.selectbox("Illustration frequency", ILLUSTRATION_FREQUENCIES, key="in_frequency")
    c3.selectbox("Image style", IMAGE_STYLES, key="in_image_style")

    st.multiselect("Include in the book", list(CONTENT_OPTIONS), key="in_options")

    book_input = collect_input()
    budget = compute_budget(book_input)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Reserved pages", budget.reserved_pages, help="Cover, title, front and back matter.")
    m2.metric("Content pages", budget.content_pages)
    m3.metric("Suggested chapters", budget.recommended_chapters)
    m4.metric("Target words", f"{budget.target_words:,}")
    if budget.clamped:
        st.warning("The selected front and back matter use most of the pages. Remove some options or add pages.")

    busy = job is not None and job.running
    if st.button("✨ Create Book Plan", type="primary", width="stretch", disabled=busy):
        problems = validate_book_input(book_input)
        if problems:
            for problem in problems:
                st.error(problem)
            return
        _create_plan(book_input)


def _create_plan(book_input: BookInput) -> None:
    storage = get_storage()
    project = current_project()
    created = False
    started = False
    with guarded("Creating the plan"):
        if project is not None and not project.chapters:
            project.book_input = book_input
            storage.save_project_meta(project)
        else:
            project = storage.create_project(book_input, owner=owner_id())
            created = True
        started = start_plan(project, new_book=created)
    if not started:
        if created:
            with guarded("Removing the unfinished project"):
                storage.delete_project(project.project_id)
        return
    st.rerun()
