"""Cyberpunk yellow visual theme: global CSS, brand block, pipeline stepper, page headers and small tags.

Colours come from ``.streamlit/config.toml``; this module adds the parts Streamlit's theme cannot express (grid background,
neon glow, angular buttons, the pipeline stepper). Everything is plain CSS: no JavaScript runs in the browser.
"""

from __future__ import annotations

from html import escape

import streamlit as st

from ats.workflow import WorkflowState

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700;900&family=Rajdhani:wght@400;500;600;700&family=Share+Tech+Mono&display=swap');
:root {
  --y: #FFE600; --y-dim: #B8A600; --y-soft: rgba(255, 230, 0, .12); --cyan: #00E5FF; --mag: #FF2E88; --ok: #39FF88; --bad: #FF2E63;
  --bg: #08080B; --panel: #111116; --panel-2: #16161C; --line: #3D3811; --dim: #8D8A72; --text: #EDEBDD;
  --display: 'Orbitron', 'Segoe UI', sans-serif; --body: 'Rajdhani', 'Segoe UI', sans-serif; --mono: 'Share Tech Mono', Consolas, monospace;
}
html, body, .stApp, [data-testid="stAppViewContainer"] { font-family: var(--body); font-size: 17px; }
.stApp {
  background:
    radial-gradient(1100px 520px at 88% -8%, rgba(255, 230, 0, .10), transparent 62%),
    radial-gradient(800px 420px at -5% 105%, rgba(0, 229, 255, .06), transparent 60%),
    linear-gradient(rgba(255, 230, 0, .028) 1px, transparent 1px) 0 0 / 46px 46px,
    linear-gradient(90deg, rgba(255, 230, 0, .028) 1px, transparent 1px) 0 0 / 46px 46px,
    var(--bg);
}
[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 2.2rem; max-width: 1280px; }

/* ---------- typography ---------- */
h1, h2, h3, h4 { font-family: var(--display) !important; letter-spacing: .04em; text-transform: uppercase; }
h1 { color: var(--y); text-shadow: 0 0 18px rgba(255, 230, 0, .45); font-size: 1.9rem !important; }
h2 { color: var(--y); font-size: 1.35rem !important; }
h3 { color: var(--text); font-size: 1.05rem !important; border-left: 3px solid var(--y); padding-left: .6rem; }
code, pre, kbd { font-family: var(--mono) !important; }
a { text-decoration: none; border-bottom: 1px dashed var(--y-dim); }
hr { border-color: var(--line) !important; }
[data-testid="stCaptionContainer"], .stCaption { color: var(--dim) !important; font-family: var(--mono); font-size: .8rem !important; letter-spacing: .02em; }

