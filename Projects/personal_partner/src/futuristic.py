"""Futuristic dark theme layer for WithYou.

This stylesheet is injected after APP_CSS and WELCOME_CSS, so it only changes colors,
surfaces, borders, and glow effects. Class names, widget keys, and layout stay the same.
Romantic mode keeps its rose palette and is re-themed in dark rose.
"""

FUTURISTIC_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&display=swap');

:root {
  color-scheme: dark;
  --ks-ink: #f3ecff;
  --ks-muted: #a99bc7;
  --ks-line: rgba(168,85,247,.20);
  --ks-line-strong: #5b3a8c;
  --ks-paper: #08040f;
  --ks-panel: #130a22;
  --ks-sidebar: #0d0718;
  --ks-brand: #a855f7;
  --ks-brand-dark: #d8b4fe;
  --ks-teal: #c084fc;
  --ks-cream: rgba(251,191,36,.08);
  --ks-accent: #e879f9;
  --ks-soft: rgba(168,85,247,.10);
  --ks-peach: rgba(217,70,239,.12);
  --ks-peach-ink: #f0d9ff;
  --ks-link: #d8b4fe;
  --ks-focus: #f0abfc;
  --ks-disabled-bg: #1a1030;
  --ks-disabled-ink: #7d6c9c;
  --ks-field: #0f0820;
  --ks-card: rgba(19,10,34,.78);
  --ks-glow: rgba(168,85,247,.38);
  --ks-btn-grad: linear-gradient(120deg, #6d28d9 0%, #86198f 100%);
  --ks-chat-head: linear-gradient(135deg, rgba(109,40,217,.30) 0%, rgba(134,25,143,.26) 60%, rgba(19,10,34,.92) 100%);
  --ks-user-bubble: linear-gradient(135deg, rgba(109,40,217,.30) 0%, rgba(134,25,143,.26) 100%);
}

/* Canvas: neon grid with soft purple and magenta light */
.stApp, [data-testid="stAppViewContainer"] {
  background:
    linear-gradient(rgba(168,85,247,.045) 1px, transparent 1px) 0 0 / 44px 44px,
    linear-gradient(90deg, rgba(168,85,247,.045) 1px, transparent 1px) 0 0 / 44px 44px,
    radial-gradient(900px 520px at 92% -8%, rgba(217,70,239,.22), transparent 62%),
    radial-gradient(820px 520px at -8% 12%, rgba(168,85,247,.16), transparent 60%),
    #08040f !important;
}
[data-testid="stHeader"] { background: rgba(8,4,15,.72) !important; -webkit-backdrop-filter: blur(10px); backdrop-filter: blur(10px); }
[data-testid="stMain"], [data-testid="stHeader"] { color: var(--ks-ink); }
[data-testid="stBottom"], [data-testid="stBottom"] > div, [data-testid="stBottomBlockContainer"] {
  background: linear-gradient(to top, #08040f 62%, rgba(8,4,15,0)) !important;
}
.stApp h1, .stApp h2, .stApp h3, .stApp h4 { font-family: 'Space Grotesk', system-ui, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif; text-shadow: 0 0 22px rgba(168,85,247,.12); }
[data-testid="stSidebar"], [data-testid="stSidebar"] > div {
  background: linear-gradient(180deg, #130a22 0%, #08040f 100%);
  border-right: 1px solid var(--ks-line);
  box-shadow: 0 0 36px -18px rgba(168,85,247,.45);
}
.stApp [data-testid="stCaptionContainer"], .stApp [data-testid="stCaptionContainer"] p { color: var(--ks-muted); }
.stApp [data-testid="stMarkdownContainer"] a, .stApp a:not([data-testid^="stBaseButton"]) { color: var(--ks-link); text-shadow: 0 0 12px rgba(216,180,254,.25); }
hr { border-color: var(--ks-line); }

/* Inputs */
[data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea, [data-testid="stChatInput"] textarea,
[data-testid="stSelectbox"] div[data-baseweb="select"] > div, [data-testid="stMultiSelect"] div[data-baseweb="select"] > div,
div[data-baseweb="input"], div[data-baseweb="base-input"], div[data-baseweb="textarea"] {
  background: var(--ks-field) !important; color: var(--ks-ink) !important; -webkit-text-fill-color: var(--ks-ink);
  border-color: var(--ks-line-strong) !important; caret-color: var(--ks-brand);
}
[data-testid="stTextInput"] input::placeholder, [data-testid="stTextArea"] textarea::placeholder,
[data-testid="stChatInput"] textarea::placeholder { color: #8b7aab !important; -webkit-text-fill-color: #8b7aab; opacity: 1; }
input:-webkit-autofill, input:-webkit-autofill:hover, input:-webkit-autofill:focus {
  -webkit-text-fill-color: var(--ks-ink); box-shadow: 0 0 0 1000px #0f0820 inset;
}
[data-testid="stTextInput"] input:focus, [data-testid="stTextArea"] textarea:focus,
[data-testid="stSelectbox"] div[data-baseweb="select"]:focus-within, div[data-baseweb="input"]:focus-within {
  border-color: var(--ks-brand) !important; box-shadow: 0 0 0 1px var(--ks-brand), 0 0 18px var(--ks-glow) !important;
}
[data-testid="stSelectbox"] svg, [data-testid="stMultiSelect"] svg { fill: var(--ks-brand-dark); color: var(--ks-brand-dark); }

/* Dropdown menus (rendered outside .stApp) */
div[data-baseweb="popover"], div[data-baseweb="popover"] > div, div[data-baseweb="menu"],
ul[role="listbox"], [data-baseweb="select"] ul {
  background: #130a22 !important; color: var(--ks-ink) !important; border: 1px solid var(--ks-line);
}
li[role="option"] { background: #130a22; }
span[data-baseweb="tag"] { background: var(--ks-btn-grad) !important; }

/* Buttons */
.stApp [data-testid="stBaseButton-secondary"], .stApp [data-testid="stBaseButton-secondaryFormSubmit"],
.stApp [data-testid="stBaseButton-tertiary"], .stApp .stDownloadButton > button, .stApp .stLinkButton > a {
  background: var(--ks-card) !important; border: 1px solid rgba(168,85,247,.35) !important;
  color: var(--ks-ink) !important; -webkit-text-fill-color: var(--ks-ink);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.04);
}
.stApp [data-testid="stBaseButton-secondary"]:hover, .stApp [data-testid="stBaseButton-secondaryFormSubmit"]:hover,
.stApp [data-testid="stBaseButton-tertiary"]:hover, .stApp .stDownloadButton > button:hover, .stApp .stLinkButton > a:hover {
  background: rgba(168,85,247,.12) !important; border-color: var(--ks-brand) !important;
  color: var(--ks-brand-dark) !important; -webkit-text-fill-color: var(--ks-brand-dark);
  box-shadow: 0 0 18px var(--ks-glow);
}
.stApp [data-testid="stBaseButton-primary"], .stApp [data-testid="stBaseButton-primaryFormSubmit"] {
  background: var(--ks-btn-grad) !important; border: 1px solid rgba(255,255,255,.14) !important;
  color: #ffffff !important; -webkit-text-fill-color: #ffffff; box-shadow: 0 10px 26px -12px var(--ks-glow);
}
.stApp [data-testid="stBaseButton-primary"]:hover, .stApp [data-testid="stBaseButton-primaryFormSubmit"]:hover {
  background: var(--ks-btn-grad) !important; border-color: rgba(255,255,255,.3) !important;
  color: #ffffff !important; -webkit-text-fill-color: #ffffff; filter: brightness(1.12); box-shadow: 0 0 26px var(--ks-glow);
}
.stApp button:disabled, .stApp [data-testid^="stBaseButton"]:disabled, .stApp .stLinkButton > a[aria-disabled="true"] {
  background: var(--ks-disabled-bg) !important; border-color: #3b2a5c !important; color: var(--ks-disabled-ink) !important;
  -webkit-text-fill-color: var(--ks-disabled-ink); box-shadow: none;
}
.stApp button:focus-visible, .stApp a:focus-visible, .stApp input:focus-visible, .stApp textarea:focus-visible {
  outline: 2px solid var(--ks-focus) !important; outline-offset: 2px; box-shadow: 0 0 14px rgba(240,171,252,.45);
}
[data-testid="stChatInputSubmitButton"] { color: var(--ks-brand) !important; background: transparent !important; }
[data-testid="stChatInputSubmitButton"]:hover { color: #ffffff !important; background: var(--ks-btn-grad) !important; border-radius: 12px; }

/* Containers and chat */
[data-testid="stExpander"] details, [data-testid="stForm"] { background: var(--ks-panel); border: 1px solid var(--ks-line); border-radius: 14px; }
[data-testid="stChatInput"] {
  background: var(--ks-field); border: 1px solid var(--ks-line-strong); border-radius: 16px;
  box-shadow: 0 0 0 1px rgba(168,85,247,.06), 0 18px 40px -26px rgba(0,0,0,.9);
}
[data-testid="stChatInput"]:focus-within { border-color: var(--ks-brand); box-shadow: 0 0 0 1px var(--ks-brand), 0 0 24px var(--ks-glow); }
[data-testid="stChatInput"] textarea { background: transparent !important; }
[data-testid="stChatMessage"] {
  background: var(--ks-card); border: 1px solid var(--ks-line); border-radius: 18px;
  box-shadow: 0 16px 36px -28px rgba(0,0,0,.9); -webkit-backdrop-filter: blur(6px); backdrop-filter: blur(6px);
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) { background: var(--ks-user-bubble); border-color: rgba(168,85,247,.32); }
.ks-chat-head {
  background: var(--ks-chat-head); border: 1px solid var(--ks-line);
  box-shadow: inset 0 1px 0 rgba(168,85,247,.35), 0 22px 50px -32px rgba(168,85,247,.5);
}
.ks-chat-head p { color: var(--ks-muted); }
.ks-eyebrow { color: var(--ks-brand-dark); text-shadow: 0 0 12px rgba(216,180,254,.35); }
.ks-chip { background: rgba(168,85,247,.10); border-color: rgba(168,85,247,.30); color: var(--ks-brand-dark); }
.ks-chip.rose { background: rgba(244,114,182,.12); border-color: rgba(244,114,182,.35); color: #fbcfe8; }
.ks-note { background: var(--ks-cream); border: 1px solid rgba(251,191,36,.30); color: #fde68a !important; }
.ks-card { background: var(--ks-card); border-color: var(--ks-line); }
.ks-feature { background: var(--ks-card); border-color: var(--ks-line); box-shadow: 0 14px 30px -24px rgba(0,0,0,.9); }
.ks-feature-icon { background: rgba(168,85,247,.10); }
.ks-feature-icon svg, .ks-w-icon svg { stroke: var(--ks-brand-dark); }
.ks-footer strong { color: var(--ks-brand-dark); }
.ks-brand { color: var(--ks-brand-dark); }
.ks-brand svg circle:nth-of-type(1), .ks-w-mhead svg circle:nth-of-type(1) { fill: #a855f7; }
.ks-brand svg circle:nth-of-type(2), .ks-w-mhead svg circle:nth-of-type(2) { fill: #e879f9; }
.ks-brand svg path, .ks-w-mhead svg path { fill: #f0abfc; }

/* Welcome page */
.st-key-ks_nav { background: rgba(13,7,26,.72); border: 1px solid var(--ks-line); box-shadow: 0 14px 34px -22px rgba(168,85,247,.35); }
.st-key-ks_herobox {
  background: radial-gradient(120% 120% at 100% 0%, rgba(217,70,239,.20) 0%, rgba(217,70,239,0) 55%),
    linear-gradient(135deg, #130a22 0%, #1a0b2e 55%, #120a24 100%);
  border: 1px solid var(--ks-line); box-shadow: 0 0 60px -30px rgba(168,85,247,.45), 0 22px 44px -32px rgba(0,0,0,.9);
}
.ks-w-badge { background: rgba(13,7,26,.78); border: 1px solid var(--ks-line); color: var(--ks-brand-dark); box-shadow: 0 0 18px -10px rgba(168,85,247,.8); }
.ks-w-badge i { background: var(--ks-btn-grad); }
.ks-w-grad { background: linear-gradient(100deg, #a855f7 0%, #e879f9 55%, #f0abfc 100%); -webkit-background-clip: text; background-clip: text; }
.st-key-welcome_login [data-testid^="stBaseButton"] {
  background: var(--ks-btn-grad) !important; border: 0 !important; box-shadow: 0 0 26px -10px var(--ks-glow);
}
.stApp .st-key-welcome_login [data-testid^="stBaseButton"] {
  background: var(--ks-btn-grad) !important; border: 0 !important; box-shadow: 0 0 26px -10px var(--ks-glow);
}
.stApp .st-key-welcome_login [data-testid^="stBaseButton"]:hover {
  background: var(--ks-btn-grad) !important; box-shadow: 0 0 34px -8px var(--ks-glow); filter: brightness(1.12);
}
.stApp .st-key-welcome_signup [data-testid^="stBaseButton"] {
  background: var(--ks-card) !important; border: 1.5px solid var(--ks-brand) !important; color: var(--ks-brand-dark) !important;
  -webkit-text-fill-color: var(--ks-brand-dark); box-shadow: 0 0 20px -12px var(--ks-glow);
}
.stApp .st-key-welcome_signup [data-testid^="stBaseButton"]:hover { background: rgba(168,85,247,.12) !important; }
.stApp .st-key-welcome_google [data-testid^="stBaseButton"], .stApp .st-key-welcome_github a {
  background: var(--ks-card) !important; border: 1px solid rgba(168,85,247,.30) !important;
}
.ks-w-mock {
  background: linear-gradient(180deg, rgba(22,12,40,.96) 0%, rgba(12,6,24,.96) 100%); border: 1px solid rgba(168,85,247,.30);
  box-shadow: 0 40px 70px -34px rgba(0,0,0,.9), 0 0 60px -20px rgba(168,85,247,.35);
}
.ks-w-mhead { border-bottom: 1px solid var(--ks-line); }
.ks-w-msg.me { background: var(--ks-btn-grad); }
.ks-w-blob.b1 { background: rgba(217,70,239,.45); }
.ks-w-blob.b2 { background: rgba(168,85,247,.38); }
.ks-w-chip { background: var(--ks-card); border: 1px solid rgba(168,85,247,.30); color: var(--ks-ink); box-shadow: 0 0 22px -12px rgba(168,85,247,.8); }
.ks-w-chip.c2 svg { fill: #f0abfc; stroke: #f0abfc; }
.ks-w-card {
  background: var(--ks-card); border: 1px solid var(--ks-line);
  box-shadow: 0 18px 36px -30px rgba(0,0,0,.9);
}
.ks-w-card:hover { border-color: rgba(168,85,247,.55); box-shadow: 0 0 34px -12px var(--ks-glow), 0 28px 44px -28px rgba(0,0,0,.9); }
.ks-w-icon { background: linear-gradient(135deg, rgba(168,85,247,.18), rgba(217,70,239,.18)); border: 1px solid rgba(168,85,247,.35); }
.ks-w-trust svg { stroke: var(--ks-brand-dark); }
.ks-w-footer { border-top: 1px solid var(--ks-line); }

/* Login, create account, reset */
.st-key-ks_auth, .st-key-ks_authpage {
  background: var(--ks-card); border: 1px solid var(--ks-line);
  box-shadow: 0 0 60px -30px rgba(168,85,247,.45), 0 22px 44px -32px rgba(0,0,0,.9);
}
.ks-authhead {
  background: radial-gradient(120% 120% at 100% 0%, rgba(217,70,239,.20) 0%, rgba(217,70,239,0) 55%),
    linear-gradient(135deg, #130a22 0%, #1a0b2e 55%, #120a24 100%);
  border: 1px solid var(--ks-line);
}
.ks-badge { background: var(--ks-btn-grad); box-shadow: 0 0 18px -6px var(--ks-glow); }
.st-key-ks_authpage [data-baseweb="input"], .st-key-ks_authpage [data-baseweb="base-input"] { background: var(--ks-field); }
.st-key-ks_authpage [data-baseweb="input"]:focus-within { border-color: var(--ks-brand); box-shadow: 0 0 0 1px var(--ks-brand), 0 0 18px var(--ks-glow); }
.stApp :is(.st-key-create_to_login, .st-key-login_to_signup) [data-testid^="stBaseButton"] {
  background: var(--ks-card) !important; border: 1.5px solid var(--ks-brand) !important;
  color: var(--ks-brand-dark) !important; box-shadow: 0 0 20px -12px var(--ks-glow) !important;
}
.stApp :is(.st-key-create_to_login, .st-key-login_to_signup) [data-testid^="stBaseButton"]:hover {
  background: var(--ks-btn-grad) !important; color: #ffffff !important; border-color: transparent !important;
}
.stApp :is(.st-key-create_to_login, .st-key-login_to_signup) [data-testid^="stBaseButton"]:hover p { color: #ffffff !important; }
.st-key-ks_authlinks { border-top: 1px solid var(--ks-line); }

/* Romantic mode: dark rose palette, applied only while the flag is rendered */
.stApp:has(.ks-romantic-flag) {
  --ks-ink: #fff1f6;
  --ks-muted: #cfa0b4;
  --ks-line: rgba(232,80,143,.26);
  --ks-line-strong: #8a2f58;
  --ks-paper: #10030a;
  --ks-panel: #1c0813;
  --ks-sidebar: #140510;
  --ks-brand: #e8508f;
  --ks-brand-dark: #fcc5da;
  --ks-link: #fca5c3;
  --ks-accent: #f43f5e;
  --ks-soft: rgba(232,80,143,.12);
  --ks-field: #1a0812;
  --ks-card: rgba(32,9,22,.78);
  --ks-glow: rgba(232,80,143,.38);
  --ks-btn-grad: linear-gradient(120deg, #be123c 0%, #881337 100%);
  --ks-chat-head: linear-gradient(135deg, rgba(190,18,60,.30) 0%, rgba(136,19,55,.24) 60%, rgba(22,5,15,.92) 100%);
  --ks-user-bubble: linear-gradient(135deg, rgba(190,18,60,.30) 0%, rgba(136,19,55,.26) 100%);
  background:
    radial-gradient(900px 520px at 100% -10%, rgba(232,80,143,.22), transparent 62%),
    radial-gradient(760px 460px at -8% 105%, rgba(190,18,60,.22), transparent 60%),
    linear-gradient(180deg, #10030a 0%, #16050f 100%) !important;
}
.stApp:has(.ks-romantic-flag) .ks-chat-head { background: var(--ks-chat-head); border-color: rgba(232,80,143,.30); box-shadow: 0 16px 34px -26px rgba(232,80,143,.5); }
.stApp:has(.ks-romantic-flag) .ks-eyebrow { color: #fca5c3; text-shadow: 0 0 12px rgba(249,168,212,.35); }
.stApp:has(.ks-romantic-flag) [data-testid="stChatMessage"] { background: var(--ks-card); border-color: rgba(232,80,143,.24); box-shadow: 0 12px 26px -22px rgba(232,80,143,.5); }
.stApp:has(.ks-romantic-flag) [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) { background: var(--ks-user-bubble); border-color: rgba(232,80,143,.32); }
.stApp:has(.ks-romantic-flag) [data-testid="stChatInput"] { border-color: var(--ks-line-strong); box-shadow: 0 12px 28px -22px rgba(232,80,143,.7); }
.stApp:has(.ks-romantic-flag) .ks-brand svg circle:nth-of-type(1) { fill: #e8508f; }
.stApp:has(.ks-romantic-flag) .ks-brand svg circle:nth-of-type(2) { fill: #f43f5e; }
.stApp:has(.ks-romantic-flag) [data-testid="stAppViewContainer"],
.stApp:has(.ks-romantic-flag) [data-testid="stMain"],
.stApp:has(.ks-romantic-flag) [data-testid="stHeader"],
.stApp:has(.ks-romantic-flag) [data-testid="stBottom"],
.stApp:has(.ks-romantic-flag) [data-testid="stBottomBlockContainer"] { background: transparent !important; }

@media (max-width: 640px) {
  .stApp h1, .stApp h2 { letter-spacing: -.01em; }
  .ks-w-blob { filter: blur(34px); }
}

/* Mode selector stays pinned under the header while the chat scrolls */
[data-testid="stLayoutWrapper"]:has(> .st-key-ks_modebar), .st-key-ks_modebar:not([data-testid="stLayoutWrapper"] > *) {
  position: sticky; top: 3.5rem; z-index: 60;
}
.st-key-ks_modebar {
  margin: 0 0 .6rem; padding: .45rem .8rem .55rem;
  background: linear-gradient(135deg, rgba(109,40,217,.34) 0%, rgba(134,25,143,.30) 100%), #130a22;
  border: 1px solid rgba(168,85,247,.32); border-radius: 16px;
  box-shadow: 0 14px 30px -20px rgba(168,85,247,.65), inset 0 1px 0 rgba(255,255,255,.06);
}
.st-key-ks_modebar [data-testid="stRadio"] { margin: 0; }
.st-key-ks_modebar [data-testid="stWidgetLabel"] p { color: var(--ks-muted); font-size: .78rem; letter-spacing: .04em; text-transform: uppercase; }
.st-key-ks_modebar [role="radiogroup"] { gap: .45rem; flex-wrap: wrap; }
.st-key-ks_modebar [data-testid="stRadioOption"] {
  margin: 0; padding: .28rem .85rem; border-radius: 999px; cursor: pointer;
  border: 1px solid rgba(168,85,247,.28); background: rgba(168,85,247,.07);
  transition: background .18s ease, box-shadow .18s ease, border-color .18s ease;
}
.st-key-ks_modebar [data-testid="stRadioOption"]:hover { background: rgba(168,85,247,.16); border-color: rgba(168,85,247,.5); }
.st-key-ks_modebar [data-testid="stRadioOption"][data-selected="true"] {
  background: var(--ks-btn-grad); border-color: transparent; box-shadow: 0 0 16px -2px var(--ks-glow);
}
.st-key-ks_modebar [data-testid="stRadioOption"] > div > div:first-child { display: none; }
.st-key-ks_modebar [data-testid="stRadioOption"] p { color: var(--ks-ink); font-weight: 600; }
.stApp:has(.ks-romantic-flag) .st-key-ks_modebar {
  background: linear-gradient(135deg, rgba(190,18,60,.36) 0%, rgba(136,19,55,.30) 100%), #16050f;
  border-color: rgba(232,80,143,.38); box-shadow: 0 14px 30px -20px rgba(232,80,143,.65), inset 0 1px 0 rgba(255,255,255,.06);
}
.stApp:has(.ks-romantic-flag) .st-key-ks_modebar [data-testid="stRadioOption"] { border-color: rgba(232,80,143,.30); background: rgba(232,80,143,.08); }
.stApp:has(.ks-romantic-flag) .st-key-ks_modebar [data-testid="stRadioOption"]:hover { background: rgba(232,80,143,.18); border-color: rgba(232,80,143,.55); }

/* Hosting chrome (Share, star, edit, GitHub, menu, Manage app) is not part of the app. The sidebar expand button lives in the toolbar, so keep it. */
[data-testid="stToolbar"] *:not(:has([data-testid="stExpandSidebarButton"])):not([data-testid="stExpandSidebarButton"]):not([data-testid="stExpandSidebarButton"] *) { display: none !important; }
[data-testid="stToolbarActions"], [data-testid="stAppDeployButton"], [data-testid="stMainMenu"],
[data-testid="stStatusWidget"], [data-testid="stDecoration"], [data-testid="manage-app-button"], #MainMenu, footer,
[class*="viewerBadge"], [class*="stDeployButton"], [class*="_terminalButton_"], [class*="_profileContainer_"],
[class*="_profilePreview_"], a[href*="streamlit.io/cloud"][class*="badge" i] {
  display: none !important; visibility: hidden !important; pointer-events: none !important;
}
[data-testid="stSidebarCollapsedControl"], [data-testid="stExpandSidebarButton"] { display: flex !important; visibility: visible !important; pointer-events: auto !important; }
[data-testid="stElementContainer"]:has(> iframe[height="0"]), [data-testid="stElementContainer"]:has(> iframe[height="1"]) { display: none !important; }
.stApp:has(.ks-romantic-flag) .st-key-ks_modebar [data-testid="stRadioOption"][data-selected="true"] {
  background: var(--ks-btn-grad); border-color: transparent; box-shadow: 0 0 16px -2px rgba(232,80,143,.6);
}
/* Phones: all four modes on a single line */
@media (max-width: 640px) {
  .st-key-ks_modebar { padding: .4rem .5rem .5rem; }
  .st-key-ks_modebar [role="radiogroup"] { flex-wrap: nowrap; gap: .25rem; overflow-x: auto; scrollbar-width: none; }
  .st-key-ks_modebar [data-testid="stRadioOption"] { flex: 1 1 auto; justify-content: center; padding: .28rem .42rem; white-space: nowrap; }
  .st-key-ks_modebar [data-testid="stRadioOption"] p { font-size: .72rem; white-space: nowrap; }
}
/* Pasted or attached image preview above the chat box: larger on every screen */
[data-testid="stFileChip"] { padding: .35rem .6rem .35rem .35rem; gap: .65rem; min-height: 5rem; align-items: center; }
[data-testid="stFileChip"] > div:has(> [data-testid="stFileChipImagePreview"]) { width: 4.5rem; height: 4.5rem; flex: 0 0 4.5rem; }
[data-testid="stFileChipImagePreview"] { width: 100%; height: 100%; object-fit: cover; border-radius: .6rem; }
[data-testid="stFileChipName"] { font-size: .9rem; }
@media (max-width: 640px) {
  [data-testid="stFileChip"] { min-height: 4.25rem; gap: .5rem; }
  [data-testid="stFileChip"] > div:has(> [data-testid="stFileChipImagePreview"]) { width: 3.75rem; height: 3.75rem; flex: 0 0 3.75rem; }
  [data-testid="stFileChipName"] { font-size: .8rem; max-width: 7rem; }
}
</style>
"""
