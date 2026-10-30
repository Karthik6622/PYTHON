"""Nemotron AI Code Studio: a repository-aware AI coding IDE built with Streamlit.

Run with:  streamlit run app.py
"""

import streamlit as st

st.set_page_config(page_title="Nemotron AI Code Studio", page_icon=":material/terminal:", layout="wide", initial_sidebar_state="collapsed")

from ui.agent_panel import render_agent_panel  # noqa: E402  (set_page_config must be the first Streamlit call)
from ui.bottom import render_bottom  # noqa: E402
from ui.dialogs import connect_dialog  # noqa: E402
from ui.editor import render_editor  # noqa: E402
from ui.explorer import render_explorer, render_search  # noqa: E402
from ui.source_control import render_source_control  # noqa: E402
from ui.state import init_state, repo  # noqa: E402
from ui.topbar import render_top_bar  # noqa: E402

CSS = """
<style>
  .block-container { padding-top: 1.2rem; padding-bottom: 0.5rem; max-width: 100%; }
  [data-testid="stHeader"] { background: transparent; }
  div[data-testid="stExpander"] details summary { padding: 0.25rem 0.5rem; }
  .stButton > button { text-align: left; justify-content: flex-start; }
</style>
"""

SIDE_PANELS = ["Explorer", "Search", "Source Control"]


def main() -> None:
    init_state()
    st.markdown(CSS, unsafe_allow_html=True)
    render_top_bar()

    if repo() is None and not st.session_state.get("connect_prompted"):
        st.session_state["connect_prompted"] = True
        connect_dialog()

    left, centre, right = st.columns([1.5, 4.2, 2.6], gap="small")
    with left:
        st.segmented_control("Side panel", SIDE_PANELS, key="side", label_visibility="collapsed", width="stretch")
        with st.container(height=760, border=True):
            panel = st.session_state.get("side") or "Explorer"
            if panel == "Search":
                render_search()
            elif panel == "Source Control":
                render_source_control()
            else:
                render_explorer()
    with centre:
        render_editor()
        render_bottom()
    with right:
        render_agent_panel()


main()
