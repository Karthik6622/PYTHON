"""AI Book Studio: turn an idea into a planned, written, reviewed, illustrated and exported book."""

from __future__ import annotations

import streamlit as st
from dotenv import load_dotenv

from config import APP_ICON, APP_NAME, ROOT_DIR, get_image_settings, get_nvidia_settings

st.set_page_config(page_title=APP_NAME, page_icon=APP_ICON, layout="wide", initial_sidebar_state="expanded")
load_dotenv(ROOT_DIR / ".env")

from components import chapters_tab, create_tab, export_tab, images_tab, plan_tab, preview_tab  # noqa: E402
from components.state import (  # noqa: E402
    current_project,
    delete_project,
    get_storage,
    init_state,
    new_book,
    open_project,
    render_flash,
    setup_logging,
    sync_mirrors,
)
from components.styles import apply_styles, pill, render_header  # noqa: E402

_STAGE_PILLS = {
    "new": ("Not started", "info"),
    "planned": ("Plan ready", "info"),
    "running": ("Running / paused", "warn"),
    "failed": ("Stopped - resume available", "bad"),
    "completed": ("Completed", "ok"),
}


def render_sidebar() -> None:
    project = current_project()
    storage = get_storage()
    with st.sidebar:
        st.markdown(f"## {APP_ICON} {APP_NAME}")
        nvidia, image = get_nvidia_settings(), get_image_settings()
        st.markdown(
            pill("NVIDIA key found", "ok") if nvidia.configured else pill("NVIDIA key missing", "bad"),
            unsafe_allow_html=True,
        )
        st.caption(f"Text model: {nvidia.model}")
        st.markdown(
            pill("Image API configured", "ok") if image.use_api else pill("Placeholder images", "warn"),
            unsafe_allow_html=True,
        )
        if not nvidia.configured:
            st.warning("Add NVIDIA_API_KEY to .streamlit/secrets.toml or .env to generate text.")

        st.divider()
        st.markdown("### Generation status")
        if project is None:
            st.caption("No book open.")
        else:
            text, kind = _STAGE_PILLS.get(project.status.stage, ("Unknown", "info"))
            st.markdown(pill(text, kind), unsafe_allow_html=True)
            st.progress(min(max(project.status.progress, 0.0), 1.0))
            if project.status.message:
                st.caption(project.status.message)
            if project.status.total_chapters:
                st.caption(f"Chapters complete: {len(project.status.completed_chapters)} / {project.status.total_chapters}")
            if project.status.error:
                st.error(project.status.error)
            if project.status.stage in {"running", "failed"}:
                st.caption("Open the Plan tab and press **Resume Generation** to continue.")

        st.divider()
        st.markdown("### Saved projects")
        saved = storage.list_projects()
        ids = [item["id"] for item in saved]
        if st.session_state.get("sb_open") not in ids:
            st.session_state.pop("sb_open", None)
        if saved:
            labels = {item["id"]: f"{item['title']} · {item['stage']} · {item['updated_at'][:10]}" for item in saved}
            selected = st.selectbox("Open a saved project", ids, format_func=lambda i: labels[i], key="sb_open")
            st.button("📂 Open selected project", on_click=open_project, args=(selected,), width="stretch")
        else:
            st.caption("Saved books appear here.")
        st.button("🆕 New book", on_click=new_book, width="stretch")

        if project is not None:
            with st.expander("Danger zone"):
                confirm = st.checkbox("I want to delete this saved project", key="sb_confirm_delete")
                st.button(
                    "🗑️ Delete saved project",
                    on_click=delete_project,
                    args=(project.project_id,),
                    disabled=not confirm,
                    width="stretch",
                )


def main() -> None:
    setup_logging()
    init_state()
    apply_styles()
    sync_mirrors(current_project())
    render_sidebar()
    render_header()
    render_flash()

    tabs = st.tabs(["✍️ Create", "🗺️ Plan", "📖 Chapters", "🖼️ Images", "👁️ Preview", "📤 Export"])
    for tab, module in zip(tabs, (create_tab, plan_tab, chapters_tab, images_tab, preview_tab, export_tab)):
        with tab:
            module.render()


main()
