"""RK Studio: a repository-aware AI coding IDE built with Streamlit.

Run with:  streamlit run app.py
"""

import streamlit as st

try:  # same switch as [global] minCachedMessageSize in .streamlit/config.toml, for hosts that do not read that file
    from streamlit import config as _config

    _config.set_option("global.minCachedMessageSize", 1e12)
except Exception:
    pass

st.set_page_config(page_title="RK Studio", page_icon=":material/terminal:", layout="wide", initial_sidebar_state="collapsed")

from ui.agent_panel import render_agent_panel  # noqa: E402  (set_page_config must be the first Streamlit call)
from ui.bottom import render_bottom  # noqa: E402
from ui.editor import render_editor  # noqa: E402
from ui.explorer import render_explorer, render_search  # noqa: E402
from ui.layout import install_layout  # noqa: E402
from ui.local_folder import render_local_folder  # noqa: E402
from ui.source_control import render_source_control  # noqa: E402
from ui.state import init_state  # noqa: E402
from ui.statusbar import render_status_bar  # noqa: E402
from ui.theme import inject_theme  # noqa: E402
from ui.topbar import render_top_bar  # noqa: E402

SIDE_PANELS = [
    ("Explorer", ":material/folder_open:", "Explorer"),
    ("Search", ":material/search:", "Search"),
    ("Source Control", ":material/account_tree:", "Source Control"),
]


def _pick(panel: str) -> None:
    st.session_state["side"] = panel


def _activity_bar() -> None:
    current = st.session_state.get("side") or "Explorer"
    with st.container(key="activity"):
        for panel, icon, tip in SIDE_PANELS:
            st.button("", icon=icon, help=tip, key=f"act_{panel}", type="primary" if panel == current else "tertiary", on_click=_pick, args=(panel,))


def main() -> None:
    init_state()
    inject_theme()
    render_top_bar()

    with st.container(key="shell"):
        activity, side, centre, agent = st.columns([1, 1, 1, 1], gap="small")
        with activity:
            _activity_bar()
        with side:
            with st.container(key="sidebar"):
                panel = st.session_state.get("side") or "Explorer"
                st.session_state["_local_visible"] = panel == "Explorer"
                render_local_folder()  # always mounted: it also writes changes back to the user's folder
                if panel == "Search":
                    render_search()
                elif panel == "Source Control":
                    render_source_control()
                else:
                    render_explorer()
        with centre:
            with st.container(key="centre"):
                render_editor()
                with st.container(key="bottompanel"):
                    render_bottom()
        with agent:
            with st.container(key="agent"):
                render_agent_panel()

    render_status_bar()
    install_layout()


main()
