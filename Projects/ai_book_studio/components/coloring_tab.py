"""Coloring-book screens: the Create form, the page plan, the pages gallery and the export.

A coloring book has no chapters or text. Nemotron plans the cover and every page scene; the configured image model draws
them and Pillow turns each drawing into clean black-and-white line art. The sections reuse the eBook navigation keys:
``plan`` -> page plan, ``chapters`` -> Pages, ``export`` -> Export.
"""

from __future__ import annotations

import io
import time
from pathlib import Path

import streamlit as st
from PIL import Image
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from components.cover_text_editor import open_cover_text_editor, render_cover_text_editor
from components.progress_panel import controls, render_plan_live, stage_pill
from components.state import (
    bump_content,
    current_project,
    flash,
    get_storage,
    guarded,
    image_if_exists,
    job_for,
    job_running,
    make_pipeline,
    plan_job_here,
    plan_job_running_for,
    refresh,
    start_plan,
)
from components.export_tab import _cover_jpg_bytes, _safe_name
from config import (
    COLORING_AUDIENCES,
    COLORING_COMPLEXITIES,
    COLORING_EXTRA_PAGES,
    COLORING_LAYOUTS,
    COLORING_MAX_PAGES,
    COLORING_MIN_PAGES,
    COMPLEXITY_HELP,
    LAYOUT_PAGE_WITH_ICON,
    MAX_IDEA_CHARS,
    get_image_settings,
)
from components.styles import pill
from models.book_models import BookProject, IllustrationPlan
from services.coloring_book import line_key, page_key

_GALLERY_COLUMNS = 4
_GALLERY_PAGE_SIZE = 12


def _key(name: str, *parts: object) -> str:
    return "_".join([name, str(st.session_state["plan_version"]), *map(str, parts)])


@st.cache_data(show_spinner=False, max_entries=400)
def _thumbnail(path: str, modified: float, width: int = 360) -> bytes:
    """Small JPEG of a page, so a gallery of full-size pages does not have to be sent to the browser."""
    with Image.open(path) as image:
        image = image.convert("RGB")
        image.thumbnail((width, width * 2))
        buffer = io.BytesIO()
        image.save(buffer, "JPEG", quality=85)
    return buffer.getvalue()


def _show(path: Path, caption: str = "", width: int = 360) -> None:
    st.image(_thumbnail(str(path), path.stat().st_mtime, width), caption=caption, width="stretch")


def _cover_pdf_bytes(path: Path | None, title: str) -> bytes:
    """The front cover alone as a one-page US Letter PDF."""
    if not path:
        return b""
    buffer = io.BytesIO()
    width, height = letter
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setTitle(f"{title} - Cover")
    pdf.drawImage(ImageReader(str(path)), 0, 0, width=width, height=height)
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def _report(entry: IllustrationPlan, success_message: str) -> None:
    if entry.status == "failed":
        flash(f"{entry.label}: drawing failed. {entry.warning}", "error")
    elif entry.status == "placeholder":
        flash(f"{entry.label}: a drawn pattern was used instead. {entry.warning}", "warning")
    else:
        flash(success_message, "success")


def _run(action: str, call, success_message: str) -> None:
    project = current_project()
    with guarded(action):
        with st.spinner(f"{action}... (this can take a minute)"):
            entry = call(make_pipeline(project))
        _report(entry, success_message)
        bump_content()
        refresh()


def _page_state(project: BookProject, number: int) -> str:
    job = job_for(project)
    if job and job.running:
        phase = job.phase_of(number)
        if phase == "illustrating":
            return "🎨 Drawing"
    record = project.images.get(line_key(number))
    if not image_if_exists(project, line_key(number)):
        return "⏳ Waiting" if job and job.running else "Not drawn"
    if record and record.status == "placeholder":
        return "⚠️ Pattern used (regenerate)"
    return "✅ Done"


def drawn_count(project: BookProject) -> int:
    return sum(1 for n in project.chapter_numbers if image_if_exists(project, line_key(n)))


