"""Ember Forge look and feel: a futuristic dark interface with an orange palette.

Static CSS, HTML and one small script only; no user or model text is ever injected here.
"""

from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components

from config import APP_ICON, APP_NAME, APP_TAGLINE

# Palette (kept in sync with the CSS variables and .streamlit/config.toml).
BG_DEEP = "#0A0605"
EMBER = "#FF6A1F"
AMBER = "#FFC24D"
TEXT_BRIGHT = "#FFF4EA"
TEXT_MUTED = "#CDB8A8"

_CSS = r"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&display=swap');

:root {
  --bg: #0A0605;
  --bg-2: #130C08;
  --panel: rgba(255, 255, 255, .045);
  --panel-2: rgba(255, 255, 255, .075);
  --line: rgba(255, 140, 60, .20);
  --line-2: rgba(255, 140, 60, .42);
  --ember: #FF6A1F;
  --orange: #FF8A2B;
  --amber: #FFC24D;
  --rose: #FF4D6A;
  --ink: #FFF4EA;
  --muted: #CDB8A8;
  --dim: #9C8777;
  --ok: #5EEAA8;
  --warn: #FFC24D;
  --bad: #FF6B7A;
  --grad: linear-gradient(135deg, #FF5A14 0%, #FF8A2B 55%, #FFC24D 100%);
  --glow: rgba(255, 106, 31, .45);
  --display: 'Space Grotesk', 'Segoe UI', system-ui, -apple-system, sans-serif;
}

/* ---------- Base and ambient background ---------- */
html { color-scheme: dark; }
.stApp {
  color: var(--ink);
  background:
    radial-gradient(900px 520px at 12% -8%, rgba(255, 106, 31, .26), transparent 60%),
    radial-gradient(760px 480px at 100% 8%, rgba(255, 77, 106, .15), transparent 60%),
    radial-gradient(900px 600px at 50% 112%, rgba(255, 194, 77, .12), transparent 60%),
    linear-gradient(rgba(255, 140, 60, .035) 1px, transparent 1px) 0 0 / 46px 46px,
    linear-gradient(90deg, rgba(255, 140, 60, .035) 1px, transparent 1px) 0 0 / 46px 46px,
    var(--bg);
  background-attachment: scroll;
}
.stApp, .stApp p, .stApp li, .stApp label, .stApp span { color: var(--ink); }
.stApp [data-testid="stCaptionContainer"], .stApp .stCaption, .section-note { color: var(--muted); }
::selection { background: var(--ember); color: #1A0A02; }
.block-container { padding-top: 1.2rem; padding-bottom: 4rem; max-width: 1240px; }
[data-testid="stHeader"] { background: transparent; }
h1, h2, h3, h4 { font-family: var(--display); letter-spacing: -.01em; color: var(--ink); }
.stApp h2 { font-size: 1.55rem; }
.stApp h3 { font-size: 1.2rem; }
a, a:visited { color: var(--amber); }
a:hover { color: #FFD98A; }
hr { border: none !important; height: 1px; background: linear-gradient(90deg, transparent, var(--line-2), transparent) !important; }

/* Scrollbars */
* { scrollbar-width: thin; scrollbar-color: rgba(255, 106, 31, .55) transparent; }
::-webkit-scrollbar { width: 9px; height: 9px; }
::-webkit-scrollbar-thumb { background: linear-gradient(var(--ember), var(--amber)); border-radius: 99px; }
::-webkit-scrollbar-track { background: transparent; }

/* Subheader accent bar */
.stApp h2::before {
  content: ""; display: inline-block; width: 6px; height: 1.05em; margin-right: .6rem; vertical-align: -.12em;
  border-radius: 4px; background: var(--grad); box-shadow: 0 0 14px var(--glow);
}

/* ---------- Hero ---------- */
.hero {
  position: relative; overflow: hidden; isolation: isolate;
  padding: 30px 34px 26px; margin-bottom: 18px; border-radius: 22px;
  border: 1px solid transparent;
  background:
    linear-gradient(135deg, rgba(28, 14, 8, .94), rgba(14, 8, 5, .96)) padding-box,
    linear-gradient(120deg, rgba(255, 106, 31, .95), rgba(255, 194, 77, .35) 45%, rgba(255, 77, 106, .7)) border-box;
  box-shadow: 0 28px 60px -34px rgba(255, 106, 31, .65), 0 0 0 1px rgba(255, 255, 255, .02) inset;
}
.hero::before {
  content: ""; position: absolute; z-index: -1; inset: -40% -10% auto auto; width: 520px; height: 520px;
  background: radial-gradient(circle, rgba(255, 106, 31, .38), transparent 62%);
  animation: ember-drift 9s ease-in-out infinite alternate;
}
.hero::after {
  content: ""; position: absolute; z-index: -1; inset: 0;
  background: repeating-linear-gradient(0deg, rgba(255, 255, 255, .018) 0 1px, transparent 1px 4px);
  pointer-events: none;
}
.hero .kicker {
  display: inline-flex; align-items: center; gap: 8px; font-size: .72rem; font-weight: 700;
  letter-spacing: .22em; text-transform: uppercase; color: var(--amber); margin-bottom: 10px;
}
.hero .kicker i {
  width: 8px; height: 8px; border-radius: 50%; background: var(--ok);
  box-shadow: 0 0 0 0 rgba(94, 234, 168, .7); animation: pulse-dot 2s infinite;
}
.hero h1 {
  font-family: var(--display); margin: 0 0 8px; padding: 0; line-height: 1.05;
  font-size: clamp(1.9rem, 4.6vw, 3rem); font-weight: 700; letter-spacing: -.02em;
  background: linear-gradient(100deg, #FFF4EA 0%, #FFC24D 38%, #FF7A1F 78%, #FF4D6A 100%);
  -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; color: transparent;
}
.hero p { color: var(--muted); font-size: clamp(.95rem, 1.6vw, 1.08rem); margin: 0 0 16px; max-width: 46rem; }
.hero .flow { display: flex; flex-wrap: wrap; gap: 8px; margin: 0; }
.hero .badge {
  display: inline-flex; align-items: center; gap: 8px; padding: 6px 14px 6px 8px; border-radius: 999px;
  font-size: .8rem; font-weight: 600; color: var(--ink);
  background: rgba(255, 255, 255, .05); border: 1px solid var(--line);
  backdrop-filter: blur(6px); -webkit-backdrop-filter: blur(6px);
  transition: transform .2s ease, border-color .2s ease, box-shadow .2s ease;
}
.hero .badge b {
  display: inline-grid; place-items: center; min-width: 22px; height: 22px; padding: 0 4px; border-radius: 999px;
  font-size: .66rem; letter-spacing: .04em; color: #1A0A02; background: var(--grad);
}
.hero .badge:hover { transform: translateY(-2px); border-color: var(--line-2); box-shadow: 0 8px 22px -10px var(--glow); }
.hero .orbit {
  position: absolute; z-index: -1; right: 34px; top: 50%; width: 150px; height: 150px; margin-top: -75px;
  border-radius: 50%; border: 1px dashed rgba(255, 160, 80, .35); animation: spin 26s linear infinite;
}
.hero .orbit::before, .hero .orbit::after { content: ""; position: absolute; border-radius: 50%; }
.hero .orbit::before { inset: 22px; border: 1px solid rgba(255, 194, 77, .3); }
.hero .orbit::after {
  width: 12px; height: 12px; top: -6px; left: 50%; margin-left: -6px; background: var(--grad); box-shadow: 0 0 18px 4px var(--glow);
}

@keyframes spin { to { transform: rotate(360deg); } }
@keyframes ember-drift { from { transform: translate(0, 0) scale(1); } to { transform: translate(-40px, 30px) scale(1.18); } }
@keyframes pulse-dot { 70% { box-shadow: 0 0 0 9px rgba(94, 234, 168, 0); } 100% { box-shadow: 0 0 0 0 rgba(94, 234, 168, 0); } }
@keyframes sheen { from { transform: translateX(-120%) skewX(-20deg); } to { transform: translateX(260%) skewX(-20deg); } }
@keyframes stripes { to { background-position: 32px 0; } }

/* ---------- Section navigation (horizontal radio) ---------- */
[data-testid="stRadio"] [role="radiogroup"] {
  display: flex; flex-wrap: wrap; gap: 6px; padding: 6px; border-radius: 18px;
  background: var(--panel); border: 1px solid var(--line);
  backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);
}
[data-testid="stRadio"] [data-testid="stRadioOption"], [data-testid="stRadio"] label[data-baseweb="radio"] {
  flex: 1 1 auto; justify-content: center; margin: 0; padding: .55rem 1rem; border-radius: 13px;
  border: 1px solid transparent; background: transparent; cursor: pointer;
  transition: background .2s ease, border-color .2s ease, box-shadow .2s ease, transform .2s ease;
}
[data-testid="stRadio"] [data-testid="stRadioOption"] > div > div:first-child { display: none; }
[data-testid="stRadio"] [data-testid="stRadioOption"] p,
[data-testid="stRadio"] label[data-baseweb="radio"] p { color: var(--muted); font-weight: 600; font-size: .92rem; white-space: nowrap; margin: 0; }
[data-testid="stRadio"] [data-testid="stRadioOption"]:hover,
[data-testid="stRadio"] label[data-baseweb="radio"]:hover { background: var(--panel-2); border-color: var(--line); transform: translateY(-1px); }
[data-testid="stRadio"] [data-testid="stRadioOption"]:hover p { color: var(--ink); }
[data-testid="stRadio"] [data-testid="stRadioOption"][data-selected="true"],
[data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked) {
  background: var(--grad); border-color: transparent; box-shadow: 0 8px 22px -8px var(--glow);
}
[data-testid="stRadio"] [data-testid="stRadioOption"][data-selected="true"] p,
[data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked) p { color: #1A0A02; font-weight: 700; }

/* ---------- Tabs (if used) ---------- */
.stTabs [data-baseweb="tab-list"] { gap: 6px; border-bottom: 1px solid var(--line); overflow-x: auto; }
.stTabs [data-baseweb="tab"] { padding: 10px 16px; border-radius: 12px 12px 0 0; font-weight: 600; color: var(--muted); background: transparent; }
.stTabs [data-baseweb="tab"]:hover { color: var(--ink); background: var(--panel); }
.stTabs [aria-selected="true"] { color: var(--amber); background: var(--panel); }
.stTabs [data-baseweb="tab-highlight"] { background: var(--grad); height: 3px; border-radius: 3px; }

/* ---------- Buttons ---------- */
.stButton > button, .stDownloadButton > button, [data-testid="stFormSubmitButton"] > button, [data-testid="stBaseLinkButton-secondary"] {
  position: relative; overflow: hidden; min-height: 46px; padding: .55rem 1.2rem; border-radius: 14px;
  font-weight: 600; color: var(--ink); background: var(--panel); border: 1px solid var(--line-2);
  transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease, background .18s ease;
}
.stButton > button:hover, .stDownloadButton > button:hover, [data-testid="stFormSubmitButton"] > button:hover {
  transform: translateY(-2px); color: #fff; border-color: var(--orange); background: rgba(255, 106, 31, .14);
  box-shadow: 0 12px 26px -14px var(--glow);
}
.stButton > button:active, .stDownloadButton > button:active { transform: translateY(0) scale(.99); }
.stButton > button:focus-visible, .stDownloadButton > button:focus-visible { outline: 2px solid var(--amber); outline-offset: 2px; }
.stButton > button:disabled, .stDownloadButton > button:disabled { opacity: .45; transform: none; box-shadow: none; }
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"], [data-testid="stFormSubmitButton"] > button[kind="primary"] {
  color: #1A0A02; font-weight: 700; background: var(--grad); border: none;
  box-shadow: 0 14px 30px -12px var(--glow), 0 0 0 1px rgba(255, 255, 255, .12) inset;
}
.stButton > button[kind="primary"] p, .stDownloadButton > button[kind="primary"] p { color: #1A0A02; font-weight: 700; }
.stButton > button[kind="primary"]::after, .stDownloadButton > button[kind="primary"]::after {
  content: ""; position: absolute; top: 0; left: 0; width: 40%; height: 100%;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, .5), transparent);
  transform: translateX(-120%) skewX(-20deg); pointer-events: none;
}
.stButton > button[kind="primary"]:hover, .stDownloadButton > button[kind="primary"]:hover {
  color: #1A0A02; background: var(--grad); box-shadow: 0 18px 38px -12px var(--glow), 0 0 0 1px rgba(255, 255, 255, .2) inset; filter: brightness(1.06);
}
.stButton > button[kind="primary"]:hover::after, .stDownloadButton > button[kind="primary"]:hover::after { animation: sheen .9s ease; }
.stButton > button[kind="primary"]:disabled { filter: grayscale(.5); }

/* ---------- Form controls ---------- */
[data-testid="stWidgetLabel"] p, .stApp label p {
  color: var(--ink); font-weight: 600; font-size: .86rem; letter-spacing: .01em;
}
[data-baseweb="input"], [data-baseweb="base-input"], [data-baseweb="textarea"], [data-baseweb="select"] > div {
  background: rgba(255, 255, 255, .05) !important; color: var(--ink) !important;
  border-color: var(--line-2) !important; border-radius: 12px !important; transition: border-color .2s ease, box-shadow .2s ease;
}
[data-baseweb="input"] input, [data-baseweb="textarea"] textarea, [data-baseweb="base-input"] input { color: var(--ink) !important; -webkit-text-fill-color: var(--ink); caret-color: var(--amber); background: transparent !important; }
[data-baseweb="input"] input::placeholder, [data-baseweb="textarea"] textarea::placeholder { color: var(--dim) !important; -webkit-text-fill-color: var(--dim); opacity: 1; }
[data-baseweb="input"]:hover, [data-baseweb="textarea"]:hover, [data-baseweb="select"] > div:hover { border-color: var(--line-2) !important; }
[data-baseweb="input"]:focus-within, [data-baseweb="textarea"]:focus-within, [data-baseweb="select"]:focus-within > div {
  border-color: var(--orange) !important; box-shadow: 0 0 0 3px rgba(255, 106, 31, .25), 0 0 22px -6px var(--glow) !important;
}
[data-baseweb="select"] svg, [data-testid="stNumberInput"] button svg { color: var(--amber); fill: var(--amber); }
/* Current Streamlit draws its boxes with a border that has the same colour as the fill, so give them a soft visible edge. */
[data-testid="stTextAreaRootElement"], [data-testid="stTextInputRootElement"], [data-testid="stNumberInputContainer"],
[data-testid="stSelectbox"] [role="group"], [data-testid="stMultiSelect"] [role="group"] {
  border: 1px solid rgba(255, 150, 80, .38) !important; border-radius: 12px !important;
  transition: border-color .2s ease, box-shadow .2s ease;
}
[data-testid="stTextAreaRootElement"]:hover, [data-testid="stTextInputRootElement"]:hover, [data-testid="stNumberInputContainer"]:hover,
[data-testid="stSelectbox"] [role="group"]:hover, [data-testid="stMultiSelect"] [role="group"]:hover { border-color: rgba(255, 160, 90, .6) !important; }
[data-testid="stTextAreaRootElement"]:focus-within, [data-testid="stTextInputRootElement"]:focus-within, [data-testid="stNumberInputContainer"]:focus-within,
[data-testid="stSelectbox"] [role="group"]:focus-within, [data-testid="stMultiSelect"] [role="group"]:focus-within {
  border-color: var(--orange) !important; box-shadow: 0 0 0 3px rgba(255, 106, 31, .22) !important;
}
[data-testid="stNumberInput"] button { background: rgba(255, 255, 255, .05); border-color: var(--line); color: var(--ink); }
[data-testid="stNumberInput"] button:hover { background: rgba(255, 106, 31, .2); }
[data-baseweb="tag"] { background: rgba(255, 106, 31, .22) !important; border: 1px solid var(--line-2); border-radius: 999px !important; }
[data-baseweb="tag"] span { color: var(--ink) !important; }
[data-baseweb="popover"] [data-baseweb="menu"], [data-baseweb="popover"] ul {
  background: #1A0F0A !important; border: 1px solid var(--line-2); border-radius: 14px; box-shadow: 0 24px 50px -16px rgba(0, 0, 0, .8);
}
[data-baseweb="popover"] li { color: var(--ink); }
[data-baseweb="popover"] li:hover, [data-baseweb="popover"] li[aria-selected="true"] { background: rgba(255, 106, 31, .22) !important; }
[data-testid="stCheckbox"] label span[role="checkbox"], [data-baseweb="checkbox"] > span:first-child { border-color: var(--line-2) !important; }
[data-baseweb="checkbox"] [aria-checked="true"] + div, [data-baseweb="checkbox"] input:checked + div { background: var(--ember) !important; }
[data-testid="stSlider"] [role="slider"] { background: var(--grad) !important; box-shadow: 0 0 14px var(--glow); }
[data-testid="stFileUploaderDropzone"] { background: var(--panel); border: 1.5px dashed var(--line-2); border-radius: 16px; }
[data-testid="stFileUploaderDropzone"]:hover { border-color: var(--orange); background: rgba(255, 106, 31, .08); }

/* ---------- Metrics ---------- */
[data-testid="stMetric"] {
  position: relative; overflow: hidden; padding: 14px 16px 12px 20px; border-radius: 16px;
  background: linear-gradient(160deg, rgba(255, 255, 255, .07), rgba(255, 255, 255, .02));
  border: 1px solid var(--line); backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px);
  transition: transform .2s ease, border-color .2s ease, box-shadow .2s ease;
}
[data-testid="stMetric"]::before { content: ""; position: absolute; left: 0; top: 14%; bottom: 14%; width: 4px; border-radius: 0 4px 4px 0; background: var(--grad); box-shadow: 0 0 14px var(--glow); }
[data-testid="stMetric"]:hover { transform: translateY(-2px); border-color: var(--line-2); box-shadow: 0 16px 30px -20px var(--glow); }
[data-testid="stMetricLabel"], [data-testid="stMetricLabel"] p { color: var(--muted) !important; font-size: .78rem; letter-spacing: .06em; text-transform: uppercase; }
[data-testid="stMetricValue"] { font-family: var(--display); font-weight: 700; font-size: clamp(1.35rem, 2.4vw, 2rem); color: var(--amber); text-shadow: 0 0 22px rgba(255, 140, 40, .35); }
[data-testid="stMetricValue"] > div { overflow: visible !important; text-overflow: clip !important; white-space: nowrap; }

/* ---------- Progress and status ---------- */
/* The track (empty part) is a dark, clearly different colour; only the fill (done part) is orange. */
[data-testid="stProgress"] [role="progressbar"] { background: transparent !important; }
[data-testid="stProgress"] [data-testid="stProgressBarTrack"] {
  background: #2A1E18 !important; border: 1px solid rgba(255, 255, 255, .14); border-radius: 99px; overflow: hidden;
  height: 14px !important; box-shadow: inset 0 1px 4px rgba(0, 0, 0, .6);
}
[data-testid="stProgress"] [data-testid="stProgressBarTrack"] > div {
  position: relative; overflow: hidden; background: var(--grad) !important; border-radius: 99px; box-shadow: 0 0 14px var(--glow);
}
[data-testid="stProgress"] [data-testid="stProgressBarTrack"] > div::after {
  content: ""; position: absolute; inset: 0;
  background: repeating-linear-gradient(115deg, rgba(255, 255, 255, .25) 0 8px, transparent 8px 16px) 0 0 / 32px 100%;
  animation: stripes 1.1s linear infinite;
}
[data-testid="stProgress"] p { color: var(--muted); }

/* ---------- Alerts ---------- */
[data-testid="stAlertContainer"] {
  border-radius: 14px !important; border: 1px solid var(--line) !important; border-left-width: 4px !important;
  background: #1B100A !important; backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px);
}
[data-testid="stAlertContainer"] p, [data-testid="stAlertContainer"] li, [data-testid="stAlertContainer"] span, [data-testid="stAlertContainer"] strong { color: var(--ink) !important; }
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentSuccess"]) { border-color: rgba(94, 234, 168, .5) !important; border-left-color: var(--ok) !important; background: linear-gradient(90deg, rgba(94, 234, 168, .14), #1B100A 70%) !important; }
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentWarning"]) { border-color: rgba(255, 194, 77, .5) !important; border-left-color: var(--warn) !important; background: linear-gradient(90deg, rgba(255, 194, 77, .15), #1B100A 70%) !important; }
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentError"]) { border-color: rgba(255, 107, 122, .5) !important; border-left-color: var(--bad) !important; background: linear-gradient(90deg, rgba(255, 107, 122, .16), #1B100A 70%) !important; }
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentInfo"]) { border-color: rgba(255, 138, 43, .45) !important; border-left-color: var(--ember) !important; background: linear-gradient(90deg, rgba(255, 106, 31, .16), #1B100A 70%) !important; }

/* ---------- Expanders, status, containers ---------- */
[data-testid="stExpander"] details, [data-testid="stExpander"] { border-radius: 16px; }
[data-testid="stExpander"] details { border: 1px solid var(--line); background: var(--panel); transition: border-color .2s ease; }
[data-testid="stExpander"] details:hover, [data-testid="stExpander"] details[open] { border-color: var(--line-2); }
[data-testid="stExpander"] summary { padding: .7rem 1rem; border-radius: 16px; }
[data-testid="stExpander"] summary:hover { background: rgba(255, 106, 31, .08); }
[data-testid="stExpander"] summary p { color: var(--ink); font-weight: 600; }
[data-testid="stExpander"] summary svg { color: var(--amber); }
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) { border-radius: 16px; }
div[data-testid="stVerticalBlockBorderWrapper"][class*="border"], [data-testid="stVerticalBlock"][class*="stVerticalBlock"] > [data-testid="stVerticalBlockBorderWrapper"] { border-color: var(--line); }

