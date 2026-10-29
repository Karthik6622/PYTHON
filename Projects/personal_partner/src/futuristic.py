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
  --ks-ink: #e6f7ff;
  --ks-muted: #8ea6c2;
  --ks-line: rgba(34,211,238,.20);
  --ks-line-strong: #2b6f8a;
  --ks-paper: #050914;
  --ks-panel: #0b1426;
  --ks-sidebar: #08101f;
  --ks-brand: #22d3ee;
  --ks-brand-dark: #67e8f9;
  --ks-teal: #2dd4bf;
  --ks-cream: rgba(251,191,36,.08);
  --ks-accent: #a78bfa;
  --ks-soft: rgba(34,211,238,.10);
  --ks-peach: rgba(167,139,250,.12);
  --ks-peach-ink: #ddd6fe;
  --ks-link: #7dd3fc;
  --ks-focus: #f0abfc;
  --ks-disabled-bg: #131c2e;
  --ks-disabled-ink: #5f7389;
  --ks-field: #0a1222;
  --ks-card: rgba(11,20,38,.78);
  --ks-glow: rgba(34,211,238,.38);
  --ks-btn-grad: linear-gradient(120deg, #0e7490 0%, #6d28d9 100%);
  --ks-chat-head: linear-gradient(135deg, rgba(14,116,144,.30) 0%, rgba(76,29,149,.26) 60%, rgba(11,20,38,.92) 100%);
  --ks-user-bubble: linear-gradient(135deg, rgba(14,116,144,.30) 0%, rgba(76,29,149,.26) 100%);
}

