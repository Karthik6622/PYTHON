"""Enterprise look and feel (static CSS and HTML only; no user text is ever injected)."""

from __future__ import annotations

import streamlit as st

from config import APP_ICON, APP_NAME, APP_TAGLINE

NAVY = "#1E1B4B"
INDIGO = "#4F46E5"
TEAL = "#0D9488"
AMBER = "#F59E0B"

_CSS = f"""
<style>
.block-container {{ padding-top: 1.4rem; max-width: 1240px; }}
.hero {{
    background: linear-gradient(120deg, {NAVY} 0%, #312E81 55%, {INDIGO} 100%);
    border-radius: 16px; padding: 28px 34px; margin-bottom: 18px; color: #fff;
    box-shadow: 0 8px 24px rgba(30, 27, 75, 0.22);
}}
.hero h1 {{ color: #fff; font-size: 2.1rem; margin: 0 0 6px 0; padding: 0; letter-spacing: -0.01em; }}
.hero p {{ color: #E0E7FF; font-size: 1.02rem; margin: 0; }}
.hero .badge {{
    display: inline-block; margin-top: 12px; margin-right: 8px; padding: 3px 12px; border-radius: 999px;
    background: rgba(255,255,255,0.14); color: #fff; font-size: 0.78rem; letter-spacing: .03em;
}}
.stTabs [data-baseweb="tab-list"] {{ gap: 6px; border-bottom: 1px solid #E2E5F1; }}
.stTabs [data-baseweb="tab"] {{
    padding: 10px 18px; border-radius: 10px 10px 0 0; font-weight: 600; color: #475569;
}}
.stTabs [aria-selected="true"] {{ color: {INDIGO}; background: #EEF0FF; }}
.stButton > button, .stDownloadButton > button, [data-testid="stFormSubmitButton"] > button {{
    border-radius: 10px; font-weight: 600; padding: .55rem 1.1rem;
}}
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {{
    background: {INDIGO}; border: none; color: #fff;
}}
.stButton > button[kind="primary"]:hover {{ background: #4338CA; }}
[data-testid="stMetric"] {{
    background: #FFFFFF; border: 1px solid #E2E5F1; border-radius: 12px; padding: 12px 16px;
    box-shadow: 0 1px 3px rgba(30, 27, 75, 0.06);
}}
[data-testid="stSidebar"] {{ background: #EEF0F8; }}
[data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {{ color: {NAVY}; }}
.pill {{
    display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: .78rem; font-weight: 600; margin-right: 6px;
}}
.pill-ok {{ background: #CCFBF1; color: #0F766E; }}
.pill-warn {{ background: #FEF3C7; color: #B45309; }}
.pill-bad {{ background: #FEE2E2; color: #B91C1C; }}
.pill-info {{ background: #E0E7FF; color: #3730A3; }}
.section-note {{ color: #64748B; font-size: .92rem; }}
.side-brand {{
    background: linear-gradient(135deg, {NAVY} 0%, #4F46E5 60%, #7C3AED 100%); color: #FFFFFF; border-radius: 16px;
    padding: 18px 18px 16px 18px; margin-bottom: 8px; box-shadow: 0 6px 16px rgba(79, 70, 229, 0.25);
}}
.side-brand .logo {{ font-size: 2rem; line-height: 1; }}
.side-brand .name {{ font-size: 1.3rem; font-weight: 800; margin: 6px 0 2px 0; letter-spacing: .2px; }}
.side-brand .tag {{ font-size: .85rem; opacity: .85; margin-bottom: 12px; }}
.side-brand .chip {{
    display: inline-block; background: rgba(255, 255, 255, 0.16); border-radius: 999px; padding: 2px 10px;
    font-size: .74rem; font-weight: 600; margin: 0 4px 4px 0;
}}
</style>
"""


def apply_styles() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def render_header() -> None:
    st.markdown(
        f"""
<div class="hero">
  <h1>{APP_ICON} {APP_NAME}</h1>
  <p>{APP_TAGLINE}</p>
  <span class="badge">Plan</span><span class="badge">Write</span><span class="badge">Review</span>
  <span class="badge">Illustrate</span><span class="badge">Export PDF &amp; DOCX</span>
</div>
""",
        unsafe_allow_html=True,
    )


def pill(text: str, kind: str = "info") -> str:
    """HTML for a status pill. ``text`` must be application-controlled, never user or model text."""
    return f'<span class="pill pill-{kind}">{text}</span>'
