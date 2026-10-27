"""Cross-browser, cross-device stylesheet for WithYou.

The palette is fixed (light) on purpose: Streamlit components inherit their colors
from the browser/OS color scheme, which can produce light text on light surfaces
(or the reverse) on some devices. Every interactive element therefore sets its own
background, text color, and text-fill color explicitly. All text/background pairs
meet WCAG AA contrast (4.5:1) or better.
"""

import html

APP_CSS = """
<style>
:root {
  color-scheme: light;
  --ks-ink: #102f32;        /* body text on paper/white: ~14:1 */
  --ks-muted: #536b6d;      /* secondary text on paper/white: ~5.5:1 */
  --ks-line: #d7e4e1;
  --ks-line-strong: #6d8884;
  --ks-paper: #f4f9f7;
  --ks-panel: #ffffff;
  --ks-sidebar: #edf5f2;
  --ks-brand: #0b5d55;      /* white on brand: ~7.9:1 */
  --ks-brand-dark: #08463f;
  --ks-teal: #2b8c7e;
  --ks-cream: #f8f5ed;
  --ks-accent: #e9a06d;
  --ks-soft: #e9f4f1;
  --ks-peach: #fff1e7;
  --ks-peach-ink: #4a3226;
  --ks-link: #0b5a8f;
  --ks-focus: #b45309;
  --ks-disabled-bg: #e4e9e7;
  --ks-disabled-ink: #4f5f5c;
}

html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
  color-scheme: light;
  background: var(--ks-paper);
  color: var(--ks-ink);
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  -webkit-text-size-adjust: 100%;
  text-size-adjust: 100%;
}
[data-testid="stHeader"], [data-testid="stBottom"], [data-testid="stBottom"] > div,
[data-testid="stBottomBlockContainer"] { background: var(--ks-paper); color: var(--ks-ink); }
.block-container { width: 100%; max-width: 980px; padding: clamp(3.75rem, 8vw, 4.5rem) clamp(.85rem, 4vw, 2rem) 2.5rem; }

/* Text */
.stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6 { color: var(--ks-ink); letter-spacing: -.02em; }
.stApp p, .stApp li, .stApp label, .stApp [data-testid="stWidgetLabel"] p,
.stApp [data-testid="stMarkdownContainer"] { color: var(--ks-ink); }
.stApp [data-testid="stCaptionContainer"], .stApp [data-testid="stCaptionContainer"] p { color: var(--ks-muted); opacity: 1 !important; }
.stApp [data-testid="stMarkdownContainer"] a, .stApp a:not([data-testid^="stBaseButton"]) { color: var(--ks-link); text-decoration: underline; }

/* Sidebar */
[data-testid="stSidebar"], [data-testid="stSidebar"] > div { background: var(--ks-sidebar); border-right: 1px solid var(--ks-line); }
[data-testid="stSidebar"] .block-container { padding: 1.25rem .9rem; }
[data-testid="stSidebar"] p, [data-testid="stSidebar"] label, [data-testid="stSidebar"] span { color: var(--ks-ink); }
[data-testid="stSidebar"] [data-testid="stCaptionContainer"], [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p { color: var(--ks-muted); }

/* Inputs */
[data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea, [data-testid="stChatInput"] textarea,
[data-testid="stSelectbox"] div[data-baseweb="select"] > div, [data-testid="stMultiSelect"] div[data-baseweb="select"] > div,
div[data-baseweb="input"], div[data-baseweb="base-input"], div[data-baseweb="textarea"] {
  background: #fff !important; color: var(--ks-ink) !important; -webkit-text-fill-color: var(--ks-ink);
  border-color: var(--ks-line-strong) !important; border-radius: 12px; caret-color: var(--ks-ink);
}
[data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea, [data-testid="stChatInput"] textarea { font-size: 16px; }
[data-testid="stTextInput"] input::placeholder, [data-testid="stTextArea"] textarea::placeholder,
[data-testid="stChatInput"] textarea::placeholder { color: #5b6e71 !important; -webkit-text-fill-color: #5b6e71; opacity: 1; }
input:-webkit-autofill, input:-webkit-autofill:hover, input:-webkit-autofill:focus {
  -webkit-text-fill-color: var(--ks-ink); box-shadow: 0 0 0 1000px #fff inset; transition: background-color 9999s ease-out 0s;
}
[data-testid="stTextInput"] input:focus, [data-testid="stTextArea"] textarea:focus,
[data-testid="stSelectbox"] div[data-baseweb="select"]:focus-within, div[data-baseweb="input"]:focus-within {
  border-color: var(--ks-brand) !important; box-shadow: 0 0 0 2px rgba(11,93,85,.28);
}
[data-testid="stTextInput"] button { background: transparent !important; color: var(--ks-ink) !important; border: 0 !important; }
[data-testid="stSelectbox"] svg, [data-testid="stMultiSelect"] svg { fill: var(--ks-ink); color: var(--ks-ink); }

/* Dropdown menus render in a portal outside .stApp */
div[data-baseweb="popover"], div[data-baseweb="popover"] > div, div[data-baseweb="menu"],
ul[role="listbox"], [data-baseweb="select"] ul { background: #fff !important; color: var(--ks-ink) !important; }
li[role="option"], li[role="option"] * { background: #fff; color: var(--ks-ink) !important; -webkit-text-fill-color: var(--ks-ink); }
li[role="option"]:hover, li[role="option"][aria-selected="true"] { background: var(--ks-soft); }
span[data-baseweb="tag"] { background: var(--ks-brand) !important; color: #fff !important; }
span[data-baseweb="tag"] * { color: #fff !important; -webkit-text-fill-color: #fff; }

/* Buttons: every nested element inherits the button color so no inner <p>/<span> can differ */
.stApp [data-testid="stBaseButton-secondary"], .stApp [data-testid="stBaseButton-secondaryFormSubmit"],
.stApp [data-testid="stBaseButton-tertiary"], .stApp .stDownloadButton > button, .stApp .stLinkButton > a {
  min-height: 2.75rem; border-radius: 12px; font-weight: 600; text-decoration: none;
  background: #fff !important; border: 1px solid var(--ks-line-strong) !important; color: var(--ks-ink) !important;
  -webkit-text-fill-color: var(--ks-ink); transition: background-color .15s ease, border-color .15s ease;
}
.stApp [data-testid="stBaseButton-primary"], .stApp [data-testid="stBaseButton-primaryFormSubmit"] {
  min-height: 2.75rem; border-radius: 12px; font-weight: 600; text-decoration: none;
  background: var(--ks-brand) !important; border: 1px solid var(--ks-brand) !important; color: #fff !important;
  -webkit-text-fill-color: #fff; transition: background-color .15s ease, border-color .15s ease;
}
.stApp [data-testid="stBaseButton-secondary"] *, .stApp [data-testid="stBaseButton-secondaryFormSubmit"] *,
.stApp [data-testid="stBaseButton-tertiary"] *, .stApp [data-testid="stBaseButton-primary"] *,
.stApp [data-testid="stBaseButton-primaryFormSubmit"] *, .stApp .stDownloadButton > button *, .stApp .stLinkButton > a * {
  color: inherit !important; -webkit-text-fill-color: currentColor; background: transparent !important;
}
.stApp [data-testid="stBaseButton-secondary"]:hover, .stApp [data-testid="stBaseButton-secondaryFormSubmit"]:hover,
.stApp [data-testid="stBaseButton-tertiary"]:hover, .stApp .stDownloadButton > button:hover, .stApp .stLinkButton > a:hover {
  background: var(--ks-soft) !important; border-color: var(--ks-brand) !important; color: var(--ks-brand-dark) !important;
  -webkit-text-fill-color: var(--ks-brand-dark);
}
.stApp [data-testid="stBaseButton-primary"]:hover, .stApp [data-testid="stBaseButton-primaryFormSubmit"]:hover {
  background: var(--ks-brand-dark) !important; border-color: var(--ks-brand-dark) !important; color: #fff !important;
  -webkit-text-fill-color: #fff;
}
.stApp button:disabled, .stApp [data-testid^="stBaseButton"]:disabled, .stApp .stLinkButton > a[aria-disabled="true"] {
  background: var(--ks-disabled-bg) !important; border-color: #aebbb7 !important; color: var(--ks-disabled-ink) !important;
  -webkit-text-fill-color: var(--ks-disabled-ink); opacity: 1 !important; cursor: not-allowed;
}
.stApp button:focus-visible, .stApp a:focus-visible, .stApp input:focus-visible, .stApp textarea:focus-visible {
  outline: 3px solid var(--ks-focus) !important; outline-offset: 2px;
}
[data-testid="stChatInputSubmitButton"] { color: var(--ks-brand) !important; background: transparent !important; }

/* Containers */
[data-testid="stExpander"] details, [data-testid="stForm"] { background: var(--ks-panel); border: 1px solid var(--ks-line); border-radius: 14px; }
[data-testid="stExpander"] summary, [data-testid="stExpander"] summary * { color: var(--ks-ink) !important; }
[data-testid="stChatInput"] { background: #fff; border: 1px solid var(--ks-line-strong); border-radius: 16px; }
[data-testid="stChatInput"] textarea { min-height: 3.2rem; }
[data-testid="stChatMessage"] { padding: .85rem 1rem; margin: .4rem 0; border: 1px solid var(--ks-line); border-radius: 18px; background: #fff; }
[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] { line-height: 1.65; }
[data-testid="stAlert"], [data-testid="stAlert"] * { color: var(--ks-ink) !important; }
[data-testid="stCheckbox"] label, [data-testid="stRadio"] label { color: var(--ks-ink); }
hr { border-color: var(--ks-line); }

/* Brand components */
.ks-brand { display: inline-flex; align-items: center; gap: .55rem; color: var(--ks-brand-dark); font-weight: 800; font-size: 1.2rem; letter-spacing: -.02em; }
.ks-brand svg { width: 30px; height: 30px; flex: none; }
.ks-topbar { display: flex; align-items: center; justify-content: space-between; padding: .15rem .1rem 1rem; }
.ks-hero { position: relative; overflow: hidden; isolation: isolate; display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(0, .85fr);
  align-items: center; gap: clamp(1rem, 4vw, 2.5rem); padding: clamp(1.4rem, 5vw, 3.25rem); border: 1px solid var(--ks-line); border-radius: 28px;
  background: radial-gradient(120% 120% at 100% 0%, #dcefe9 0%, rgba(220,239,233,0) 55%), linear-gradient(135deg, #ffffff 0%, #eef7f4 55%, #f8f5ed 100%);
  box-shadow: 0 22px 44px -32px rgba(11,93,85,.55); }
.ks-hero-text { position: relative; z-index: 2; min-width: 0; }
.stApp .ks-hero h1 { color: var(--ks-ink); font-size: clamp(1.85rem, 4.6vw, 3.05rem); line-height: 1.1; font-weight: 800; letter-spacing: -.03em; margin: .6rem 0 .95rem; padding: 0; overflow-wrap: anywhere; }
.stApp .ks-hero p { color: var(--ks-muted); font-size: clamp(1rem, 1.9vw, 1.12rem); line-height: 1.65; max-width: 48ch; margin: 0; }
.ks-hello { color: var(--ks-brand); font-weight: 600; margin: .5rem 0 0; }
.ks-hero-art { position: relative; z-index: 1; display: flex; justify-content: center; }
.ks-hero-art svg { width: 100%; max-width: 280px; height: auto; animation: ks-float 10s ease-in-out infinite; }
.ks-features { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1rem; margin: 1.75rem 0 1.25rem; }
.ks-feature { min-width: 0; padding: 1.25rem 1.25rem 1.35rem; border: 1px solid var(--ks-line); border-radius: 20px; background: #fff; color: var(--ks-ink);
  box-shadow: 0 10px 22px -20px rgba(16,47,50,.55); }
.ks-feature-icon { width: 42px; height: 42px; border-radius: 12px; background: var(--ks-soft); display: flex; align-items: center; justify-content: center; margin-bottom: .85rem; }
.ks-feature-icon svg { width: 22px; height: 22px; stroke: var(--ks-brand); fill: none; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
.ks-feature strong { display: block; color: var(--ks-ink); font-size: 1.05rem; line-height: 1.3; margin-bottom: .35rem; }
.ks-feature span { color: var(--ks-muted); font-size: .95rem; line-height: 1.55; }
@keyframes ks-float { 0%, 100% { transform: translate3d(0, 0, 0); } 50% { transform: translate3d(0, -10px, 0); } }
.ks-eyebrow { color: var(--ks-brand-dark); font-weight: 700; font-size: .78rem; letter-spacing: .12em; text-transform: uppercase; }
.ks-note { padding: .85rem 1rem; border-radius: 14px; border: 1px solid #ecd3c1; background: var(--ks-cream); color: #4a3a2c !important; font-size: .92rem; line-height: 1.55; }
.ks-card { padding: 1rem; border: 1px solid var(--ks-line); border-radius: 16px; background: var(--ks-panel); color: var(--ks-ink); }
.ks-footer { text-align: center; color: var(--ks-muted); font-size: .85rem; margin-top: 1.25rem; }

/* Welcome call-to-action area */
.st-key-ks_auth { max-width: 640px; margin: 1.5rem auto 0; background: #fff; border: 1px solid var(--ks-line); border-radius: 24px;
  padding: clamp(1rem, 3vw, 1.6rem); box-shadow: 0 14px 30px -26px rgba(16,47,50,.6); }
.st-key-welcome_login button { min-height: 3.1rem; font-size: 1.02rem; }
.st-key-welcome_signup button { min-height: 3.1rem; font-size: 1.02rem; }
.ks-or { display: flex; align-items: center; gap: .8rem; color: var(--ks-muted); font-size: .9rem; margin: 1rem 0 .7rem; }
.ks-or::before, .ks-or::after { content: ""; flex: 1; height: 1px; background: var(--ks-line); }
:is(.st-key-welcome_google, .st-key-login_google, .st-key-signup_google) button::before, :is(.st-key-welcome_github, .st-key-login_github, .st-key-signup_github) a::before {
  content: ""; display: inline-block; flex: none; width: 18px; height: 18px; margin-right: .55rem; background-repeat: no-repeat; background-position: center; background-size: contain; }
:is(.st-key-welcome_google, .st-key-login_google, .st-key-signup_google) button::before { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 48 48'%3E%3Cpath fill='%23EA4335' d='M24 9.5c3.5 0 6.6 1.2 9.1 3.6l6.8-6.8C35.8 2.4 30.3 0 24 0 14.6 0 6.5 5.4 2.6 13.2l7.9 6.1C12.4 13.6 17.7 9.5 24 9.5z'/%3E%3Cpath fill='%234285F4' d='M46.5 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.7c-.6 3-2.3 5.5-4.8 7.2l7.5 5.8c4.4-4.1 7.1-10.1 7.1-17.5z'/%3E%3Cpath fill='%23FBBC05' d='M10.5 28.7c-.5-1.5-.8-3-.8-4.7s.3-3.2.8-4.7l-7.9-6.1C.9 16.4 0 20.1 0 24s.9 7.6 2.6 10.8l7.9-6.1z'/%3E%3Cpath fill='%2334A853' d='M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.5-5.8c-2.1 1.4-4.8 2.3-8.4 2.3-6.3 0-11.6-4.1-13.5-9.8l-7.9 6.1C6.5 42.6 14.6 48 24 48z'/%3E%3C/svg%3E"); }
:is(.st-key-welcome_github, .st-key-login_github, .st-key-signup_github) a::before { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Cpath fill='%23102F32' d='M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z'/%3E%3C/svg%3E"); }

/* Signed-in chat */
.ks-chat-head { display: flex; align-items: center; justify-content: space-between; gap: .75rem 1rem; flex-wrap: wrap; padding: 1.1rem 1.3rem; margin-bottom: .6rem;
  border: 1px solid var(--ks-line); border-radius: 20px; background: linear-gradient(135deg, #ffffff 0%, #eef7f4 60%, #f8f5ed 100%); }
.stApp .ks-chat-head h2 { margin: .1rem 0 0; padding: 0; font-size: clamp(1.3rem, 3.2vw, 1.7rem); font-weight: 800; line-height: 1.2; }
.ks-chat-head p { margin: .2rem 0 0; color: var(--ks-muted); font-size: .95rem; }
.ks-chip { display: inline-block; max-width: 100%; padding: .28rem .7rem; border-radius: 999px; border: 1px solid var(--ks-line); background: var(--ks-soft); color: var(--ks-brand-dark);
  font-size: .8rem; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ks-chip.rose { background: #fdeaf0; border-color: #f2c6d4; color: #7a2343; }
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) { background: var(--ks-soft); border-color: #cfe3dd; }
.st-key-sidebar_chats [data-testid^="stBaseButton"] { justify-content: flex-start; text-align: left; }
.st-key-sidebar_chats [data-testid^="stBaseButton"] p { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
[class*="st-key-ks_active_"] [data-testid^="stBaseButton"] { background: var(--ks-soft) !important; border-color: var(--ks-brand) !important; }
[data-testid="stToggle"] label p, [data-testid="stCheckbox"] label p { color: var(--ks-ink) !important; }

/* Login / Create account / Reset pages */
.st-key-ks_authpage { max-width: 520px; margin: 0 auto; background: #fff; border: 1px solid var(--ks-line); border-radius: 28px;
  padding: clamp(1rem, 4vw, 2rem); box-shadow: 0 22px 44px -32px rgba(11,93,85,.55); }
.ks-authhead { text-align: center; padding: 1.5rem 1rem 1.35rem; margin-bottom: 1.1rem; border: 1px solid var(--ks-line); border-radius: 22px;
  background: radial-gradient(120% 120% at 100% 0%, #dcefe9 0%, rgba(220,239,233,0) 55%), linear-gradient(135deg, #ffffff 0%, #eef7f4 55%, #f8f5ed 100%); }
.ks-badge { display: inline-block; margin-top: 1rem; padding: .32rem 1.1rem; border-radius: 999px; background: var(--ks-brand); color: #fff;
  font-weight: 800; font-size: .8rem; letter-spacing: .22em; text-transform: uppercase; }
.stApp .ks-authhead h1 { color: var(--ks-ink); font-size: clamp(1.6rem, 5.5vw, 2.15rem); font-weight: 800; line-height: 1.15; letter-spacing: -.03em; margin: .8rem 0 .35rem; padding: 0; }
.stApp .ks-authhead p { color: var(--ks-muted); margin: 0; font-size: 1rem; line-height: 1.55; }
.st-key-ks_authpage [data-testid="stForm"] { border: 0; background: transparent; padding: 0; }
.st-key-ks_authpage [data-baseweb="input"], .st-key-ks_authpage [data-baseweb="base-input"] { border-radius: 14px; background: var(--ks-paper); }
.st-key-ks_authpage [data-baseweb="input"]:focus-within { border-color: var(--ks-brand); box-shadow: 0 0 0 3px rgba(11,93,85,.18); }
.st-key-ks_authpage input { min-height: 3rem; }
.st-key-ks_authpage [data-testid="stWidgetLabel"] p { font-weight: 600; }
.st-key-ks_authpage [data-testid="stFormSubmitButton"] button { min-height: 3.1rem; font-size: 1.02rem; margin-top: .35rem; }
.st-key-ks_authlinks { margin-top: .6rem; align-items: center !important; gap: .1rem !important; }
.st-key-ks_authlinks > [data-testid="stElementContainer"] { width: auto !important; }
.st-key-ks_authlinks [data-testid="stButton"] { display: flex; justify-content: center; }
.st-key-ks_authlinks [data-testid^="stBaseButton"] { background: transparent !important; border: 0 !important; box-shadow: none !important; outline: none;
  color: var(--ks-brand) !important; font-weight: 700; min-height: 2.4rem; padding: .3rem 1.1rem; border-radius: 999px !important; text-decoration: none;
  transition: background-color .15s ease, color .15s ease; }
.st-key-ks_authlinks [data-testid^="stBaseButton"]:hover, .st-key-ks_authlinks [data-testid^="stBaseButton"]:active {
  color: var(--ks-brand-dark) !important; background: var(--ks-soft) !important; border: 0 !important; box-shadow: none !important; }
.st-key-ks_authlinks [data-testid^="stBaseButton"]:focus-visible { outline: 3px solid var(--ks-focus) !important; outline-offset: 1px; }
.st-key-ks_authlinks [data-testid^="stBaseButton"]:focus:not(:focus-visible) { box-shadow: none !important; outline: none !important; }
.st-key-ks_authlinks [data-testid^="stBaseButton"] p { color: inherit !important; background: transparent !important; }
.ks-authprompt { text-align: center; color: var(--ks-muted); font-size: .95rem; margin-top: .6rem; }
.ks-authhead h1 a, .ks-hero h1 a { display: none !important; }

@media (max-width: 820px) {
  .ks-features { grid-template-columns: 1fr; }
}
@media (max-width: 640px) {
  [data-testid="stSidebar"] { min-width: 0; }
  [data-testid="stSidebar"] .block-container { padding: .8rem .65rem; }
  .ks-hero { grid-template-columns: 1fr; border-radius: 20px; }
  .ks-hero-art svg { max-width: 190px; }
  .ks-features { grid-template-columns: 1fr; }
  .ks-hero h1 br { display: none; }
  [data-testid="stHorizontalBlock"] { gap: .65rem; }
  [data-testid="stChatMessage"] { padding: .65rem .75rem; }
  .stApp [data-testid^="stBaseButton"] { min-height: 2.9rem; }
}
@media (forced-colors: active) {
  .stApp [data-testid^="stBaseButton"], .stApp .stLinkButton > a { border: 1px solid ButtonText !important; forced-color-adjust: auto; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { scroll-behavior: auto !important; transition-duration: .01ms !important; animation-duration: .01ms !important; animation-iteration-count: 1 !important; }
}
</style>
"""