# --------------------------------------------------------------------------------------
# Create form
# --------------------------------------------------------------------------------------
def render_form() -> bool:
    """The simplified Create form. Returns True when the 'create plan' button was pressed."""
    st.markdown(
        '<p class="section-note">Describe what the pictures should show. The app designs a cover and one unique page per '
        "picture, with no text on the pages.</p>",
        unsafe_allow_html=True,
    )
    left, right = st.columns([3, 2], gap="large")
    with left:
        st.text_area(
            "Coloring book theme *",
            key="in_idea",
            height=150,
            max_chars=MAX_IDEA_CHARS,
            placeholder="Example: Friendly dinosaurs exploring a magical jungle, with waterfalls, flowers and baby animals.",
        )
        st.text_input("Book title (optional)", key="in_title", max_chars=150, help="Leave empty to let the AI suggest a title.")
        st.text_input("Author name (optional)", key="in_author", max_chars=100, help="Printed on the cover.")
    with right:
        st.selectbox("Who is it for?", COLORING_AUDIENCES, key="in_coloring_audience", help="Children get bold simple shapes; adults get finer detail.")
        st.number_input(
            "Number of coloring pages",
            min_value=COLORING_MIN_PAGES,
            max_value=COLORING_MAX_PAGES,
            step=2,
            key="in_coloring_pages",
            help="Pages inside the book. The cover is extra.",
        )
        st.radio(
            "Complexity",
            list(COLORING_COMPLEXITIES),
            format_func=COLORING_COMPLEXITIES.get,
            key="in_coloring_complexity",
            horizontal=True,
            help=COMPLEXITY_HELP,
        )
        st.radio(
            "Page style",
            list(COLORING_LAYOUTS),
            format_func=COLORING_LAYOUTS.get,
            key="in_coloring_layout",
            horizontal=True,
            help="The small colored picture (top-left corner) shows how the finished page can look.",
        )
    st.markdown("**Extra pages before the pictures**")
    for column, (name, label) in zip(st.columns(len(COLORING_EXTRA_PAGES)), COLORING_EXTRA_PAGES.items()):
        with column:
            st.radio(label, [False, True], format_func=lambda on: "Yes" if on else "No", key=f"in_extra_{name}", horizontal=True)
            if name == "copyright_page":
                st.text_input(
                    "Copyright name",
                    key="in_coloring_copyright",
                    max_chars=100,
                    placeholder="Name to print",
                    help="Printed on the copyright page and on every other extra page that shows a name. Empty = the author name.",
                )
    settings = get_image_settings()
    if settings.configured:
        st.markdown(pill(f"Pictures drawn by {settings.provider_label}", "ok"), unsafe_allow_html=True)
    else:
        st.markdown(pill("No image provider set up: simple drawn patterns will be used", "warn"), unsafe_allow_html=True)
    plan_running = plan_job_here()
    busy = plan_running is not None and plan_running.running
    return st.button("✨ Create Coloring Book Plan", type="primary", width="stretch", disabled=busy)


