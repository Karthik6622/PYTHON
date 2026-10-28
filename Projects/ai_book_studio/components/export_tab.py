"""Tab 6: build and download the PDF, DOCX, cover and project data."""

from __future__ import annotations

import re
import time

import streamlit as st

from components.state import current_project, flash, get_storage, guarded, image_if_exists, job_running, make_pipeline, refresh


def _safe_name(title: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", title).strip("_")[:60] or "book"


def render() -> None:
    project = current_project()
    if project is None or project.plan is None:
        st.info("Create a book plan first.")
        return
    if job_running(project):
        st.info("The book is still being generated. The PDF and DOCX are built automatically at the end; see the Chapters tab.")
        return
    storage = get_storage()
    st.subheader("Export")

    missing = [n for n in project.chapter_numbers if not project.chapters.get(n, "").strip()]
    if missing:
        st.warning("These chapters have no text yet: " + ", ".join(map(str, missing)) + ". Generate or resume the book first.")
    if st.button("🛠️ Build PDF and DOCX", type="primary", width="stretch", disabled=bool(missing)):
        with guarded("Building the export files"):
            started = time.time()
            with st.status("Building the PDF and DOCX...", expanded=True) as status:
                bar = st.progress(0.0, text="Starting...")

                def on_progress(fraction: float, message: str) -> None:
                    bar.progress(min(max(fraction, 0.0), 1.0), text=f"{message}  ({fraction * 100:.0f}%)")
                    st.write(f"{time.time() - started:4.0f}s  {message}")

                try:
                    summary = make_pipeline(project).assemble_exports(progress=on_progress)
                except BaseException:
                    status.update(label="The export failed", state="error", expanded=True)
                    raise
                status.update(label=f"PDF and DOCX built in {time.time() - started:.0f}s", state="complete", expanded=False)
            st.session_state["export_summary"] = summary
            flash(f"The files were built. The PDF has {summary.pages} pages.", "success")
            refresh()

    summary = st.session_state.get("export_summary")
    warnings = summary.warnings if summary else project.status.warnings
    if summary:
        st.success(f"PDF: {summary.pages} pages (you requested about {project.book_input.pages}). Final page counts vary with fonts, images, spacing, headings and paragraph lengths.")
    if warnings:
        with st.expander(f"Warnings ({len(warnings)})", expanded=True):
            for warning in warnings:
                st.markdown(f"- {warning}")

    name = _safe_name(project.title)
    pdf, docx, cover = storage.export_file(project, "pdf"), storage.export_file(project, "docx"), image_if_exists(project, "cover_final")
    c1, c2, c3, c4 = st.columns(4)
    c1.download_button(
        "📕 Download PDF", pdf.read_bytes() if pdf else b"", f"{name}.pdf", "application/pdf",
        disabled=pdf is None, width="stretch", key="dl_pdf",
    )
    c2.download_button(
        "📘 Download DOCX", docx.read_bytes() if docx else b"", f"{name}.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        disabled=docx is None, width="stretch", key="dl_docx",
    )
    c3.download_button(
        "🖼️ Download Cover PNG", cover.read_bytes() if cover else b"", f"{name}_cover.png", "image/png",
        disabled=cover is None, width="stretch", key="dl_cover",
    )
    c4.download_button(
        "📦 Download Project JSON", project.model_dump_json(indent=2).encode("utf-8"), f"{name}_project.json", "application/json",
        width="stretch", key="dl_json",
    )
    if not pdf:
        st.caption("Build the files first to enable the PDF and DOCX downloads.")