BRAND_MARK_SVG = (
    '<svg viewBox="0 0 32 32" aria-hidden="true" focusable="false">'
    '<circle cx="12" cy="16" r="9" fill="#0B5D55"/>'
    '<circle cx="21" cy="16" r="9" fill="#E9A06D" fill-opacity=".9"/>'
    '<path d="M16.5 9.4a9 9 0 0 1 0 13.2 9 9 0 0 1 0-13.2Z" fill="#2B8C7E"/>'
    '</svg>'
)

BRAND_HTML = f'<span class="ks-brand">{BRAND_MARK_SVG}<span>WithYou</span></span>'

_HERO_ART = (
    '<svg viewBox="0 0 240 240" role="img" aria-label="A small leafy plant in a warm pot, surrounded by soft circles">'
    '<circle cx="120" cy="120" r="112" fill="#ffffff" fill-opacity=".72"/>'
    '<circle cx="120" cy="120" r="86" fill="#E9F4F1"/>'
    '<circle cx="186" cy="62" r="16" fill="#E9A06D" fill-opacity=".55"/>'
    '<circle cx="52" cy="176" r="10" fill="#2B8C7E" fill-opacity=".35"/>'
    '<path d="M120 178 C120 140 120 118 120 92" stroke="#0B5D55" stroke-width="6" stroke-linecap="round" fill="none"/>'
    '<path d="M120 126 C86 126 66 104 64 80 C92 80 116 96 120 126 Z" fill="#0B5D55"/>'
    '<path d="M120 108 C148 108 168 90 172 64 C144 64 122 80 120 108 Z" fill="#2B8C7E"/>'
    '<path d="M92 178 H148 L142 208 H98 Z" fill="#E9A06D"/>'
    '<rect x="88" y="172" width="64" height="10" rx="5" fill="#D88B55"/>'
    '</svg>'
)

