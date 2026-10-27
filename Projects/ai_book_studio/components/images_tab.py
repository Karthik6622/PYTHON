"""Tab 4: cover and chapter illustrations (prompts written by Nemotron, pictures made by the image provider)."""

from __future__ import annotations

import streamlit as st

from components.state import bump_content, current_project, flash, guarded, image_if_exists, make_pipeline, refresh
from components.styles import pill
from config import get_image_settings
from models.book_models import IllustrationPlan
from services.image_prompt_service import choose_orientation
from utils.image_utils import ORIENTATIONS


def _report(entry: IllustrationPlan, success_message: str) -> None:
    if entry.status == "failed":
        flash(f"{entry.label}: image generation failed. {entry.warning}", "error")
    elif entry.status == "placeholder":
        flash(f"{entry.label}: a placeholder image was used. {entry.warning}", "warning")
    else:
        flash(success_message, "success")


def render() -> None:
    project = current_project()
    if project is None or project.plan is None:
        st.info("Create a book plan first.")
        return
    version = st.session_state["content_version"]
    settings = get_image_settings()
    st.subheader("Images")
    if settings.use_api:
        st.markdown(pill("Image API connected", "ok"), unsafe_allow_html=True)
    else:
        st.markdown(pill("Development placeholder images", "warn"), unsafe_allow_html=True)
        st.caption("No IMAGE_API_KEY is configured, so abstract placeholder art is used. Add the key to .streamlit/secrets.toml for real illustrations.")

    st.markdown("##### Front cover")
    cover_record = project.images.get("cover")
    left, right = st.columns([1, 2], gap="large")
    cover_file = image_if_exists(project, "cover_final")
    with left:
        if cover_file:
            st.image(str(cover_file), caption="Final cover (2:3)", width="stretch")
        else:
            st.info("No cover yet.")
    with right:
        prompt = st.text_area(
            "Cover artwork prompt",
            cover_record.prompt if cover_record else "",
            height=170,
            key=f"cover_prompt_{version}",
            help="Leave empty and Nemotron writes one. The title and author are added with real text, never by the AI image.",
        )
        a, b, c = st.columns(3)
        if a.button("🎨 Generate Cover", width="stretch", key="cover_generate"):
            _run("Generating the cover", lambda p: p.generate_cover(prompt=prompt.strip() or None), "The cover was created.")
        if b.button("✨ New Prompt and Cover", width="stretch", key="cover_new"):
            _run("Generating the cover", lambda p: p.generate_cover(new_prompt=True), "A new cover was created.")
        if c.button("🖋️ Update Cover Text", width="stretch", key="cover_text", disabled=not image_if_exists(project, "cover_art")):
            with guarded("Updating the cover"):
                make_pipeline(project).recompose_cover()
                flash("The cover text was refreshed from the current title and author.", "success")
                bump_content()
                refresh()
        if cover_record and cover_record.warning:
            st.warning(cover_record.warning)

    st.divider()
    st.markdown("##### Chapter illustrations")
    plan = project.plan
    numbers = [c.chapter_number for c in plan.chapters]
    number = st.selectbox(
        "Chapter",
        numbers,
        format_func=lambda n: f"Chapter {n}: {plan.chapter(n).title}" + ("" if plan.chapter(n).requires_image else "  (no illustration planned)"),
        key="images_selected",
    )
    chapter = plan.chapter(number)
    key = f"chapter_{number:02d}"
    record = project.images.get(key)
    default_orientation = (record.orientation if record else "") or choose_orientation(chapter, plan.book_type)
    left, right = st.columns([1, 2], gap="large")
    with left:
        file = image_if_exists(project, key)
        if file:
            st.image(str(file), caption=f"Chapter {number} ({record.orientation if record else ''})", width="stretch")
        else:
            st.info("No image yet.")
    with right:
        orientation = st.selectbox(
            "Orientation",
            ORIENTATIONS,
            index=ORIENTATIONS.index(default_orientation) if default_orientation in ORIENTATIONS else 2,
            key=f"orientation_{version}_{number}",
        )
        prompt = st.text_area(
            "Illustration prompt",
            record.prompt if record else "",
            height=150,
            key=f"chapter_prompt_{version}_{number}",
            help="Edit the prompt and press Generate to use your wording.",
        )
        a, b = st.columns(2)
        if a.button("🎨 Generate / Regenerate Image", width="stretch", key=f"img_gen_{number}"):
            _run(
                f"Generating the chapter {number} image",
                lambda p: p.generate_chapter_image(number, prompt=prompt.strip() or None, orientation=orientation),
                f"The chapter {number} image was created.",
            )
        if b.button("✨ New Prompt and Image", width="stretch", key=f"img_new_{number}"):
            _run(
                f"Generating the chapter {number} image",
                lambda p: p.generate_chapter_image(number, new_prompt=True, orientation=orientation),
                f"A new chapter {number} image was created.",
            )
        if record and record.warning:
            st.warning(record.warning)

    missing = [n for n in numbers if plan.chapter(n).requires_image and not image_if_exists(project, f"chapter_{n:02d}")]
    if missing:
        st.caption(f"Planned illustrations still missing: chapters {', '.join(map(str, missing))}. They are created automatically during book generation.")


def _run(action: str, call, success_message: str) -> None:
    project = current_project()
    with guarded(action):
        with st.spinner(f"{action}..."):
            entry = call(make_pipeline(project))
        _report(entry, success_message)
        bump_content()
        refresh()
