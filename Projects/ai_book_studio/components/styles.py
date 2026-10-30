"""Futuristic neon look and feel (static CSS and HTML only; no user text is ever injected)."""

from __future__ import annotations

import streamlit as st

from config import APP_ICON, APP_NAME, APP_TAGLINE

# Futuristic cyberpunk palette: deep space background with neon accents.
BG_DEEP = "#05050A"      # near-black space background
BG_PANEL = "#0A0A12"     # slightly lighter panel
BG_CARD = "#0F0F1A"      # card surface
NEON_CYAN = "#00F3FF"    # primary neon accent
NEON_MAGENTA = "#BC13FE" # secondary neon accent
NEON_PURPLE = "#8B5CF6"  # tertiary neon accent
NEON_GREEN = "#22FF88"   # success / ok neon
NEON_AMBER = "#FFB800"   # warning neon
NEON_RED = "#FF3366"     # error / bad neon
TEXT_BRIGHT = "#FFFFFF"
TEXT_MUTED = "#9AA5B1"

_CSS = f"""
<style>
/* Base app background */
.stApp {{
    background: {BG_DEEP};
    color: {TEXT_BRIGHT};
}}
.block-container {{
    padding-top: 1.4rem;
    max-width: 1240px;
    background: transparent;
}}
/* Hide Streamlit chrome that clashes with the dark theme */
header, footer {{ visibility: hidden; }}

/* Hero banner with neon gradient */
.hero {{
    background: linear-gradient(120deg, {BG_PANEL} 0%, #161625 55%, {NEON_CYAN}22 100%);
    border: 1px solid {NEON_CYAN}33;
    border-radius: 16px;
    padding: 28px 34px;
    margin-bottom: 18px;
    color: {TEXT_BRIGHT};
    box-shadow: 0 0 30px {NEON_CYAN}22, 0 8px 24px rgba(5, 5, 10, 0.6);
    position: relative;
    overflow: hidden;
}}
.hero::before {{
    content: "";
    position: absolute;
    top: -50%; left: -50%;
    width: 200%; height: 200%;
    background: radial-gradient(circle at 20% 30%, {NEON_CYAN}1a 0%, transparent 45%),
                radial-gradient(circle at 80% 70%, {NEON_MAGENTA}1a 0%, transparent 45%);
    pointer-events: none;
    z-index: 0;
}}
.hero > * {{ position: relative; z-index: 1; }}
.hero h1 {{
    color: {TEXT_BRIGHT};
    font-size: 2.1rem;
    margin: 0 0 6px 0;
    padding: 0;
    letter-spacing: -0.01em;
    text-shadow: 0 0 14px {NEON_CYAN}66;
}}
.hero p {{
    color: {TEXT_MUTED};
    font-size: 1.02rem;
    margin: 0;
}}
.hero .badge {{
    display: inline-block;
    margin-top: 12px;
    margin-right: 8px;
    padding: 3px 12px;
    border-radius: 999px;
    background: rgba(0, 243, 255, 0.12);
    color: {NEON_CYAN};
    font-size: 0.78rem;
    letter-spacing: .03em;
    border: 1px solid {NEON_CYAN}44;
    box-shadow: 0 0 10px {NEON_CYAN}44;
}}

/* Tabs - futuristic pill style */
.stTabs [data-baseweb="tab-list"] {{
    gap: 6px;
    border-bottom: 1px solid {NEON_CYAN}22;
}}
.stTabs [data-baseweb="tab"] {{
    padding: 10px 18px;
    border-radius: 10px 10px 0 0;
    font-weight: 600;
    color: {TEXT_MUTED};
    background: {BG_PANEL};
    border: 1px solid transparent;
    border-bottom: none;
}}
.stTabs [data-baseweb="tab"]:hover {{
    color: {NEON_CYAN};
    background: {BG_CARD};
    border-color: {NEON_CYAN}33;
}}
.stTabs [aria-selected="true"] {{
    color: {NEON_CYAN};
    background: {BG_CARD};
    border: 1px solid {NEON_CYAN};
    border-bottom: 1px solid {BG_CARD};
    box-shadow: 0 0 15px {NEON_CYAN}33;
}}

/* Buttons */
.stButton > button, .stDownloadButton > button, [data-testid="stFormSubmitButton"] > button {{
    border-radius: 10px;
    font-weight: 600;
    padding: .55rem 1.1rem;
    background: {BG_PANEL};
    color: {TEXT_BRIGHT};
    border: 1px solid {NEON_CYAN}44;
    box-shadow: 0 0 12px {NEON_CYAN}22;
}}
.stButton > button:hover, .stDownloadButton > button:hover {{
    border-color: {NEON_CYAN};
    box-shadow: 0 0 20px {NEON_CYAN}44;
    color: {NEON_CYAN};
}}
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {{
    background: {NEON_CYAN};
    border: none;
    color: {BG_DEEP};
    box-shadow: 0 0 20px {NEON_CYAN}66;
}}
.stButton > button[kind="primary"]:hover {{
    background: #40FBFF;
    box-shadow: 0 0 30px {NEON_CYAN}88;
    color: {BG_DEEP};
}}

/* Metrics */
[data-testid="stMetric"] {{
    background: {BG_CARD};
    border: 1px solid {NEON_CYAN}22;
    border-radius: 12px;
    padding: 12px 16px;
    box-shadow: 0 0 15px {NEON_CYAN}11;
    color: {TEXT_BRIGHT};
}}
[data-testid="stMetric"] label {{ color: {TEXT_MUTED}; }}
[data-testid="stMetric"] [data-testid="stMetricValue"] {{ color: {NEON_CYAN}; }}

/* Sidebar */
[data-testid="stSidebar"] {{
    background: {BG_PANEL};
    border-right: 1px solid {NEON_CYAN}22;
}}
[data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {{ color: {NEON_CYAN}; }}
[data-testid="stSidebar"] p, [data-testid="stSidebar"] label, [data-testid="stSidebar"] .stCaption {{ color: {TEXT_MUTED}; }}

/* Pills / status chips */
.pill {{
    display: inline-block;
    padding: 2px 10px;
    border-radius: 999px;
    font-size: .78rem;
    font-weight: 600;
    margin-right: 6px;
    border: 1px solid;
}}
.pill-ok {{ background: {NEON_GREEN}11; color: {NEON_GREEN}; border-color: {NEON_GREEN}44; box-shadow: 0 0 10px {NEON_GREEN}33; }}
.pill-warn {{ background: {NEON_AMBER}11; color: {NEON_AMBER}; border-color: {NEON_AMBER}44; box-shadow: 0 0 10px {NEON_AMBER}33; }}
.pill-bad {{ background: {NEON_RED}11; color: {NEON_RED}; border-color: {NEON_RED}44; box-shadow: 0 0 10px {NEON_RED}33; }}
.pill-info {{ background: {NEON_CYAN}11; color: {NEON_CYAN}; border-color: {NEON_CYAN}44; box-shadow: 0 0 10px {NEON_CYAN}33; }}

.section-note {{ color: {TEXT_MUTED}; font-size: .92rem; }}

/* Sidebar brand card */
.side-brand {{
    background: linear-gradient(135deg, {BG_PANEL} 0%, #161625 60%, {NEON_PURPLE}11 100%);
    color: {TEXT_BRIGHT};
    border: 1px solid {NEON_CYAN}33;
    border-radius: 16px;
    padding: 18px 18px 16px 18px;
    margin-bottom: 8px;
    box-shadow: 0 0 25px {NEON_CYAN}1a, 0 6px 16px rgba(5, 5, 10, 0.6);
}}
.side-brand .logo {{ font-size: 2rem; line-height: 1; }}
.side-brand .name {{ font-size: 1.3rem; font-weight: 800; margin: 6px 0 2px 0; letter-spacing: .2px; text-shadow: 0 0 10px {NEON_CYAN}44; }}
.side-brand .tag {{ font-size: .85rem; opacity: .85; margin-bottom: 12px; color: {TEXT_MUTED}; }}
.side-brand .chip {{
    display: inline-block;
    background: rgba(0, 243, 255, 0.12);
    border: 1px solid {NEON_CYAN}44;
    border-radius: 999px;
    padding: 2px 10px;
    font-size: .74rem;
    font-weight: 600;
    margin: 0 4px 4px 0;
    color: {NEON_CYAN};
    box-shadow: 0 0 8px {NEON_CYAN}33;
}}

/* Inputs and selects - dark with neon border */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea,
.stSelectbox > div > div > div,
.stNumberInput > div > div > input,
.stMultiSelect > div > div {{
    background: {BG_CARD} !important;
    color: {TEXT_BRIGHT} !important;
    border: 1px solid {NEON_CYAN}33 !important;
    border-radius: 8px !important;
}}
.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus,
.stSelectbox > div > div > div:focus {{
    border-color: {NEON_CYAN} !important;
    box-shadow: 0 0 12px {NEON_CYAN}44 !important;
}}

/* Expanders */
.streamlit-expanderHeader {{
    background: {BG_CARD};
    border: 1px solid {NEON_CYAN}22;
    border-radius: 8px;
    color: {TEXT_BRIGHT};
}}
.streamlit-expanderContent {{
    background: {BG_PANEL};
    border: 1px solid {NEON_CYAN}22;
    border-top: none;
    border-radius: 0 0 8px 8px;
}}

/* Dividers */
hr, .stDivider {{ border-color: {NEON_CYAN}22; }}

/* Dataframes */
.stDataFrame {{ border: 1px solid {NEON_CYAN}22; }}

/* Success / info / error banners */
.stAlert {{
    background: {BG_CARD};
    border: 1px solid {NEON_CYAN}33;
    border-radius: 8px;
    color: {TEXT_BRIGHT};
}}
.stAlert > div {{ color: {TEXT_BRIGHT}; }}
.stSuccess {{ border-color: {NEON_GREEN}44; }}
.stWarning {{ border-color: {NEON_AMBER}44; }}
.stError {{ border-color: {NEON_RED}44; }}
.stInfo {{ border-color: {NEON_CYAN}44; }}
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