/* Canvas: neon grid with soft cyan and violet light */
.stApp, [data-testid="stAppViewContainer"] {
  background:
    linear-gradient(rgba(34,211,238,.045) 1px, transparent 1px) 0 0 / 44px 44px,
    linear-gradient(90deg, rgba(34,211,238,.045) 1px, transparent 1px) 0 0 / 44px 44px,
    radial-gradient(900px 520px at 92% -8%, rgba(167,139,250,.22), transparent 62%),
    radial-gradient(820px 520px at -8% 12%, rgba(34,211,238,.16), transparent 60%),
    #050914 !important;
}
[data-testid="stHeader"] { background: rgba(5,9,20,.72) !important; -webkit-backdrop-filter: blur(10px); backdrop-filter: blur(10px); }
[data-testid="stMain"], [data-testid="stHeader"] { color: var(--ks-ink); }
[data-testid="stBottom"], [data-testid="stBottom"] > div, [data-testid="stBottomBlockContainer"] {
  background: linear-gradient(to top, #050914 62%, rgba(5,9,20,0)) !important;
}
.stApp h1, .stApp h2, .stApp h3, .stApp h4 { font-family: 'Space Grotesk', system-ui, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif; text-shadow: 0 0 22px rgba(34,211,238,.12); }
[data-testid="stSidebar"], [data-testid="stSidebar"] > div {
  background: linear-gradient(180deg, #0a1426 0%, #060c18 100%);
  border-right: 1px solid var(--ks-line);
  box-shadow: 0 0 36px -18px rgba(34,211,238,.45);
}
.stApp [data-testid="stCaptionContainer"], .stApp [data-testid="stCaptionContainer"] p { color: var(--ks-muted); }
.stApp [data-testid="stMarkdownContainer"] a, .stApp a:not([data-testid^="stBaseButton"]) { color: var(--ks-link); text-shadow: 0 0 12px rgba(125,211,252,.25); }
hr { border-color: var(--ks-line); }

/* Inputs */
[data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea, [data-testid="stChatInput"] textarea,
[data-testid="stSelectbox"] div[data-baseweb="select"] > div, [data-testid="stMultiSelect"] div[data-baseweb="select"] > div,
div[data-baseweb="input"], div[data-baseweb="base-input"], div[data-baseweb="textarea"] {
  background: var(--ks-field) !important; color: var(--ks-ink) !important; -webkit-text-fill-color: var(--ks-ink);
  border-color: var(--ks-line-strong) !important; caret-color: var(--ks-brand);
}
[data-testid="stTextInput"] input::placeholder, [data-testid="stTextArea"] textarea::placeholder,
[data-testid="stChatInput"] textarea::placeholder { color: #6f86a3 !important; -webkit-text-fill-color: #6f86a3; opacity: 1; }
input:-webkit-autofill, input:-webkit-autofill:hover, input:-webkit-autofill:focus {
  -webkit-text-fill-color: var(--ks-ink); box-shadow: 0 0 0 1000px #0a1222 inset;
}
[data-testid="stTextInput"] input:focus, [data-testid="stTextArea"] textarea:focus,
[data-testid="stSelectbox"] div[data-baseweb="select"]:focus-within, div[data-baseweb="input"]:focus-within {
  border-color: var(--ks-brand) !important; box-shadow: 0 0 0 1px var(--ks-brand), 0 0 18px var(--ks-glow) !important;
}
[data-testid="stSelectbox"] svg, [data-testid="stMultiSelect"] svg { fill: var(--ks-brand-dark); color: var(--ks-brand-dark); }

/* Dropdown menus (rendered outside .stApp) */
div[data-baseweb="popover"], div[data-baseweb="popover"] > div, div[data-baseweb="menu"],
ul[role="listbox"], [data-baseweb="select"] ul {
  background: #0b1426 !important; color: var(--ks-ink) !important; border: 1px solid var(--ks-line);
}
li[role="option"] { background: #0b1426; }
span[data-baseweb="tag"] { background: var(--ks-btn-grad) !important; }

/* Buttons */
.stApp [data-testid="stBaseButton-secondary"], .stApp [data-testid="stBaseButton-secondaryFormSubmit"],
.stApp [data-testid="stBaseButton-tertiary"], .stApp .stDownloadButton > button, .stApp .stLinkButton > a {
  background: var(--ks-card) !important; border: 1px solid rgba(34,211,238,.35) !important;
  color: var(--ks-ink) !important; -webkit-text-fill-color: var(--ks-ink);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.04);
}
.stApp [data-testid="stBaseButton-secondary"]:hover, .stApp [data-testid="stBaseButton-secondaryFormSubmit"]:hover,
.stApp [data-testid="stBaseButton-tertiary"]:hover, .stApp .stDownloadButton > button:hover, .stApp .stLinkButton > a:hover {
  background: rgba(34,211,238,.12) !important; border-color: var(--ks-brand) !important;
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
  background: var(--ks-disabled-bg) !important; border-color: #263449 !important; color: var(--ks-disabled-ink) !important;
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
  box-shadow: 0 0 0 1px rgba(34,211,238,.06), 0 18px 40px -26px rgba(0,0,0,.9);
}
[data-testid="stChatInput"]:focus-within { border-color: var(--ks-brand); box-shadow: 0 0 0 1px var(--ks-brand), 0 0 24px var(--ks-glow); }
[data-testid="stChatInput"] textarea { background: transparent !important; }
[data-testid="stChatMessage"] {
  background: var(--ks-card); border: 1px solid var(--ks-line); border-radius: 18px;
  box-shadow: 0 16px 36px -28px rgba(0,0,0,.9); -webkit-backdrop-filter: blur(6px); backdrop-filter: blur(6px);
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) { background: var(--ks-user-bubble); border-color: rgba(34,211,238,.32); }
.ks-chat-head {
  background: var(--ks-chat-head); border: 1px solid var(--ks-line);
  box-shadow: inset 0 1px 0 rgba(34,211,238,.35), 0 22px 50px -32px rgba(34,211,238,.5);
}
.ks-chat-head p { color: var(--ks-muted); }
.ks-eyebrow { color: var(--ks-brand-dark); text-shadow: 0 0 12px rgba(103,232,249,.35); }
.ks-chip { background: rgba(34,211,238,.10); border-color: rgba(34,211,238,.30); color: var(--ks-brand-dark); }
.ks-chip.rose { background: rgba(244,114,182,.12); border-color: rgba(244,114,182,.35); color: #fbcfe8; }
.ks-note { background: var(--ks-cream); border: 1px solid rgba(251,191,36,.30); color: #fde68a !important; }
.ks-card { background: var(--ks-card); border-color: var(--ks-line); }
.ks-feature { background: var(--ks-card); border-color: var(--ks-line); box-shadow: 0 14px 30px -24px rgba(0,0,0,.9); }
.ks-feature-icon { background: rgba(34,211,238,.10); }
.ks-feature-icon svg, .ks-w-icon svg { stroke: var(--ks-brand-dark); }
.ks-footer strong { color: var(--ks-brand-dark); }
.ks-brand { color: var(--ks-brand-dark); }
.ks-brand svg circle:nth-of-type(1), .ks-w-mhead svg circle:nth-of-type(1) { fill: #22d3ee; }
.ks-brand svg circle:nth-of-type(2), .ks-w-mhead svg circle:nth-of-type(2) { fill: #a78bfa; }
.ks-brand svg path, .ks-w-mhead svg path { fill: #f0abfc; }

/* Welcome page */
.st-key-ks_nav { background: rgba(8,14,30,.72); border: 1px solid var(--ks-line); box-shadow: 0 14px 34px -22px rgba(34,211,238,.35); }
.st-key-ks_herobox {
  background: radial-gradient(120% 120% at 100% 0%, rgba(167,139,250,.20) 0%, rgba(167,139,250,0) 55%),
    linear-gradient(135deg, #0b1426 0%, #0a1c2e 55%, #0d1224 100%);
  border: 1px solid var(--ks-line); box-shadow: 0 0 60px -30px rgba(34,211,238,.45), 0 22px 44px -32px rgba(0,0,0,.9);
}
.ks-w-badge { background: rgba(8,14,30,.78); border: 1px solid var(--ks-line); color: var(--ks-brand-dark); box-shadow: 0 0 18px -10px rgba(34,211,238,.8); }
.ks-w-badge i { background: var(--ks-btn-grad); }
.ks-w-grad { background: linear-gradient(100deg, #22d3ee 0%, #a78bfa 55%, #f0abfc 100%); -webkit-background-clip: text; background-clip: text; }
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
.stApp .st-key-welcome_signup [data-testid^="stBaseButton"]:hover { background: rgba(34,211,238,.12) !important; }
.stApp .st-key-welcome_google [data-testid^="stBaseButton"], .stApp .st-key-welcome_github a {
  background: var(--ks-card) !important; border: 1px solid rgba(34,211,238,.30) !important;
}
.ks-w-mock {
  background: linear-gradient(180deg, rgba(14,24,44,.96) 0%, rgba(8,14,28,.96) 100%); border: 1px solid rgba(34,211,238,.30);
  box-shadow: 0 40px 70px -34px rgba(0,0,0,.9), 0 0 60px -20px rgba(34,211,238,.35);
}
.ks-w-mhead { border-bottom: 1px solid var(--ks-line); }
.ks-w-msg.me { background: var(--ks-btn-grad); }
.ks-w-blob.b1 { background: rgba(167,139,250,.45); }
.ks-w-blob.b2 { background: rgba(34,211,238,.38); }
.ks-w-chip { background: var(--ks-card); border: 1px solid rgba(34,211,238,.30); color: var(--ks-ink); box-shadow: 0 0 22px -12px rgba(34,211,238,.8); }
.ks-w-chip.c2 svg { fill: #f0abfc; stroke: #f0abfc; }
.ks-w-card {
  background: var(--ks-card); border: 1px solid var(--ks-line);
  box-shadow: 0 18px 36px -30px rgba(0,0,0,.9);
}
.ks-w-card:hover { border-color: rgba(34,211,238,.55); box-shadow: 0 0 34px -12px var(--ks-glow), 0 28px 44px -28px rgba(0,0,0,.9); }
.ks-w-icon { background: linear-gradient(135deg, rgba(34,211,238,.18), rgba(167,139,250,.18)); border: 1px solid rgba(34,211,238,.35); }
.ks-w-trust svg { stroke: var(--ks-brand-dark); }
.ks-w-footer { border-top: 1px solid var(--ks-line); }

/* Login, create account, reset */
.st-key-ks_auth, .st-key-ks_authpage {
  background: var(--ks-card); border: 1px solid var(--ks-line);
  box-shadow: 0 0 60px -30px rgba(34,211,238,.45), 0 22px 44px -32px rgba(0,0,0,.9);
}
.ks-authhead {
  background: radial-gradient(120% 120% at 100% 0%, rgba(167,139,250,.20) 0%, rgba(167,139,250,0) 55%),
    linear-gradient(135deg, #0b1426 0%, #0a1c2e 55%, #0d1224 100%);
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
  --ks-ink: #fdf2f8;
  --ks-muted: #d6a9c0;
  --ks-line: rgba(244,114,182,.26);
  --ks-line-strong: #9d4b72;
  --ks-paper: #14060f;
  --ks-panel: #220a1a;
  --ks-sidebar: #1a0814;
  --ks-brand: #f472b6;
  --ks-brand-dark: #fbcfe8;
  --ks-link: #f9a8d4;
  --ks-accent: #fb7185;
  --ks-soft: rgba(244,114,182,.12);
  --ks-field: #1f0b18;
  --ks-card: rgba(38,12,30,.78);
  --ks-glow: rgba(244,114,182,.38);
  --ks-btn-grad: linear-gradient(120deg, #be185d 0%, #9d174d 100%);
  --ks-chat-head: linear-gradient(135deg, rgba(190,24,93,.30) 0%, rgba(131,24,67,.24) 60%, rgba(28,10,22,.92) 100%);
  --ks-user-bubble: linear-gradient(135deg, rgba(190,24,93,.30) 0%, rgba(131,24,67,.26) 100%);
  background:
    radial-gradient(900px 520px at 100% -10%, rgba(244,114,182,.22), transparent 62%),
    radial-gradient(760px 460px at -8% 105%, rgba(190,24,93,.22), transparent 60%),
    linear-gradient(180deg, #14060f 0%, #1c0814 100%) !important;
}
.stApp:has(.ks-romantic-flag) .ks-chat-head { background: var(--ks-chat-head); border-color: rgba(244,114,182,.30); box-shadow: 0 16px 34px -26px rgba(244,114,182,.5); }
.stApp:has(.ks-romantic-flag) .ks-eyebrow { color: #f9a8d4; text-shadow: 0 0 12px rgba(249,168,212,.35); }
.stApp:has(.ks-romantic-flag) [data-testid="stChatMessage"] { background: var(--ks-card); border-color: rgba(244,114,182,.24); box-shadow: 0 12px 26px -22px rgba(244,114,182,.5); }
.stApp:has(.ks-romantic-flag) [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) { background: var(--ks-user-bubble); border-color: rgba(244,114,182,.32); }
.stApp:has(.ks-romantic-flag) [data-testid="stChatInput"] { border-color: var(--ks-line-strong); box-shadow: 0 12px 28px -22px rgba(244,114,182,.7); }
.stApp:has(.ks-romantic-flag) .ks-brand svg circle:nth-of-type(1) { fill: #f472b6; }
.stApp:has(.ks-romantic-flag) .ks-brand svg circle:nth-of-type(2) { fill: #fb7185; }
.stApp:has(.ks-romantic-flag) [data-testid="stAppViewContainer"],
.stApp:has(.ks-romantic-flag) [data-testid="stMain"],
.stApp:has(.ks-romantic-flag) [data-testid="stHeader"],
.stApp:has(.ks-romantic-flag) [data-testid="stBottom"],
.stApp:has(.ks-romantic-flag) [data-testid="stBottomBlockContainer"] { background: transparent !important; }

@media (max-width: 640px) {
  .stApp h1, .stApp h2 { letter-spacing: -.01em; }
  .ks-w-blob { filter: blur(34px); }
}
</style>
"""
