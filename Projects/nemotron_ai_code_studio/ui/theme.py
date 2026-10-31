"""Visual theme: a full-viewport, glass-and-neon IDE shell. All styling lives here."""

from __future__ import annotations

from html import escape

import streamlit as st

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {
  --bg0:#020a07; --bg1:#04110c; --panel:rgba(5,22,15,.78); --panel2:rgba(12,40,28,.55);
  --line:rgba(110,255,190,.13); --line2:rgba(110,255,190,.26);
  --text:#dcfff0; --muted:#6fa08a; --dim:#4a7a64;
  --cyan:#2bff9a; --violet:#0fbf6b; --pink:#b8ff3d; --green:#34d399; --red:#fb7185; --amber:#fbbf24;
  --grad:linear-gradient(120deg,#2bff9a 0%,#0fbf6b 55%,#b8ff3d 100%);
  --tb:52px; --sb:28px; --act:58px;
  --main-h:calc(100vh - var(--tb) - var(--sb));
  --bottom-h-d:clamp(190px,31vh,330px); --side-w-d:clamp(230px,19vw,310px); --agent-w-d:clamp(330px,28vw,470px);
  --bottom-h:var(--bottom-h-d); --side-w:var(--side-w-d); --agent-w:var(--agent-w-d);
  --mono:'JetBrains Mono','Cascadia Code','Cascadia Mono',Consolas,monospace;
  --sans:'Space Grotesk','Segoe UI Variable Text','Segoe UI',system-ui,sans-serif;
}

/* ---------- full-viewport shell ---------- */
html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] { height:100vh; overflow:hidden !important; }
.stApp {
  font-family:var(--sans); color:var(--text);
  background:
    radial-gradient(1100px 560px at 8% -12%, rgba(15,191,107,.20), transparent 60%),
    radial-gradient(900px 520px at 100% 0%, rgba(43,255,154,.13), transparent 55%),
    radial-gradient(900px 520px at 55% 118%, rgba(184,255,61,.10), transparent 60%),
    var(--bg0) !important;
}
[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stStatusWidget"], footer { display:none !important; }
[data-testid="stMainBlockContainer"], .block-container { padding:0 !important; max-width:100% !important; }
/* No blinking while the script re-runs: Streamlit dims/fades "stale" elements on every interaction; keep them fully visible. */
[data-stale], [data-stale="true"] { opacity:1 !important; transition:none !important; }
[data-testid="stAppViewContainer"], [data-testid="stMain"], [data-testid="stMainBlockContainer"], [data-testid="stVerticalBlock"], [data-testid="stElementContainer"] { transition:none !important; }
[data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] { gap:0 !important; }
[data-testid="stAppViewContainer"] > .stMain, [data-testid="stMain"] { padding:0 !important; }
* { scrollbar-width:thin; scrollbar-color:rgba(15,191,107,.45) transparent; }
::-webkit-scrollbar { width:8px; height:8px; } ::-webkit-scrollbar-thumb { background:rgba(15,191,107,.4); border-radius:8px; } ::-webkit-scrollbar-track { background:transparent; }
h1,h2,h3,h4,h5,h6,p,label,span,div { font-family:var(--sans); }
code, pre, kbd { font-family:var(--mono) !important; }
p { margin:0; }
/* Streamlit gives every markdown block a -1rem bottom margin that cancels the 1rem margin of its paragraph; with "p { margin:0 }" that left -16px,
   so each text block was pulled under the next one and the two overlapped (approval cards, terminal prompt, agent answers) */
[data-testid="stMarkdownContainer"], [data-testid="stCaptionContainer"] { margin-bottom:0 !important; }
[data-testid="stMarkdownContainer"] p + p, [data-testid="stMarkdownContainer"] ul, [data-testid="stMarkdownContainer"] ol { margin-top:.5rem; }
[data-testid="stVerticalBlock"] { gap:.55rem; }
div[data-testid="stVerticalBlock"][class*="st-key-"] { flex:0 0 auto !important; }

/* ---------- title bar ---------- */
div.st-key-titlebar {
  height:var(--tb); padding:0 14px; display:flex; align-items:center; position:relative; z-index:1200;
  background:linear-gradient(180deg,rgba(8,30,21,.92),rgba(3,16,11,.78)); backdrop-filter:blur(18px);
  border-bottom:1px solid var(--line);
}
div.st-key-titlebar::after { content:""; position:absolute; left:0; right:0; bottom:-1px; height:1px; background:var(--grad); opacity:.55; filter:blur(.3px); }
div.st-key-titlebar [data-testid="stHorizontalBlock"] { width:100%; align-items:center; flex-wrap:nowrap !important; gap:.6rem; }
.brand { display:flex; align-items:center; gap:10px; white-space:nowrap; }
.brand .logo {
  width:30px; height:30px; border-radius:9px; display:grid; place-items:center; font:700 15px var(--mono); color:#020a07;
  background:var(--grad); box-shadow:0 0 18px rgba(15,191,107,.55), 0 0 32px rgba(43,255,154,.25);
}
.brand .word { font:700 14px var(--sans); letter-spacing:.22em; color:var(--text); }
.brand .word b { margin-left:.55em; font-weight:500; letter-spacing:.3em; background:var(--grad); -webkit-background-clip:text; background-clip:text; color:transparent; }
.pill {
  display:inline-flex; align-items:center; gap:8px; height:32px; padding:0 14px; border-radius:999px; white-space:nowrap;
  background:rgba(255,255,255,.035); border:1px solid var(--line); font:500 12.5px var(--sans); color:var(--text); max-width:100%; overflow:hidden; text-overflow:ellipsis;
}
.pill i { width:7px; height:7px; border-radius:50%; background:var(--cyan); box-shadow:0 0 10px var(--cyan); flex:none; }
.pill.off i { background:var(--dim); box-shadow:none; }
div.st-key-titlebar [data-baseweb="select"] > div { min-height:32px !important; border-radius:999px !important; font-size:12.5px; }

/* ---------- main row ---------- */
div.st-key-shell [data-testid="stHorizontalBlock"], div.st-key-shell > [data-testid="stHorizontalBlock"] { gap:0 !important; flex-wrap:nowrap !important; align-items:stretch; }
[data-testid="stColumn"] { min-width:0; }
[data-testid="stColumn"]:has(div.st-key-activity) { flex:0 0 var(--act) !important; width:var(--act) !important; min-width:var(--act) !important; }
[data-testid="stColumn"]:has(div.st-key-sidebar)  { flex:0 0 var(--side-w) !important; width:var(--side-w) !important; min-width:0 !important; }
[data-testid="stColumn"]:has(div.st-key-agent)    { flex:0 0 var(--agent-w) !important; width:var(--agent-w) !important; min-width:0 !important; }
[data-testid="stColumn"]:has(div.st-key-centre)   { flex:1 1 0 !important; width:auto !important; min-width:0 !important; }

div.st-key-activity { height:var(--main-h); padding:12px 0; align-items:center; background:rgba(3,13,9,.85); border-right:1px solid var(--line); gap:.4rem !important; }
div.st-key-activity [data-testid="stElementContainer"] { width:auto !important; }
div.st-key-activity [data-testid^="stBaseButton"] {
  width:42px; height:42px; min-height:42px; padding:0 !important; border-radius:13px !important; border:1px solid transparent !important; background:transparent !important; color:var(--muted) !important; box-shadow:none !important;
}
div.st-key-activity [data-testid^="stBaseButton"]:hover { color:var(--text) !important; background:rgba(43,255,154,.08) !important; }
div.st-key-activity [data-testid="stBaseButton-primary"] {
  color:var(--cyan) !important; background:linear-gradient(135deg,rgba(43,255,154,.16),rgba(15,191,107,.16)) !important;
  border:1px solid rgba(43,255,154,.35) !important; box-shadow:0 0 18px rgba(43,255,154,.22), inset 0 0 12px rgba(15,191,107,.18) !important;
}
div.st-key-activity [data-testid^="stBaseButton"] span[data-testid="stIconMaterial"], div.st-key-activity [data-testid^="stBaseButton"] [data-testid="stIconMaterial"] { font-size:23px !important; }

div.st-key-activity [class*="_pending"] [data-testid^="stBaseButton"] { position:relative; }
div.st-key-activity [class*="_pending"] [data-testid^="stBaseButton"]::after {
  content:""; position:absolute; top:7px; right:7px; width:10px; height:10px; border-radius:50%; background:#3b9cff;
  border:2px solid #030d09; box-shadow:0 0 8px rgba(59,156,255,.9); animation:scmdot 1.8s ease-in-out infinite;
}
@keyframes scmdot { 0%,100% { transform:scale(1); } 50% { transform:scale(1.25); } }

div.st-key-sidebar { height:var(--main-h); overflow-y:auto; overflow-x:hidden; padding:14px 12px; background:var(--panel); backdrop-filter:blur(14px); border-right:1px solid var(--line); gap:.45rem !important; }
div.st-key-centre  { height:var(--main-h); overflow:hidden; gap:0 !important; }
div.st-key-agent   { height:var(--main-h); overflow:hidden; padding:12px 14px; background:var(--panel); backdrop-filter:blur(14px); border-left:1px solid var(--line); gap:.5rem !important; display:flex; flex-direction:column; }

.sec { display:flex; align-items:baseline; justify-content:space-between; gap:8px; padding:0 2px 2px; }
.sec b { font:600 11px var(--sans); letter-spacing:.2em; text-transform:uppercase; background:var(--grad); -webkit-background-clip:text; background-clip:text; color:transparent; }
.sec span { font:500 11px var(--mono); color:var(--muted); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }

/* ---------- buttons ---------- */
[data-testid^="stBaseButton-"], [data-testid="stPopover"] > button, [data-testid="stPopoverButton"] {
  border-radius:11px !important; border:1px solid var(--line) !important; background:rgba(255,255,255,.035) !important; color:var(--text) !important;
  font:500 12.5px var(--sans) !important; min-height:32px; padding:.15rem .75rem; transition:all .18s ease; box-shadow:none;
}
[data-testid^="stBaseButton-"] p { font:500 12.5px var(--sans) !important; }
[data-testid^="stBaseButton-"]:hover, [data-testid="stPopoverButton"]:hover {
  border-color:rgba(43,255,154,.55) !important; background:rgba(43,255,154,.07) !important; color:#fff !important;
  box-shadow:0 0 0 1px rgba(43,255,154,.18), 0 0 18px rgba(43,255,154,.18) !important; transform:translateY(-1px);
}
[data-testid^="stBaseButton-"]:active { transform:translateY(0); }
[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"] {
  border:none !important; color:#020a07 !important; font-weight:700 !important;
  background:linear-gradient(120deg,#2bff9a,#0fbf6b) !important; box-shadow:0 0 20px rgba(15,191,107,.35) !important;
}
[data-testid="stBaseButton-primary"] p, [data-testid="stBaseButton-primaryFormSubmit"] p { color:#020a07 !important; font-weight:700 !important; }
[data-testid="stBaseButton-primary"]:hover, [data-testid="stBaseButton-primaryFormSubmit"]:hover { filter:brightness(1.12); box-shadow:0 0 28px rgba(43,255,154,.45) !important; }
[data-testid^="stBaseButton-"]:disabled { opacity:.35; transform:none; box-shadow:none !important; }
[data-testid="stBaseButton-tertiary"] { border-color:transparent !important; background:transparent !important; }

/* icon-only ghost buttons in the title bar */
[data-testid="stPopover"] button > div > div:last-child:not(:first-child) { display:none; }
[data-testid="stPopover"] button { justify-content:center; }
div.st-key-titlebar [data-testid^="stBaseButton"] { width:36px; padding:0 !important; border-radius:50% !important; height:36px; }

/* ---------- file rows (explorer, search hits, source control, problems) ---------- */
[class*="st-key-entry-"] [data-testid^="stBaseButton"],
[class*="st-key-hit-"] [data-testid^="stBaseButton"],
[class*="st-key-scdiff-"] [data-testid^="stBaseButton"],
[class*="st-key-prob"] [data-testid^="stBaseButton"],
[class*="st-key-tprob"] [data-testid^="stBaseButton"],
div.st-key-up [data-testid^="stBaseButton"] {
  justify-content:flex-start !important; text-align:left; border-color:transparent !important; background:transparent !important; box-shadow:none !important;
  min-height:30px; padding:.1rem .55rem; border-radius:9px !important; color:#b6e8d0 !important; font-family:var(--mono) !important;
}
[class*="st-key-entry-"] [data-testid^="stBaseButton"] p, [class*="st-key-hit-"] [data-testid^="stBaseButton"] p,
[class*="st-key-entry-"] [data-testid^="stBaseButton"] > div, [class*="st-key-hit-"] [data-testid^="stBaseButton"] > div,
[class*="st-key-scdiff-"] [data-testid^="stBaseButton"] > div, [class*="st-key-prob"] [data-testid^="stBaseButton"] > div,
[class*="st-key-tprob"] [data-testid^="stBaseButton"] > div, div.st-key-up [data-testid^="stBaseButton"] > div,
[class*="st-key-entry-"] [data-testid^="stBaseButton"] > div > span, [class*="st-key-hit-"] [data-testid^="stBaseButton"] > div > span,
[class*="st-key-scdiff-"] [data-testid^="stBaseButton"] > div > span, [class*="st-key-prob"] [data-testid^="stBaseButton"] > div > span,
[class*="st-key-tprob"] [data-testid^="stBaseButton"] > div > span, div.st-key-up [data-testid^="stBaseButton"] > div > span { justify-content:flex-start !important; text-align:left !important; }
[class*="st-key-entry-"] [data-testid^="stBaseButton"] p, [class*="st-key-hit-"] [data-testid^="stBaseButton"] p,
[class*="st-key-scdiff-"] [data-testid^="stBaseButton"] p, [class*="st-key-prob"] [data-testid^="stBaseButton"] p { font:500 12px var(--mono) !important; text-align:left; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
[class*="st-key-entry-"] [data-testid^="stBaseButton"]:hover, [class*="st-key-hit-"] [data-testid^="stBaseButton"]:hover,
[class*="st-key-scdiff-"] [data-testid^="stBaseButton"]:hover, [class*="st-key-prob"] [data-testid^="stBaseButton"]:hover, div.st-key-up [data-testid^="stBaseButton"]:hover {
  background:rgba(43,255,154,.08) !important; color:#fff !important; transform:none; box-shadow:none !important;
}
[class*="st-key-entry-"] [data-testid="stBaseButton-primary"] {
  background:linear-gradient(90deg,rgba(43,255,154,.18),rgba(15,191,107,.10)) !important; color:var(--cyan) !important; font-weight:600 !important;
  box-shadow:inset 2px 0 0 var(--cyan) !important; border:none !important;
}
[class*="st-key-entry-"] [data-testid="stBaseButton-primary"] p { color:var(--cyan) !important; font-weight:600 !important; }

/* ---------- inputs ---------- */
[data-baseweb="input"], [data-baseweb="textarea"], [data-baseweb="select"] > div, [data-baseweb="base-input"] {
  background:rgba(3,14,10,.85) !important; border-color:var(--line) !important; border-radius:11px !important; color:var(--text) !important;
}
[data-baseweb="input"]:focus-within, [data-baseweb="textarea"]:focus-within, [data-baseweb="select"]:focus-within > div {
  border-color:rgba(43,255,154,.7) !important; box-shadow:0 0 0 1px rgba(43,255,154,.3), 0 0 22px rgba(43,255,154,.16) !important;
}
input, textarea { font-family:var(--sans) !important; font-size:13px !important; color:var(--text) !important; }
input::placeholder, textarea::placeholder { color:var(--dim) !important; }
[data-testid="stWidgetLabel"] p, label p { color:var(--muted) !important; font-size:12px !important; }
[data-testid="stCheckbox"] label p { color:var(--text) !important; }

/* ---------- segmented control: mode switch ---------- */
[data-testid="stButtonGroup"] { gap:0 !important; width:100%; }
[data-testid="stButtonGroup"] > div { width:100%; }
div.st-key-modebar [data-testid="stButtonGroup"] > div, div.st-key-modebar [data-testid="stButtonGroup"] { background:rgba(2,10,7,.9); border:1px solid var(--line); border-radius:14px; padding:3px; }
div.st-key-modebar [data-testid^="stBaseButton-segmented_control"] { flex:1; border:none !important; background:transparent !important; border-radius:11px !important; color:var(--muted) !important; letter-spacing:.14em; font-size:11.5px !important; min-height:30px; box-shadow:none !important; transform:none !important; }
div.st-key-modebar [data-testid^="stBaseButton-segmented_control"] p { font:600 11.5px var(--sans) !important; letter-spacing:.14em; }
div.st-key-modebar [data-testid="stBaseButton-segmented_controlActive"] { background:linear-gradient(120deg,rgba(43,255,154,.9),rgba(15,191,107,.9)) !important; color:#020a07 !important; box-shadow:0 0 18px rgba(43,255,154,.35) !important; }
div.st-key-modebar [data-testid="stBaseButton-segmented_controlActive"] p { color:#020a07 !important; }

/* ---------- editor tabs ---------- */
div.st-key-editorarea { height:calc(var(--main-h) - var(--bottom-h)); overflow-y:auto; overflow-x:hidden; gap:0 !important; padding:0; }
div.st-key-tabs { padding:8px 12px 0; background:rgba(3,13,9,.6); border-bottom:1px solid var(--line); }
div.st-key-tabs [data-testid="stButtonGroup"] { background:transparent; border:none; width:auto; overflow-x:auto; flex-wrap:nowrap; padding-bottom:0; }
div.st-key-tabs [data-testid^="stBaseButton-segmented_control"] {
  border:none !important; border-radius:10px 10px 0 0 !important; background:transparent !important; color:var(--muted) !important; min-height:34px; padding:.2rem 1rem; box-shadow:none !important; transform:none !important;
  font:500 12.5px var(--mono) !important; flex:0 0 auto;
}
div.st-key-tabs [data-testid^="stBaseButton-segmented_control"] p { font:500 12.5px var(--mono) !important; }
div.st-key-tabs [data-testid^="stBaseButton-segmented_control"]:hover { color:var(--text) !important; background:rgba(255,255,255,.04) !important; }
div.st-key-tabs [data-testid="stBaseButton-segmented_controlActive"] {
  color:#fff !important; background:linear-gradient(180deg,rgba(43,255,154,.10),rgba(15,191,107,.03)) !important; box-shadow:inset 0 -2px 0 var(--cyan), 0 8px 20px -10px var(--cyan) !important;
}
div.st-key-toolbar { padding:6px 14px; border-bottom:1px solid var(--line); background:rgba(4,18,12,.5); }
div.st-key-toolbar [data-testid="stHorizontalBlock"] { align-items:center; gap:.4rem; }
div.st-key-toolbar [data-testid^="stBaseButton"] { min-height:30px; font-size:12px !important; padding:.2rem .45rem !important; white-space:nowrap; }
div.st-key-toolbar [data-testid^="stBaseButton"] p { font-size:12px !important; white-space:nowrap; overflow:visible; }
div.st-key-toolbar .crumb { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.crumb { font:500 12px var(--mono); color:var(--muted); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.crumb b { color:var(--text); font-weight:600; }
.crumb em { font-style:normal; margin-left:10px; padding:2px 9px; border-radius:999px; font-size:10.5px; letter-spacing:.08em; color:var(--amber); border:1px solid rgba(251,191,36,.35); background:rgba(251,191,36,.08); }
.explorer-path { max-height:72px; overflow:auto; overflow-wrap:anywhere; padding:4px 7px; border:1px solid var(--line); border-radius:8px; background:rgba(2,10,7,.55); color:#a4d8bf; font:10.5px/1.45 var(--mono); }
/* The Ace iframe fills the editor area exactly; the inner editor height is 100vh of that frame. */
div.st-key-editorarea iframe { height:calc(var(--main-h) - var(--bottom-h) - 98px) !important; min-height:140px; border:none; display:block; background:#000; }

/* ---------- welcome screen ---------- */
.hero { height:100%; min-height:260px; display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center; gap:14px; padding:40px 20px; }
.hero .orb { width:88px; height:88px; border-radius:26px; display:grid; place-items:center; font:700 40px var(--mono); color:#020a07; background:var(--grad); box-shadow:0 0 60px rgba(15,191,107,.55), 0 0 120px rgba(43,255,154,.25); animation:float 5s ease-in-out infinite; }
.hero h2 { font:700 26px var(--sans); letter-spacing:.16em; margin:0; background:var(--grad); -webkit-background-clip:text; background-clip:text; color:transparent; }
.hero p { color:var(--muted); font-size:13.5px; max-width:480px; line-height:1.6; }
.hero .keys { display:flex; gap:10px; flex-wrap:wrap; justify-content:center; margin-top:6px; }
.hero .keys span { padding:6px 14px; border-radius:999px; border:1px solid var(--line2); background:rgba(255,255,255,.03); font:500 11.5px var(--mono); color:#b6e8d0; }
@keyframes float { 0%,100% { transform:translateY(0) } 50% { transform:translateY(-8px) } }

/* ---------- bottom panel ---------- */
div.st-key-bottompanel { height:var(--bottom-h); overflow-y:auto; padding:0 14px 10px; background:rgba(2,10,7,.9); backdrop-filter:blur(14px); border-top:1px solid var(--line2); position:relative; }
div.st-key-bottompanel::before { content:""; position:absolute; top:-1px; left:0; right:0; height:1px; background:var(--grad); opacity:.5; }
[data-baseweb="tab-list"] { gap:4px; border-bottom:1px solid var(--line); background:transparent; }
[data-baseweb="tab"] { height:36px; padding:0 14px !important; background:transparent !important; color:var(--muted) !important; }
[data-baseweb="tab"] p { font:600 11px var(--sans) !important; letter-spacing:.16em; }
[data-baseweb="tab"][aria-selected="true"] { color:var(--cyan) !important; }
[data-baseweb="tab"][aria-selected="true"] p { color:var(--cyan) !important; }
[data-baseweb="tab-highlight"] { background:var(--grad) !important; height:2px !important; box-shadow:0 0 10px var(--cyan); }
[data-baseweb="tab-border"] { background:transparent !important; }

/* ---------- code, expanders, alerts ---------- */
[data-testid="stCode"], [data-testid="stCode"] pre, pre { background:rgba(1,8,5,.9) !important; border:1px solid var(--line); border-radius:12px !important; font-size:12px !important; }
:not(pre) > code { background:rgba(15,191,107,.14) !important; color:#a7f3d0 !important; border-radius:6px; padding:.1em .4em; font-size:.88em; }
[data-testid="stExpander"] details { border:1px solid var(--line) !important; border-radius:12px !important; background:var(--panel2); }
[data-testid="stExpander"] summary { padding:.35rem .7rem; }
[data-testid="stExpander"] summary p { font-size:12.5px !important; }
[data-testid="stAlert"] { border-radius:12px; border:1px solid var(--line); background:rgba(255,255,255,.03); }
[data-testid="stVerticalBlockBorderWrapper"] { border-color:var(--line) !important; border-radius:14px; background:var(--panel2); }
[data-testid="stCaptionContainer"], .stCaption { color:var(--muted) !important; font-size:12px; }
[data-testid="stToast"] { background:rgba(5,22,15,.92); border:1px solid var(--line2); border-radius:14px; backdrop-filter:blur(14px); }
[role="dialog"] [data-testid="stVerticalBlock"] { flex:0 0 auto !important; gap:.85rem !important; }
[role="dialog"] [data-testid="stElementContainer"], [role="dialog"] [data-testid="stLayoutWrapper"] { flex:0 0 auto !important; height:auto !important; }
[data-testid="stModal"] [role="dialog"], [data-testid="stDialog"] > div { background:rgba(4,18,12,.96) !important; border:1px solid var(--line2); border-radius:20px; box-shadow:0 30px 90px rgba(0,0,0,.7), 0 0 60px rgba(15,191,107,.2); }
[data-baseweb="popover"] > div { background:rgba(4,18,12,.97) !important; border:1px solid var(--line2); border-radius:14px; backdrop-filter:blur(14px); }
[data-baseweb="menu"], [data-baseweb="menu"] li { background:transparent !important; }

/* ---------- agent panel ---------- */
.agent-title { display:flex; align-items:center; gap:10px; min-width:0; height:34px; color:#e6e6e6; font:600 13px/1.3 Inter,"Segoe UI",system-ui,sans-serif; }
.agent-title > span:last-child { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.agent-title .pulse { width:8px; height:8px; border-radius:50%; background:var(--green); box-shadow:0 0 8px var(--green); flex:none; }
.agent-title .pulse.off { background:var(--red); box-shadow:0 0 8px var(--red); }
div.st-key-agent { background:rgba(4,14,10,.96); border-left-color:#17362a; }
div.st-key-agent [data-testid="stChatMessage"] { border:0; border-bottom:1px solid rgba(255,255,255,.07); border-radius:0; padding:.7rem .25rem; background:transparent !important; color:#e6e6e6; }
div.st-key-agent [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) { border-color:rgba(255,255,255,.09); }
div.st-key-agent [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) { border-color:rgba(255,255,255,.07); }
div.st-key-agent [data-testid^="stChatMessageAvatar"] { border-radius:6px; }
div.st-key-agent div.st-key-agentcomposer { flex:none; padding:8px; border:1px solid #1f4a38; border-radius:13px; background:#0a1a12; box-shadow:0 8px 24px rgba(0,0,0,.24); }
div.st-key-agentcomposer [data-testid="stHorizontalBlock"] { flex-wrap:nowrap !important; gap:.45rem !important; }
div.st-key-agentcomposer [data-baseweb="select"] > div { min-height:30px !important; border-radius:8px !important; background:#0c2018 !important; border-color:#1f4a38 !important; }
div.st-key-agentcomposer [data-testid="stCaptionContainer"] { margin:.25rem .25rem .1rem; }
div.st-key-agentcomposer [data-testid="stCaptionContainer"] p { color:#9a9a9a !important; font-size:10.5px !important; }
div.st-key-agentcomposer [data-testid="stChatInput"] { border-radius:10px !important; border-color:#1f4a38 !important; background:#0c2018 !important; box-shadow:none !important; }
div.st-key-agentcomposer [data-testid="stChatInput"]:focus-within { border-color:#16a34a !important; box-shadow:0 0 0 1px rgba(22,163,74,.35) !important; }
div.st-key-agentcomposer [data-testid="stChatInputSubmitButton"] { background:#16a34a !important; color:#fff !important; border-radius:7px !important; }
.agent-head { display:flex; align-items:center; gap:10px; }
.agent-head .pulse { width:9px; height:9px; border-radius:50%; background:var(--green); box-shadow:0 0 0 0 rgba(52,211,153,.6); animation:pulse 2.2s infinite; flex:none; }
.agent-head .pulse.off { background:var(--red); animation:none; box-shadow:0 0 10px var(--red); }
.agent-head b { font:700 12px var(--sans); letter-spacing:.22em; }
.agent-head small { font:500 10.5px var(--mono); color:var(--muted); margin-left:auto; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
@keyframes pulse { 0% { box-shadow:0 0 0 0 rgba(52,211,153,.55) } 70% { box-shadow:0 0 0 9px rgba(52,211,153,0) } 100% { box-shadow:0 0 0 0 rgba(52,211,153,0) } }
.mode-note { font-size:11.5px; color:var(--muted); padding:0 2px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; flex:none; }
div.st-key-agent > * { flex:none; min-width:0; }
div.st-key-agent > *:has(div.st-key-chat), div.st-key-agent *:has(> div.st-key-chat) { flex:1 1 0 !important; min-height:0; display:flex; flex-direction:column; }
div.st-key-agent div.st-key-chat { flex:1 1 0 !important; min-height:0; overflow-y:auto; overflow-x:hidden; padding:2px 2px 8px; }
[data-testid="stChatMessage"] { border:1px solid var(--line); border-radius:16px; padding:.7rem .8rem; background:var(--panel2); }
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) { background:linear-gradient(135deg,rgba(15,191,107,.16),rgba(184,255,61,.07)); border-color:rgba(15,191,107,.3); }
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) { background:linear-gradient(135deg,rgba(43,255,154,.09),rgba(15,191,107,.05)); border-color:rgba(43,255,154,.22); }
[data-testid^="stChatMessageAvatar"] { border-radius:11px; }
[data-testid="stChatInput"] { border-radius:18px !important; border:1px solid var(--line2) !important; background:rgba(2,10,7,.95) !important; box-shadow:0 0 0 1px rgba(15,191,107,.12), 0 8px 30px rgba(0,0,0,.4); }
[data-testid="stChatInput"]:focus-within { border-color:rgba(43,255,154,.7) !important; box-shadow:0 0 0 1px rgba(43,255,154,.3), 0 0 26px rgba(43,255,154,.2); }
[data-testid="stChatInput"] textarea { font-size:13px !important; }
[data-testid="stChatInputSubmitButton"] { background:var(--grad) !important; border-radius:12px !important; color:#020a07 !important; }
.suggest-title { font:600 10.5px var(--sans); letter-spacing:.2em; color:var(--muted); text-transform:uppercase; margin:6px 2px 2px; }
.intro { text-align:center; padding:26px 8px 10px; }
.intro .orb { width:54px; height:54px; margin:0 auto 12px; border-radius:17px; display:grid; place-items:center; font:700 24px var(--mono); color:#020a07; background:var(--grad); box-shadow:0 0 34px rgba(15,191,107,.5); }
.intro h4 { font:700 15px var(--sans); letter-spacing:.1em; margin:0 0 4px; }
.intro p { color:var(--muted); font-size:12.5px; line-height:1.55; }
div.st-key-suggest [data-testid^="stBaseButton"] { justify-content:flex-start !important; text-align:left; width:100%; min-height:38px; background:rgba(255,255,255,.03) !important; }

/* ---------- status bar ---------- */
div.st-key-statusbar {
  position:fixed; left:0; right:0; bottom:0; height:var(--sb); z-index:999; display:flex; align-items:center; padding:0 !important;
  background:linear-gradient(90deg,rgba(43,255,154,.14),rgba(15,191,107,.16) 55%,rgba(184,255,61,.14)), #04100b; border-top:1px solid var(--line2);
}
div.st-key-statusbar [data-testid="stElementContainer"], div.st-key-statusbar [data-testid="stMarkdownContainer"] { width:100%; }
.sbar { display:flex; align-items:center; justify-content:space-between; width:100%; height:var(--sb); font:500 11.5px var(--mono); color:#bff0d8; padding-right:14px; white-space:nowrap; }
.sbar .grp { display:flex; align-items:center; height:100%; }
.sbar .it { display:flex; align-items:center; gap:7px; height:100%; padding:0 12px; border-right:1px solid rgba(110,255,190,.08); }
.sbar .it.remote { background:var(--grad); color:#020a07; font-weight:700; letter-spacing:.14em; border-right:none; padding:0 16px; }
.sbar .dot { width:7px; height:7px; border-radius:50%; flex:none; }
.sbar .ok { background:var(--green); box-shadow:0 0 8px var(--green); }
.sbar .bad { background:var(--red); box-shadow:0 0 8px var(--red); }
.sbar .warn { background:var(--amber); box-shadow:0 0 8px var(--amber); }
.sbar .idle { background:var(--muted); }
.sbar .mut { color:var(--muted); }

/* ---------- layering: tooltips, menus and dialogs always sit above every panel ---------- */
div.st-key-shell { position:relative; z-index:1; }
[data-baseweb="tooltip"], [data-baseweb="popover"], [data-baseweb="layer"], [role="tooltip"], [data-testid="stTooltipContent"] { z-index:5000 !important; }
[data-testid="stToastContainer"], [data-testid="stToast"] { z-index:6000 !important; }
/* Tooltips are drawn by layout.py (above the element, on top of everything); Streamlit's own copy is only used as the text source. */
div:has(> [data-testid="stTooltipContent"]) { opacity:0 !important; pointer-events:none !important; }
.rk-tip {
  position:fixed; z-index:2147483000; left:0; top:0; display:none; max-width:300px; padding:6px 10px; border-radius:8px; pointer-events:none;
  font:500 12px/1.4 var(--sans); color:#e6fff3; background:#07170f; border:1px solid rgba(15,191,107,.55); box-shadow:0 8px 26px rgba(0,0,0,.6); white-space:normal; overflow-wrap:anywhere;
}
.rk-tip::after { content:""; position:absolute; left:var(--ax,50%); width:8px; height:8px; margin-left:-4px; background:#07170f; transform:rotate(45deg); }
.rk-tip.above::after { bottom:-5px; border-right:1px solid rgba(15,191,107,.55); border-bottom:1px solid rgba(15,191,107,.55); }
.rk-tip.below::after { top:-5px; border-left:1px solid rgba(15,191,107,.55); border-top:1px solid rgba(15,191,107,.55); }
[data-testid="stModal"], [data-testid="stDialog"] { z-index:5500 !important; }

/* ---------- hosted-platform chrome ("Manage app" etc.) must never cover the agent input ---------- */
[class*="viewerBadge"], [class*="_viewerBadge"], [data-testid="manage-app-button"], [data-testid="stAppDeployButton"], [class*="stDeployButton"],
[class*="_terminalButton_"], [class*="_profileContainer_"], [class*="_profilePreview_"], .viewerBadge_container__r5tak, .styles_viewerBadge__CvC9N,
a[href*="streamlit.io/cloud"][class*="badge" i] { display:none !important; visibility:hidden !important; pointer-events:none !important; }
[data-testid="stElementContainer"]:has(> iframe[height="0"]), [data-testid="stElementContainer"]:has(> div > iframe[height="0"]) { display:none !important; }

/* ---------- resizable panes ---------- */
.rk-split { position:fixed; z-index:1500; touch-action:none; user-select:none; }
.rk-split.v { width:12px; cursor:col-resize; }
.rk-split.h { height:12px; cursor:row-resize; }
.rk-split .grip { position:absolute; background:transparent; transition:background .15s, box-shadow .15s; pointer-events:none; }
.rk-split.v .grip { top:0; bottom:0; left:5px; width:2px; }
.rk-split.h .grip { left:0; right:0; top:5px; height:2px; }
.rk-split:hover .grip, .rk-split.drag .grip { background:var(--cyan); box-shadow:0 0 12px var(--cyan); }
.rk-split .btns { position:absolute; display:flex; gap:4px; }
.rk-split.v .btns { top:14px; left:-3px; flex-direction:column; }
.rk-split.h .btns { right:16px; top:-3px; flex-direction:row; }
.rk-split button {
  width:18px; height:18px; padding:0; border-radius:50%; border:1px solid var(--line2); background:rgba(4,18,12,.94); color:var(--muted);
  font:700 11px/1 var(--mono); cursor:pointer; display:grid; place-items:center; opacity:.6; transition:all .15s;
}
.rk-split:hover button { opacity:1; }
.rk-split button:hover { color:#020a07; background:var(--cyan); border-color:var(--cyan); box-shadow:0 0 12px rgba(43,255,154,.6); }
html.rk-dragging, html.rk-dragging * { user-select:none !important; cursor:inherit; }
html.rk-dragging iframe { pointer-events:none !important; }
html.rk-no-side [data-testid="stColumn"]:has(div.st-key-sidebar), html.rk-no-agent [data-testid="stColumn"]:has(div.st-key-agent) { overflow:hidden; }
html.rk-no-side div.st-key-sidebar, html.rk-no-agent div.st-key-agent { visibility:hidden; padding-left:0; padding-right:0; border:none; }
html.rk-no-bottom div.st-key-bottompanel { display:none; }

/* ---------- agent: live activity ---------- */
div.st-key-runinput { flex:none; padding:7px 7px 7px 14px; border-radius:18px; border:1px solid rgba(43,255,154,.45); background:rgba(2,10,7,.95); box-shadow:0 0 0 1px rgba(43,255,154,.18), 0 0 22px rgba(43,255,154,.14); }
div.st-key-runinput [data-testid="stHorizontalBlock"] { flex-wrap:nowrap !important; align-items:center; gap:.5rem !important; }
div.st-key-runinput [data-testid="stColumn"]:last-child { flex:0 0 40px !important; width:40px !important; min-width:40px !important; }
.runinput-text { display:flex; align-items:center; gap:9px; color:var(--muted); font:500 12.5px var(--sans); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
div.st-key-agent_stop_input [data-testid^="stBaseButton"] { width:40px; height:40px; min-height:40px; padding:0 !important; border-radius:12px !important; border:none !important; color:#fff !important; background:linear-gradient(135deg,#ef4444,#fb7185) !important; box-shadow:0 0 16px rgba(239,68,68,.45) !important; }
div.st-key-agent_stop_input [data-testid^="stBaseButton"]:hover { filter:brightness(1.12); box-shadow:0 0 24px rgba(239,68,68,.7) !important; }
div.st-key-agent_stop_input [data-testid="stIconMaterial"] { font-size:22px !important; }
div.st-key-modebar { flex:none; }
div.st-key-agent [data-baseweb="select"] > div { min-height:32px !important; font-size:12px; }
.runbar { display:flex; align-items:center; gap:8px; padding:6px 10px; border-radius:10px; border:1px solid rgba(43,255,154,.3); background:linear-gradient(90deg,rgba(43,255,154,.10),rgba(15,191,107,.07)); font:600 12px var(--sans); color:var(--text); }
.runbar .st { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; min-width:0; }
.runbar .meta { margin-left:auto; font:500 11px var(--mono); color:var(--muted); white-space:nowrap; flex:none; }
.spin { width:12px; height:12px; flex:none; border-radius:50%; border:2px solid rgba(43,255,154,.25); border-top-color:var(--cyan); animation:spin .8s linear infinite; }
@keyframes spin { to { transform:rotate(360deg) } }
.think { font:italic 11.5px var(--sans); color:var(--muted); margin:6px 0 2px; max-height:3.4em; overflow:hidden; line-height:1.45; }
.timeline { display:flex; flex-direction:column; gap:2px; margin:6px 0; padding:6px 6px; border:1px solid var(--line); border-radius:12px; background:rgba(1,8,5,.55); }
.act { display:flex; align-items:center; gap:7px; padding:2px 5px; border-radius:7px; font:500 11.5px var(--mono); min-width:0; line-height:1.5; }
.act.write { background:rgba(251,191,36,.08); }
.act .ic { width:14px; height:14px; flex:none; border-radius:50%; display:grid; place-items:center; font:700 9px var(--mono); }
.act.ok .ic { background:rgba(52,211,153,.18); color:var(--green); } .act.ok .ic::before { content:"\\2713"; }
.act.fail .ic { background:rgba(251,113,133,.2); color:var(--red); } .act.fail .ic::before { content:"\\2715"; }
.act.run .ic { border:2px solid rgba(43,255,154,.25); border-top-color:var(--cyan); animation:spin .8s linear infinite; }
.act .verb { color:var(--muted); flex:none; }
.act.write .verb { color:var(--amber); } .act.exec .verb { color:var(--violet); }
.act code.tgt { flex:1 1 auto; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; background:none !important; padding:0 !important; color:#a7f3d0 !important; }
.act .res { color:var(--dim); flex:0 1 auto; max-width:32%; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.act .dur { color:var(--dim); flex:none; font-size:10.5px; }
/* agent review card (approve / revert): dark card, sans font, blue primary action */
div[class*="st-key-review_"], div[class*="st-key-approval_"] {
  background:#0a1a12 !important; border:1px solid #17362a !important; border-radius:12px !important; padding:.75rem .85rem !important;
  box-shadow:0 10px 26px -18px rgba(0,0,0,.8);
}
div[class*="st-key-review_"] *, div[class*="st-key-approval_"] * { font-family:Inter,"Segoe UI",system-ui,sans-serif !important; }
div[class*="st-key-review_"] code, div[class*="st-key-approval_"] code { font-family:var(--mono) !important; }
/* the blanket font above must never reach Streamlit's icon glyphs, or their names ("keyboard_arrow_right") are printed over the text */
div[class*="st-key-review_"] [data-testid="stIconMaterial"], div[class*="st-key-approval_"] [data-testid="stIconMaterial"],
div[class*="st-key-review_"] [data-testid="stExpanderIcon"], div[class*="st-key-approval_"] [data-testid="stExpanderIcon"],
div.st-key-agent [data-testid="stIconMaterial"], div.st-key-agent [data-testid="stExpanderIcon"] {
  font-family:"Material Symbols Rounded","Material Symbols Outlined","Material Icons" !important; font-feature-settings:"liga" 1; flex:none; overflow:hidden; white-space:nowrap; letter-spacing:normal; text-transform:none;
}
div.st-key-agent [data-testid="stExpander"] summary { display:flex; align-items:center; gap:.5rem; }
div.st-key-agent [data-testid="stExpander"] summary p { overflow-wrap:anywhere; word-break:break-word; min-width:0; line-height:1.4; }
/* review and approval cards: nothing may overflow or overlap in a narrow panel */
div[class*="st-key-review_"] code, div[class*="st-key-approval_"] code { white-space:pre-wrap !important; overflow-wrap:anywhere; word-break:break-word; font-size:11px !important; }
div[class*="st-key-review_"] [data-testid="stHorizontalBlock"], div[class*="st-key-approval_"] [data-testid="stHorizontalBlock"] { flex-wrap:wrap !important; gap:.4rem !important; }
div[class*="st-key-review_"] [data-testid="stColumn"], div[class*="st-key-approval_"] [data-testid="stColumn"] { flex:1 1 110px !important; min-width:110px !important; width:auto !important; }
div[class*="st-key-review_"] [data-testid^="stBaseButton"], div[class*="st-key-approval_"] [data-testid^="stBaseButton"] { min-height:30px; height:auto; padding:.2rem .6rem; }
div[class*="st-key-review_"] [data-testid^="stBaseButton"] p, div[class*="st-key-approval_"] [data-testid^="stBaseButton"] p { font-size:12px !important; white-space:normal; line-height:1.3; }
div[class*="st-key-approval_"] [data-testid="stMarkdownContainer"] p { font-size:12px !important; line-height:1.5; overflow-wrap:anywhere; }
div[class*="st-key-approval_"] [data-testid="stMarkdownContainer"] p:first-child strong { font-size:12.5px; }
/* agent answers and outputs: compact text */
div.st-key-agent [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] p, div.st-key-agent [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] li { font-size:12.5px !important; line-height:1.55; }
div.st-key-agent [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] h1 { font-size:15px !important; margin:.5rem 0 .3rem; padding:0; }
div.st-key-agent [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] h2 { font-size:14px !important; margin:.45rem 0 .25rem; padding:0; }
div.st-key-agent [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] h3, div.st-key-agent [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] h4 { font-size:13px !important; margin:.4rem 0 .2rem; padding:0; }
div.st-key-agent [data-testid="stChatMessage"] code, div.st-key-agent [data-testid="stCode"] pre, div.st-key-agent [data-testid="stCode"] code { font-size:11.5px !important; line-height:1.5; }
div.st-key-agent [data-testid="stCaptionContainer"] p { font-size:11px !important; }
div.st-key-agent [data-testid="stExpander"] summary p { font-size:12px !important; }
div.st-key-agent [data-testid="stAlert"] p { font-size:12px !important; }
div.st-key-agent [data-testid="stChatInput"] textarea { font-size:12.5px !important; }
.rev-head { display:flex; align-items:center; flex-wrap:wrap; gap:6px 10px; font-size:12.5px; color:#e6e6e6; margin:0 0 .5rem; }
.rev-title { font-weight:600; letter-spacing:.01em; }
.rev-stat { font-size:12px; color:#9a9a9a; } .rev-stat i { font-style:normal; font-weight:600; }
.rev-stat i.add { color:#4ade80; } .rev-stat i.del { color:#f87171; }
.rev-pill { margin-left:auto; padding:2px 10px; border-radius:999px; font-size:11px; font-weight:600; color:#fff; background:#16a34a; white-space:nowrap; }
.rev-pill.wait { background:#16a34a; } .rev-pill.run { background:#52525b; } .rev-pill.ok { background:#16a34a; } .rev-pill.rev { background:#52525b; color:#e4e4e7; }
div[class*="st-key-review_"] [data-testid="stBaseButton-primary"], div[class*="st-key-approval_"] [data-testid="stBaseButton-primary"] {
  background:#16a34a !important; border:1px solid #16a34a !important; color:#fff !important; box-shadow:none !important; filter:none !important;
}
div[class*="st-key-review_"] [data-testid="stBaseButton-primary"]:hover, div[class*="st-key-approval_"] [data-testid="stBaseButton-primary"]:hover {
  background:#15803d !important; border-color:#15803d !important; box-shadow:none !important; filter:none !important;
}
div[class*="st-key-review_"] [data-testid="stBaseButton-primary"] p, div[class*="st-key-approval_"] [data-testid="stBaseButton-primary"] p { color:#fff !important; }
div[class*="st-key-review_"] [data-testid="stBaseButton-secondary"], div[class*="st-key-approval_"] [data-testid="stBaseButton-secondary"] {
  background:#10281d !important; border:1px solid #1f4a38 !important; color:#e6e6e6 !important; box-shadow:none !important; border-radius:8px !important;
}
div[class*="st-key-review_"] [data-testid="stBaseButton-secondary"]:hover, div[class*="st-key-approval_"] [data-testid="stBaseButton-secondary"]:hover { background:#17362a !important; }
div[class*="st-key-review_"] [data-testid="stBaseButton-secondary"] p, div[class*="st-key-approval_"] [data-testid="stBaseButton-secondary"] p { color:#e6e6e6 !important; }
div[class*="st-key-review_"] [data-testid="stExpander"] { background:#07130d !important; border:1px solid #17362a !important; border-radius:9px !important; }
div[class*="st-key-review_"] [data-testid="stExpander"] summary p { font-size:12.5px !important; color:#e6e6e6 !important; }
div[class*="st-key-review_"] [data-testid="stCaptionContainer"] p, div[class*="st-key-approval_"] [data-testid="stCaptionContainer"] p { color:#9fc9b4 !important; }
.pending-banner { flex:none; padding:6px 10px; border-radius:10px; border:1px solid rgba(251,191,36,.4); background:rgba(251,191,36,.08); color:var(--amber); font:500 12px var(--sans); }

/* ---------- terminal ---------- */
.term { padding:0; }
.term pre, .term [data-testid="stMarkdownPre"] { display:block; margin:0 !important; padding:0 !important; border:none !important; background:transparent !important; color:#d4d4d4; white-space:pre-wrap !important; word-break:break-word; font:12.5px/1.5 var(--mono) !important; }
.term .ps, .termps { color:#e6edf7; font-weight:600; }
.term .cmd { color:#6ee7b7; }
.term .dim { color:var(--dim); }
.term .hint { color:var(--amber); }
.term .gap { display:inline-block; height:.6em; }
/* the whole terminal is one scrolling console: history, then "PS <folder>>" with the input on the same line */
div.st-key-termbox { height:calc(var(--bottom-h) - 74px) !important; min-height:60px; overflow-y:auto; overflow-x:hidden; display:block !important; padding:8px 12px; border:1px solid var(--line); border-radius:12px; background:#030d08; }
div.st-key-termbox > [data-testid="stElementContainer"], div.st-key-termbox [data-testid="stMarkdownContainer"] { width:100%; }
div.st-key-termbox [data-testid="stMarkdownContainer"] p { margin:0; }
div.st-key-termbox [data-testid="stForm"] .termps, .termps { font:600 12.5px/1.5 var(--mono) !important; }
div.st-key-termbox [data-testid="stForm"] { position:relative; display:block; padding:0 !important; border:none !important; font:12.5px/1.5 var(--mono); }
/* every Streamlit wrapper around the prompt and the input is removed from the layout, so both flow as one line of text and the input follows the last line of a wrapped prompt */
div.st-key-termbox [data-testid="stForm"] [data-testid="stVerticalBlock"],
div.st-key-termbox [data-testid="stForm"] [data-testid="stElementContainer"]:not(:has([data-testid="stFormSubmitButton"])),
div.st-key-termbox [data-testid="stForm"] [data-testid="stMarkdown"], div.st-key-termbox [data-testid="stForm"] [data-testid="stMarkdown"] div,
div.st-key-termbox [data-testid="stForm"] [data-testid="stTextInput"], div.st-key-termbox [data-testid="stForm"] [data-testid="stTextInput"] > div,
div.st-key-termbox [data-testid="stTextInputRootElement"] { display:contents !important; }
div.st-key-termbox [data-testid="stForm"] [data-testid="stMarkdownContainer"] p { display:inline !important; font:12.5px/1.5 var(--mono) !important; overflow-wrap:anywhere; }
div.st-key-termbox [data-testid="stForm"] .termps { margin-right:.7ch; }
div.st-key-termbox [data-testid="stForm"] [data-testid="stWidgetLabel"], div.st-key-termbox [data-testid="stTextInputRootElement"] > div { display:none !important; }
div.st-key-termbox [data-testid="stForm"] [data-testid="stElementContainer"]:has([data-testid="stFormSubmitButton"]) { position:absolute; width:1px !important; height:1px; overflow:hidden; opacity:0; pointer-events:none; }
div.st-key-termbox [data-testid="stTextInput"] [data-baseweb="input"], div.st-key-termbox [data-testid="stTextInput"] [data-baseweb="base-input"] { background:transparent !important; border:none !important; box-shadow:none !important; min-height:0 !important; }
div.st-key-termbox [data-testid="stTextInput"] input { display:inline-block; field-sizing:content; width:auto !important; min-width:10ch; max-width:100%; vertical-align:baseline; padding:0 !important; height:19px; min-height:0; font:12.5px/1.5 var(--mono) !important; color:#6ee7b7 !important; caret-color:#d4d4d4; caret-shape:block; background:transparent !important; border:none !important; outline:none !important; box-shadow:none !important; }
div.st-key-termbox [data-testid="stTextInput"] input::placeholder { color:var(--dim); opacity:.55; }
div.st-key-termbox [data-testid="stTextInputRootElement"], div.st-key-termbox [data-testid="stTextInputRootElement"]:focus-within { border:none !important; box-shadow:none !important; outline:none !important; background:transparent !important; }
div.st-key-termbox [data-testid="InputInstructions"] { display:none !important; }
</style>
"""


def inject_theme() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def section_title(title: str, right: str = "") -> None:
    st.markdown(f"<div class='sec'><b>{escape(title)}</b><span>{escape(right)}</span></div>", unsafe_allow_html=True)