/* ---------- Data, media ---------- */
[data-testid="stDataFrame"] { border: 1px solid var(--line); border-radius: 14px; overflow: hidden; }
[data-testid="stImage"] img { border-radius: 14px; border: 1px solid var(--line); box-shadow: 0 20px 40px -26px rgba(0, 0, 0, .9); }
[data-testid="stAudio"] audio, audio { width: 100%; border-radius: 99px; }
code, pre { border-radius: 10px; }
[data-testid="stCode"], pre { background: #140B07 !important; border: 1px solid var(--line); }
[data-testid="stMarkdownContainer"] blockquote { border-left: 3px solid var(--ember); background: var(--panel); border-radius: 0 12px 12px 0; padding: .4rem 1rem; }
[data-testid="stToast"] { border: 1px solid var(--line-2); border-radius: 14px; background: #1A0F0A; }
[data-testid="stSpinner"] i, [data-testid="stSpinner"] svg { border-top-color: var(--ember); }

/* ---------- Sidebar ---------- */
[data-testid="stSidebar"] {
  background: linear-gradient(180deg, #160C08 0%, #0D0705 100%); border-right: 1px solid var(--line);
  box-shadow: 18px 0 50px -30px rgba(255, 106, 31, .35);
}
[data-testid="stSidebar"] h3 {
  font-size: .78rem !important; font-weight: 700; letter-spacing: .2em; text-transform: uppercase; color: var(--amber);
  display: flex; align-items: center; gap: 10px;
}
[data-testid="stSidebar"] h3::after { content: ""; flex: 1; height: 1px; background: linear-gradient(90deg, var(--line-2), transparent); }
[data-testid="stSidebar"] p, [data-testid="stSidebar"] label, [data-testid="stSidebar"] .stCaption { color: var(--muted); }
[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"] button, [data-testid="stExpandSidebarButton"] button {
  color: var(--amber); border-radius: 12px;
}
[data-testid="stExpandSidebarButton"] { background: rgba(255, 106, 31, .15); border: 1px solid var(--line-2); border-radius: 12px; }

.side-brand {
  position: relative; overflow: hidden; isolation: isolate; padding: 18px 18px 14px; margin-bottom: 10px; border-radius: 20px; border: 1px solid transparent;
  background:
    linear-gradient(145deg, rgba(34, 17, 9, .96), rgba(15, 8, 5, .96)) padding-box,
    linear-gradient(130deg, rgba(255, 106, 31, .9), rgba(255, 194, 77, .3), rgba(255, 77, 106, .55)) border-box;
  box-shadow: 0 20px 40px -26px var(--glow);
}
.side-brand::before {
  content: ""; position: absolute; z-index: -1; right: -40px; top: -50px; width: 170px; height: 170px;
  background: radial-gradient(circle, rgba(255, 106, 31, .42), transparent 65%); animation: ember-drift 8s ease-in-out infinite alternate;
}
.side-brand .logo {
  display: inline-grid; place-items: center; width: 46px; height: 46px; border-radius: 14px; font-size: 1.5rem; line-height: 1;
  background: var(--grad); box-shadow: 0 10px 24px -8px var(--glow);
}
.side-brand .name { font-family: var(--display); font-size: 1.3rem; font-weight: 700; margin: 10px 0 2px; letter-spacing: -.01em; color: var(--ink); }
.side-brand .tag { font-size: .84rem; color: var(--muted); margin-bottom: 12px; line-height: 1.35; }
.side-brand .chip {
  display: inline-block; margin: 0 4px 4px 0; padding: 3px 10px; border-radius: 999px; font-size: .72rem; font-weight: 600;
  letter-spacing: .03em; color: var(--amber); background: rgba(255, 140, 40, .12); border: 1px solid var(--line-2);
}

/* ---------- Pills ---------- */
.pill {
  display: inline-flex; align-items: center; gap: 6px; padding: 3px 11px; margin: 0 6px 4px 0; border-radius: 999px;
  font-size: .76rem; font-weight: 700; letter-spacing: .02em; border: 1px solid; white-space: nowrap;
}
.pill::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: currentColor; box-shadow: 0 0 8px currentColor; }
.pill-ok { color: var(--ok); background: rgba(94, 234, 168, .10); border-color: rgba(94, 234, 168, .45); }
.pill-warn { color: var(--warn); background: rgba(255, 194, 77, .10); border-color: rgba(255, 194, 77, .5); }
.pill-bad { color: var(--bad); background: rgba(255, 107, 122, .10); border-color: rgba(255, 107, 122, .5); }
.pill-info { color: #FFB27A; background: rgba(255, 138, 43, .12); border-color: rgba(255, 138, 43, .5); }
.section-note { font-size: .95rem; margin: -.2rem 0 1rem; }

/* ---------- Hosting chrome (Share, star, edit, GitHub, menu, Manage app) is not part of the app ----------
   The sidebar expand button lives in the toolbar, so it stays. */
[data-testid="stToolbar"] *:not(:has([data-testid="stExpandSidebarButton"])):not([data-testid="stExpandSidebarButton"]):not([data-testid="stExpandSidebarButton"] *) { display: none !important; }
[data-testid="stToolbarActions"], [data-testid="stAppDeployButton"], [data-testid="stMainMenu"],
[data-testid="stStatusWidget"], [data-testid="stDecoration"], [data-testid="manage-app-button"], #MainMenu, footer,
[class*="viewerBadge"], [class*="stDeployButton"], [class*="_terminalButton_"], [class*="_profileContainer_"],
[class*="_profilePreview_"], a[href*="streamlit.io/cloud"][class*="badge" i] {
  display: none !important; visibility: hidden !important; pointer-events: none !important;
}
[data-testid="stSidebarCollapsedControl"], [data-testid="stExpandSidebarButton"] { display: flex !important; visibility: visible !important; pointer-events: auto !important; }
[data-testid="stElementContainer"]:has(> iframe[height="0"]), [data-testid="stElementContainer"]:has(> iframe[height="1"]) { display: none !important; }

/* ---------- Tablets ---------- */
@media (max-width: 900px) {
  .block-container { padding-left: 1rem; padding-right: 1rem; padding-top: 1rem; }
  .hero { padding: 24px 22px 20px; border-radius: 20px; }
  .hero .orbit { opacity: .5; right: 12px; width: 110px; height: 110px; margin-top: -55px; }
  [data-testid="stRadio"] [role="radiogroup"] { flex-wrap: nowrap; overflow-x: auto; scrollbar-width: none; }
  [data-testid="stRadio"] [role="radiogroup"]::-webkit-scrollbar { display: none; }
  [data-testid="stRadio"] [data-testid="stRadioOption"], [data-testid="stRadio"] label[data-baseweb="radio"] { flex: 0 0 auto; }
}

/* ---------- Phones ---------- */
@media (max-width: 640px) {
  .block-container { padding-left: .75rem; padding-right: .75rem; padding-bottom: 3rem; }
  .hero { padding: 20px 16px 16px; border-radius: 18px; }
  .hero .orbit { display: none; }
  .hero .badge { padding: 5px 11px 5px 6px; font-size: .74rem; }
  .stApp h2 { font-size: 1.3rem; }
  .stButton > button, .stDownloadButton > button, [data-testid="stFormSubmitButton"] > button { width: 100%; min-height: 48px; }
  [data-testid="stRadio"] [data-testid="stRadioOption"], [data-testid="stRadio"] label[data-baseweb="radio"] { padding: .5rem .85rem; }
  [data-testid="stMetric"] { padding: 10px 12px 10px 16px; }
  [data-testid="stMetricValue"] { font-size: 1.5rem; }
  [data-testid="stHorizontalBlock"] { gap: .6rem; }
  [data-baseweb="input"] input, [data-baseweb="textarea"] textarea, [data-baseweb="select"] input { font-size: 16px; }
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important; transition: none !important; }
}
</style>
"""

# Hides the hosting overlays that Streamlit Cloud adds outside the app (Manage app bar, profile badge, deploy button).
_HIDE_HOST_CHROME = r"""<script>
(function () {
  var P; try { P = window.parent; void P.document; } catch (e) { return; }
  if (P.__abTimer) P.clearInterval(P.__abTimer);
  var SEL = '[class*="viewerBadge"],[data-testid="manage-app-button"],[class*="_terminalButton_"],[class*="_profileContainer_"],[class*="stDeployButton"],[data-testid="stAppDeployButton"],[data-testid="stMainMenu"]';
  function hide(doc) {
    try {
      doc.querySelectorAll(SEL).forEach(function (el) { el.style.setProperty('display', 'none', 'important'); });
      var walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT, null), node, hits = [];
      while ((node = walker.nextNode())) { if (/^\s*Manage app\s*$/i.test(node.nodeValue)) hits.push(node.parentElement); }
      hits.forEach(function (el) {
        var up = el, fixed = null;
        for (var i = 0; i < 8 && up && up !== doc.body; i++, up = up.parentElement) {
          var cs = doc.defaultView.getComputedStyle(up);
          if (cs.position === 'fixed' || cs.position === 'sticky') { fixed = up; break; }
        }
        (fixed || el).style.setProperty('display', 'none', 'important');
      });
    } catch (e) {}
  }
  function run() {
    var docs = [P.document];
    try { if (P.top && P.top !== P && P.top.document) docs.push(P.top.document); } catch (e) {}
    docs.forEach(hide);
  }
  P.__abTimer = P.setInterval(run, 500);
  run();
})();
</script>"""


def apply_styles() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
    # st.components.v1.html is deprecated; st.iframe replaces it on newer Streamlit releases.
    if hasattr(st, "iframe"):
        st.iframe(_HIDE_HOST_CHROME, height=1)
    else:
        components.html(_HIDE_HOST_CHROME, height=0)


def render_header() -> None:
    st.markdown(
        f"""
<div class="hero">
  <div class="orbit"></div>
  <div class="kicker"><i></i>Ember Forge &middot; AI publishing suite</div>
  <h1>{APP_ICON} {APP_NAME}</h1>
  <p>{APP_TAGLINE}</p>
  <div class="flow">
    <span class="badge"><b>01</b>Plan</span><span class="badge"><b>02</b>Write</span><span class="badge"><b>03</b>Review</span><span class="badge"><b>04</b>Illustrate</span><span class="badge"><b>05</b>Export PDF &amp; DOCX</span>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def pill(text: str, kind: str = "info") -> str:
    """HTML for a status pill. ``text`` must be application-controlled, never user or model text."""
    return f'<span class="pill pill-{kind}">{text}</span>'
