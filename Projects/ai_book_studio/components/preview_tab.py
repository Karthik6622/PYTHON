"""Tab 5: read the book as a reader would."""

from __future__ import annotations

import streamlit as st

from components.state import current_project, go_to, image_if_exists
from models.book_models import BookProject
from services.chapter_writer import author_page_text
from utils.text_utils import chapter_label, count_words, estimate_pdf_pages, label


def _sections(project: BookProject) -> list[tuple[str, str]]:
    """(id, heading) for every section that has content, in reading order."""
    plan = project.plan
    assert plan is not None
    language = plan.language
    options = project.book_input
    items: list[tuple[str, str]] = []
    for key in ("dedication", "preface", "introduction"):
        if options.has(key) and project.front_matter.get(key, "").strip():
            items.append((key, label(key, language)))
    for chapter in plan.chapters:
        if project.chapters.get(chapter.chapter_number, "").strip():
            items.append((f"chapter:{chapter.chapter_number}", f"{chapter_label(chapter.chapter_number, language)}: {chapter.title}"))
    for key in ("conclusion", "glossary"):
        if options.has(key) and project.front_matter.get(key, "").strip():
            items.append((key, label(key, language)))
    if options.has("author_page"):
        items.append(("author_page", label("author_page", language)))
    return items


def render() -> None:
    project = current_project()
    if project is None or project.plan is None:
        st.info("Create a book plan first.")
        return
    plan = project.plan
    sections = _sections(project)
    if not project.chapters:
        st.info("Nothing to preview yet. Generate the book on the Plan tab.")
        return

    words = [count_words(text) for text in project.chapters.values()]
    st.subheader(plan.title)
    if project.status.stage == "completed":
        st.button("📤 Looks good: go to Export and download", on_click=go_to, args=("export",), type="primary")
    if plan.subtitle:
        st.caption(plan.subtitle)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Chapters written", f"{len(words)} / {len(plan.chapters)}")
    m2.metric("Words", f"{sum(words):,}")
    m3.metric("Estimated pages", estimate_pdf_pages(project.book_input, words), help="Estimate. The exported PDF page count is shown on the Export tab.")
    m4.metric("Author", plan.author)

    left, right = st.columns([1, 3], gap="large")
    with left:
        cover = image_if_exists(project, "cover_final")
        if cover:
            st.image(str(cover), width="stretch")
        else:
            st.info("No cover yet.")
    with right:
        keys = [item[0] for item in sections]
        selected = st.selectbox("Read", keys, format_func=lambda k: dict(sections)[k], key="preview_section")
        st.markdown(f"### {dict(sections)[selected]}")
        if selected.startswith("chapter:"):
            number = int(selected.split(":")[1])
            picture = image_if_exists(project, f"chapter_{number:02d}")
            if picture:
                st.image(str(picture), width="stretch")
            st.markdown(project.chapters[number])
        elif selected == "author_page":
            st.markdown(author_page_text(project))
        else:
            st.markdown(project.front_matter[selected])

    if project.status.warnings:
        with st.expander(f"Warnings ({len(project.status.warnings)})"):
            for warning in project.status.warnings:
                st.markdown(f"- {warning}")