# --------------------------------------------------------------------------------------
# Plan
# --------------------------------------------------------------------------------------
def render_plan() -> None:
    project = current_project()
    job = plan_job_here()
    if job is not None and (job.running or not job.handled):
        st.subheader("Coloring book plan")
        render_plan_live(job)
        return
    if project is None or project.plan is None:
        st.info("Create a coloring book plan on the **Create** tab first.")
        return
    plan = project.plan
    locked = job_running(project) or plan_job_running_for(project)
    started = drawn_count(project) > 0

    st.subheader("Coloring book plan")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Coloring pages", len(plan.chapters))
    m2.metric("Audience", project.book_input.audience)
    m3.metric("Complexity", COLORING_COMPLEXITIES.get(project.book_input.coloring_complexity, "Medium"))
    m4.metric("Page style", "With preview" if project.book_input.coloring_layout == LAYOUT_PAGE_WITH_ICON else "Page only")
    if started:
        st.warning("Pages are already drawn. Changed scenes are drawn again only when you redraw that page on the Pages tab.")

    st.text_input("Title", plan.title, key=_key("p_title"), max_chars=200)
    st.text_input("Subtitle", plan.subtitle, key=_key("p_subtitle"), max_chars=250)
    st.text_area("Cover scene", plan.cover_concept, key=_key("p_cover"), height=90, help="What the front cover shows. No text is drawn by the AI; the title is added as real text.")
    st.radio(
        "Page style",
        list(COLORING_LAYOUTS),
        index=list(COLORING_LAYOUTS).index(project.book_input.coloring_layout),
        format_func=COLORING_LAYOUTS.get,
        key=_key("p_layout"),
        horizontal=True,
        disabled=started,
        help="Fixed once pages are drawn. Start a new plan to change it.",
    )

    st.markdown("##### Pages")
    for chapter in plan.chapters:
        n = chapter.chapter_number
        with st.expander(f"Page {n}: {chapter.title}", expanded=False):
            st.text_input("Page name", chapter.title, key=_key("ct", n), max_chars=120)
            st.text_area("What the page shows", chapter.image_concept, key=_key("cc", n), height=80)

    save_col, regen_col = st.columns(2)
    if save_col.button("💾 Save Plan Changes", width="stretch", disabled=locked):
        _save_plan(project)
    with regen_col:
        confirmed = True
        if started:
            confirmed = st.checkbox("Discard the drawn pages when making a new plan", key="plan_regen_confirm")
        if st.button("🔄 Regenerate Plan", width="stretch", disabled=not confirmed or locked):
            storage = get_storage()
            with guarded("Regenerating the plan"):
                if project.images:
                    storage.clear_generated(project)
                if start_plan(project):
                    st.rerun()

    st.divider()
    st.markdown("##### Draw the coloring book")
    st.markdown(
        '<p class="section-note">Every page is drawn as clean black-and-white line art, then the cover and the PDF are built. '
        "It runs in the background and progress is saved after every page. The Pages tab opens with live status.</p>",
        unsafe_allow_html=True,
    )
    if job_running(project):
        st.info("Drawing is running. Watch it live on the Pages tab.")
        return
    controls(project, "plan")


def _save_plan(project: BookProject) -> None:
    state = st.session_state
    edited = project.plan.model_copy(deep=True)
    edited.title = state[_key("p_title")].strip()
    edited.subtitle = state[_key("p_subtitle")].strip()
    edited.cover_concept = state[_key("p_cover")].strip()
    problems = []
    if not edited.title:
        problems.append("The title cannot be empty.")
    for chapter in edited.chapters:
        n = chapter.chapter_number
        chapter.title = state[_key("ct", n)].strip()
        chapter.image_concept = state[_key("cc", n)].strip()
        chapter.summary = chapter.image_concept
        if not chapter.title or not chapter.image_concept:
            problems.append(f"Page {n} needs a name and a description of what it shows.")
    if problems:
        for problem in problems:
            st.error(problem)
        return
    project.plan = edited
    project.book_input.coloring_layout = state[_key("p_layout")]
    storage = get_storage()
    with guarded("Saving the plan"):
        storage.save_plan(project)
        storage.save_project_meta(project)
        flash("Plan saved.", "success")
        refresh()


# --------------------------------------------------------------------------------------
# Pages (live status, gallery, cover, per-page redraw)
# --------------------------------------------------------------------------------------
def _live_body() -> None:
    project = current_project()
    if project is None or project.plan is None:
        return
    job = job_for(project)
    running = bool(job and job.running)
    numbers = project.chapter_numbers
    drawn = drawn_count(project)
    patterns = sum(1 for n in numbers if (r := project.images.get(line_key(n))) and r.status == "placeholder")

    st.markdown(stage_pill(project), unsafe_allow_html=True)
    fraction = job.fraction if running and job else project.status.progress
    message = (job.message if running and job else project.status.message) or "Waiting to start"
    st.progress(min(max(fraction, 0.0), 1.0), text=f"{message}  ({fraction * 100:.0f}%)")
    if running and job:
        minutes, seconds = divmod(job.elapsed_seconds, 60)
        st.caption(f"Running for {minutes:02d}:{seconds:02d}. You can switch tabs or leave this page open; drawing continues in the background.")

    a, b, c = st.columns(3)
    a.metric("Pages drawn", f"{drawn} / {len(numbers)}")
    b.metric("Cover", "Ready" if image_if_exists(project, "cover_final") else "Pending")
    c.metric("Drawn patterns used", patterns, help="Pages where the image model failed and a simple pattern was used. Redraw them below.")

    controls(project, "live")

    if running:
        rows = [{"Page": n, "Name": project.plan.chapter(n).title, "Status": _page_state(project, n)} for n in numbers]
        st.dataframe(rows, hide_index=True, width="stretch", height=min(38 * (len(rows) + 1), 420))
        recent = [n for n in numbers if image_if_exists(project, page_key(n))][-4:]
        if recent:
            st.caption("Latest pages")
            for column, n in zip(st.columns(len(recent)), recent):
                with column:
                    _show(get_storage().image_path(project, page_key(n)), f"Page {n}", 260)
        with st.expander("Activity log", expanded=False):
            st.code("\n".join(reversed(job.log_lines())) or "Starting...", language=None)
    elif job is not None and not getattr(job, "handled", True):
        st.rerun()  # the job just finished: refresh the whole page once