/* ---------- buttons ---------- */
.stButton, .stDownloadButton, [data-testid="stFormSubmitButton"] { filter: drop-shadow(0 0 7px rgba(255, 230, 0, .18)); }
button[data-testid^="stBaseButton"] {
  font-family: var(--display); font-size: .74rem; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; min-height: 2.6rem;
  border-radius: 0 !important; clip-path: polygon(0 0, calc(100% - 10px) 0, 100% 10px, 100% 100%, 10px 100%, 0 calc(100% - 10px));
  transition: transform .12s ease, background .12s ease, color .12s ease;
}
button[data-testid="stBaseButton-primary"], button[data-testid="stBaseButton-primaryFormSubmit"] {
  background: var(--y) !important; color: #0A0A0A !important; border: none !important;
}
button[data-testid="stBaseButton-primary"]:hover, button[data-testid="stBaseButton-primaryFormSubmit"]:hover { background: #FFF45C !important; transform: translateY(-1px); }
button[data-testid="stBaseButton-secondary"], button[data-testid="stBaseButton-secondaryFormSubmit"] {
  background: rgba(255, 230, 0, .04) !important; color: var(--y) !important; border: 1px solid var(--y-dim) !important;
}
button[data-testid="stBaseButton-secondary"]:hover, button[data-testid="stBaseButton-secondaryFormSubmit"]:hover { background: var(--y-soft) !important; border-color: var(--y) !important; }
button[data-testid^="stBaseButton"]:disabled { opacity: .35; filter: grayscale(.6); }

/* ---------- inputs ---------- */
[data-baseweb="input"], [data-baseweb="textarea"], [data-baseweb="select"] > div { background: var(--panel) !important; border-color: var(--line) !important; border-radius: 0 !important; }
[data-baseweb="input"]:focus-within, [data-baseweb="textarea"]:focus-within, [data-baseweb="select"] > div:focus-within {
  border-color: var(--y) !important; box-shadow: 0 0 0 1px var(--y), 0 0 16px rgba(255, 230, 0, .22) !important;
}
label, [data-testid="stWidgetLabel"] p { font-family: var(--mono) !important; font-size: .78rem !important; letter-spacing: .06em; text-transform: uppercase; color: var(--dim) !important; }
[data-testid="stCheckbox"] label p, [data-testid="stRadio"] label p { text-transform: none; letter-spacing: 0; color: var(--text) !important; font-family: var(--body) !important; font-size: 1rem !important; }

/* ---------- containers ---------- */
[data-testid="stVerticalBlockBorderWrapper"] { border-radius: 0 !important; border-color: var(--line) !important; background: rgba(17, 17, 22, .72); }
[data-testid="stExpander"] { border: 1px solid var(--line) !important; border-radius: 0 !important; background: rgba(17, 17, 22, .6); }
[data-testid="stExpander"] summary:hover { color: var(--y); }
[data-testid="stForm"] { border: 1px solid var(--line) !important; border-radius: 0 !important; background: rgba(17, 17, 22, .6); }
[data-testid="stAlert"] { border-radius: 0 !important; border: 1px solid var(--line); border-left: 3px solid var(--y); background: rgba(17, 17, 22, .85); }
[data-testid="stStatusWidget"], [data-testid="stStatus"] { border-radius: 0 !important; border-color: var(--line) !important; }
[data-testid="stMetric"] {
  background: linear-gradient(135deg, rgba(255, 230, 0, .07), rgba(17, 17, 22, .9) 55%); border: 1px solid var(--line); border-left: 3px solid var(--y);
  padding: .7rem .9rem; clip-path: polygon(0 0, calc(100% - 12px) 0, 100% 12px, 100% 100%, 0 100%);
}
[data-testid="stMetricValue"] { font-family: var(--display); color: var(--y); font-size: 1.7rem; text-shadow: 0 0 12px rgba(255, 230, 0, .35); }
[data-testid="stMetricLabel"] p { font-family: var(--mono) !important; letter-spacing: .08em; }
[data-baseweb="tab-list"] { gap: .25rem; border-bottom: 1px solid var(--line); }
[data-baseweb="tab"] { font-family: var(--display); font-size: .72rem; letter-spacing: .1em; text-transform: uppercase; }
[data-baseweb="tab-highlight"] { background: var(--y) !important; box-shadow: 0 0 10px var(--y); }
[data-testid="stDataFrame"] { border: 1px solid var(--line); }
[data-testid="stProgress"] > div > div > div > div { background: linear-gradient(90deg, var(--y-dim), var(--y)); box-shadow: 0 0 10px rgba(255, 230, 0, .5); }

/* ---------- sidebar ---------- */
[data-testid="stSidebar"] { background: #060608; border-right: 1px solid var(--line); }
[data-testid="stSidebar"] .block-container { padding-top: 1rem; }
.ats-brand { display: flex; align-items: center; gap: .65rem; padding: .2rem 0 .9rem 0; border-bottom: 1px solid var(--line); margin-bottom: .9rem; }
.ats-brand .mark { width: 34px; height: 34px; background: var(--y); clip-path: polygon(0 0, 100% 0, 100% 62%, 62% 100%, 0 100%); box-shadow: 0 0 18px rgba(255, 230, 0, .55); }
.ats-brand .name { font-family: var(--display); font-weight: 900; font-size: 1rem; letter-spacing: .14em; color: var(--y); line-height: 1.05; }
.ats-brand .tag { font-family: var(--mono); font-size: .66rem; color: var(--dim); letter-spacing: .12em; }
.ats-next { font-family: var(--mono); font-size: .78rem; color: var(--text); border: 1px dashed var(--y-dim); padding: .55rem .7rem; margin: .5rem 0; background: var(--y-soft); }
.ats-next b { color: var(--y); letter-spacing: .1em; }

/* ---------- page header ---------- */
.ats-ph { margin: 0 0 1.1rem 0; padding-bottom: .8rem; border-bottom: 1px solid var(--line); position: relative; }
.ats-ph::after { content: ""; position: absolute; left: 0; bottom: -1px; width: 120px; height: 2px; background: var(--y); box-shadow: 0 0 12px var(--y); }
.ats-kicker { font-family: var(--mono); font-size: .72rem; letter-spacing: .24em; color: var(--cyan); text-transform: uppercase; margin-bottom: .15rem; }
.ats-ph h1 { margin: 0; padding: 0; }
.ats-sub { color: var(--dim); font-size: 1rem; margin-top: .25rem; max-width: 62rem; }

/* ---------- pipeline stepper ---------- */
.ats-pipe { display: grid; grid-template-columns: repeat(9, minmax(0, 1fr)); gap: 4px; margin: 0 0 1.3rem 0; }
.ats-step { position: relative; padding: .45rem .55rem .5rem .7rem; background: var(--panel); border: 1px solid var(--line); min-height: 3.1rem;
  clip-path: polygon(0 0, calc(100% - 10px) 0, 100% 50%, calc(100% - 10px) 100%, 0 100%, 8px 50%); }
.ats-step .n { font-family: var(--mono); font-size: .62rem; color: var(--dim); letter-spacing: .12em; }
.ats-step .t { display: block; font-family: var(--display); font-size: .62rem; letter-spacing: .08em; text-transform: uppercase; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ats-step .d { display: block; font-family: var(--mono); font-size: .6rem; color: var(--dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ats-step.done { background: var(--y); border-color: var(--y); }
.ats-step.done .n, .ats-step.done .t, .ats-step.done .d { color: #0A0A0A; }
.ats-step.current { background: var(--y-soft); border-color: var(--y); box-shadow: inset 0 0 0 1px var(--y); animation: ats-pulse 2.2s ease-in-out infinite; }
.ats-step.current .t { color: var(--y); }
.ats-step.optional { border-style: dashed; opacity: .7; }
.ats-step.blocked { border-color: var(--bad); }
@keyframes ats-pulse { 0%, 100% { box-shadow: inset 0 0 0 1px var(--y), 0 0 0 rgba(255, 230, 0, 0); } 50% { box-shadow: inset 0 0 0 1px var(--y), 0 0 16px rgba(255, 230, 0, .35); } }

/* ---------- tags and hero ---------- */
.ats-tag { display: inline-block; font-family: var(--mono); font-size: .7rem; letter-spacing: .1em; padding: .1rem .5rem; border: 1px solid var(--y-dim); color: var(--y); text-transform: uppercase; margin-right: .4rem; }
.ats-tag.ok { border-color: var(--ok); color: var(--ok); }
.ats-tag.bad { border-color: var(--bad); color: var(--bad); }
.ats-tag.info { border-color: var(--cyan); color: var(--cyan); }
.ats-tag.dim { border-color: var(--line); color: var(--dim); }
.ats-card-title { font-family: var(--display); font-size: .95rem; letter-spacing: .06em; color: var(--text); }
.ats-card-meta { font-family: var(--mono); font-size: .74rem; color: var(--dim); }
@media (max-width: 1100px) { .ats-pipe { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
"""

KIND_BY_STAGE_STATUS = {"done": "done", "current": "current", "waiting": "", "optional": "optional", "blocked": "blocked"}


def apply() -> None:
    """Inject the global stylesheet. Call once per run, before any page content."""
    st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)


def brand() -> str:
    return (
        '<div class="ats-brand"><div class="mark"></div><div><div class="name">ATS//STUDIO</div>'
        '<div class="tag">AUTONOMOUS TESTING</div></div></div>'
    )


def tag(text: str, kind: str = "") -> str:
    """HTML tag chip. ``kind``: ok, bad, info, dim or empty (yellow)."""
    return f'<span class="ats-tag {kind}">{escape(text)}</span>'


def page_header(title: str, subtitle: str = "", step: str = "") -> None:
    kicker = f'<div class="ats-kicker">{escape(step)}</div>' if step else ""
    sub = f'<div class="ats-sub">{escape(subtitle)}</div>' if subtitle else ""
    st.markdown(f'<div class="ats-ph">{kicker}<h1>{escape(title)}</h1>{sub}</div>', unsafe_allow_html=True)


def pipeline_html(state: WorkflowState) -> str:
    steps = []
    for index, stage in enumerate(state.stages, 1):
        kind = KIND_BY_STAGE_STATUS.get(stage.status, "")
        detail = escape(stage.detail) if stage.detail and stage.status != "waiting" else "&nbsp;"
        steps.append(
            f'<div class="ats-step {kind}" title="{escape(stage.name)}: {escape(stage.detail or stage.status)}">'
            f'<span class="n">{index:02d}</span><span class="t">{escape(stage.name)}</span><span class="d">{detail}</span></div>'
        )
    return f'<div class="ats-pipe">{"".join(steps)}</div>'


def pipeline(state: WorkflowState) -> None:
    st.markdown(pipeline_html(state), unsafe_allow_html=True)