_ICON_LOCK = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="11" width="14" height="9" rx="2.5"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>'
_ICON_CHAT = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 5h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-7l-5 4v-4H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z"/></svg>'
_ICON_SLIDERS = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h9M17 7h3M4 17h3M11 17h9"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="17" r="2"/></svg>'


def _feature(icon: str, title: str, text: str) -> str:
    return f'<div class="ks-feature"><div class="ks-feature-icon">{icon}</div><strong>{title}</strong><span>{text}</span></div>'


def auth_header_html(badge: str, title: str, subtitle: str) -> str:
    """Header banner for the Login / Create account / Reset pages."""
    return (
        f'<div class="ks-authhead">{BRAND_HTML}'
        f'<div><span class="ks-badge">{html.escape(badge)}</span></div>'
        f'<h1>{html.escape(title)}</h1><p>{html.escape(subtitle)}</p></div>'
    )


def welcome_html(display_name: str = "") -> str:
    """Welcome page markup. No blank lines or indentation: Markdown would otherwise end the HTML block early."""
    hello = f'<div class="ks-hello">Welcome back, {html.escape(display_name)}</div>' if display_name else ""
    return (
        f'<div class="ks-topbar">{BRAND_HTML}</div>'
        '<section class="ks-hero">'
        '<div class="ks-hero-text">'
        '<div class="ks-eyebrow">Your personal space to talk, think &amp; grow</div>'
        f'{hello}'
        '<h1>Here for whatever<br> is on your mind.</h1>'
        '<p>WithYou is your personal AI companion for everyday conversations, questions, ideas, planning, reflection, '
        'and encouragement, all in one private space.</p>'
        '</div>'
        f'<div class="ks-hero-art">{_HERO_ART}</div>'
        '</section>'
    )


def welcome_features_html() -> str:
    return (
        '<div class="ks-features">'
        + _feature(_ICON_LOCK, "Your conversations, your space", "Your chats stay connected to your account, so you can come back anytime and continue where you left off.")
        + _feature(_ICON_CHAT, "Always ready to talk", "Ask a question, share a thought, make a plan, or simply have a conversation whenever you need one.")
        + _feature(_ICON_SLIDERS, "Made to feel personal", "Choose how you like to chat and enjoy responses that feel warm, natural, and helpful.")
        + '</div>'
    )