def render_pages() -> None:
    project = current_project()
    if project is None or project.plan is None:
        st.info("Create a coloring book plan first.")
        return
    st.subheader("Coloring pages")
    interval = 2 if job_running(project) else None
    st.fragment(run_every=interval)(_live_body)()
    if job_running(project):
        return
    storage = get_storage()
    version = st.session_state["content_version"]
    plan = project.plan

    st.markdown("##### Front cover")
    cover_file = image_if_exists(project, "cover_final")
    left, right = st.columns([1, 2], gap="large")
    with left:
        if cover_file:
            _show(cover_file, "Front cover", 420)
        else:
            st.info("No cover yet. It is created when the book is generated, or press the button.")
    with right:
        record = project.images.get("cover")
        st.caption("The cover is a colored illustration with the title and author added as real text.")
        a, b = st.columns(2)
        if a.button("🎨 Draw a New Cover", width="stretch", key="cover_new"):
            _run("Drawing the cover", lambda p: p.generate_cover(new_prompt=True), "A new cover was created.")
        if b.button(
            "🖋️ Update Cover Text",
            width="stretch",
            key="cover_text",
            disabled=not image_if_exists(project, "cover_art"),
            help="Edit the title, subtitle and author printed on the front cover.",
        ):
            open_cover_text_editor(project)
        render_cover_text_editor(project, version)
        if record and record.warning:
            st.warning(record.warning)

    st.divider()
    numbers = [c.chapter_number for c in plan.chapters]
    drawn = [n for n in numbers if image_if_exists(project, page_key(n))]
    st.markdown(f"##### Pages ({len(drawn)} of {len(numbers)} drawn)")
    if not drawn:
        st.caption("No pages yet. Generate the book from the Plan tab.")
        return

    pages = max(1, -(-len(numbers) // _GALLERY_PAGE_SIZE))
    group = 1
    if pages > 1:
        group = st.select_slider("Gallery page", options=list(range(1, pages + 1)), key="cg_group")
    shown = numbers[(group - 1) * _GALLERY_PAGE_SIZE : group * _GALLERY_PAGE_SIZE]
    for row_start in range(0, len(shown), _GALLERY_COLUMNS):
        for column, n in zip(st.columns(_GALLERY_COLUMNS), shown[row_start : row_start + _GALLERY_COLUMNS]):
            with column:
                path = storage.image_path(project, page_key(n))
                if n in drawn:
                    _show(path, f"{n}. {plan.chapter(n).title}")
                else:
                    st.info(f"{n}. {plan.chapter(n).title}: not drawn")

    st.divider()
    st.markdown("##### Edit one page")
    number = st.selectbox(
        "Page",
        numbers,
        format_func=lambda n: f"Page {n}: {plan.chapter(n).title}",
        key="cp_selected",
    )
    chapter = plan.chapter(number)
    record = project.images.get(line_key(number))
    left, right = st.columns([1, 2], gap="large")
    with left:
        file = image_if_exists(project, page_key(number))
        if file:
            _show(file, f"Page {number}", 420)
        else:
            st.info("This page is not drawn yet.")
    with right:
        scene = st.text_area(
            "What the page shows",
            chapter.image_concept,
            height=110,
            key=f"cp_scene_{version}_{number}",
            help="Change the scene, then press Redraw.",
        )
        if st.button("🎨 Redraw This Page", width="stretch", key=f"cp_redraw_{number}"):
            _redraw(project, number, scene.strip(), new_prompt=True)
        if record and record.warning:
            st.warning(record.warning)


def _redraw(project: BookProject, number: int, scene: str, new_prompt: bool) -> None:
    if not scene:
        st.error("Describe what the page should show first.")
        return
    chapter = project.plan.chapter(number)
    if scene != chapter.image_concept:
        chapter.image_concept = scene
        chapter.summary = scene
        get_storage().save_plan(project)
    _run(
        f"Drawing page {number}",
        lambda p: p.generate_chapter_image(number, new_prompt=new_prompt),
        f"Page {number} was drawn again.",
    )


# --------------------------------------------------------------------------------------
# Export
# --------------------------------------------------------------------------------------
def render_export() -> None:
    project = current_project()
    if project is None or project.plan is None:
        st.info("Create a coloring book plan first.")
        return
    if job_running(project):
        st.info("The coloring book is still being drawn. The PDF and DOCX are built automatically at the end; see the Pages tab.")
        return
    storage = get_storage()
    st.subheader("Export")

    missing = [n for n in project.chapter_numbers if not image_if_exists(project, line_key(n))]
    if missing:
        st.warning("These pages are not drawn yet: " + ", ".join(map(str, missing)) + ". Generate or continue the book first.")
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
            flash(f"The files were built. The PDF has {summary.pages} pages including the cover.", "success")
            refresh()

    summary = st.session_state.get("export_summary")
    warnings = summary.warnings if summary else project.status.warnings
    if summary:
        st.success(f"PDF and DOCX: {summary.pages} pages (cover + {len(project.chapter_numbers)} coloring pages).")
    if warnings:
        with st.expander(f"Warnings ({len(warnings)})", expanded=True):
            for warning in warnings:
                st.markdown(f"- {warning}")

    name = _safe_name(project.title)
    pdf, docx, cover = storage.export_file(project, "pdf"), storage.export_file(project, "docx"), image_if_exists(project, "cover_final")
    docx_plain, archive = storage.export_file(project, "no_cover.docx"), storage.export_file(project, "zip")
    word = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    c1, c2, c3 = st.columns(3)
    c1.download_button(
        "📕 Download PDF", pdf.read_bytes() if pdf else b"", f"{name}.pdf", "application/pdf",
        disabled=pdf is None, width="stretch", key="dl_pdf",
    )
    c2.download_button(
        "📘 Download DOCX", docx.read_bytes() if docx else b"", f"{name}.docx", word,
        disabled=docx is None, width="stretch", key="dl_docx",
    )
    c3.download_button(
        "📗 Download DOCX without cover", docx_plain.read_bytes() if docx_plain else b"", f"{name}_no_cover.docx", word,
        disabled=docx_plain is None, width="stretch", key="dl_docx_no_cover",
    )
    c4, c5, c6 = st.columns(3)
    c4.download_button(
        "🖼️ Download Cover JPG", _cover_jpg_bytes(cover), f"{name}_cover.jpg", "image/jpeg",
        disabled=cover is None, width="stretch", key="dl_cover",
    )
    c5.download_button(
        "📄 Download Cover PDF", _cover_pdf_bytes(cover, project.title), f"{name}_cover.pdf", "application/pdf",
        disabled=cover is None, width="stretch", key="dl_cover_pdf",
    )
    c6.download_button(
        "🗂️ Download Page Images (ZIP)", archive.read_bytes() if archive else b"", f"{name}_pages.zip", "application/zip",
        disabled=archive is None, width="stretch", key="dl_zip",
    )
    st.download_button(
        "📦 Download Project JSON", project.model_dump_json(indent=2).encode("utf-8"), f"{name}_project.json", "application/json",
        width="stretch", key="dl_json",
    )
    if not pdf:
        st.caption("Build the files first to enable the PDF and DOCX downloads.")
    elif not docx_plain:
        st.caption("Click \"Build PDF and DOCX\" again to create the DOCX without the cover.")
