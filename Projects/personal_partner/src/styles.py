"""Cross-browser, cross-device stylesheet for KindSpace.

The palette is fixed (light) on purpose: Streamlit components inherit their colors
from the browser/OS color scheme, which can produce light text on light surfaces
(or the reverse) on some devices. Every interactive element therefore sets its own
background, text color, and text-fill color explicitly. All text/background pairs
meet WCAG AA contrast (4.5:1) or better.
"""

APP_CSS = """
<style>
:root {
  color-scheme: light;
  --ks-ink: #14292e;        /* body text on paper/white: ~14:1 */
  --ks-muted: #44595c;      /* secondary text on paper/white: ~7:1 */
  --ks-line: #c9d8d4;
  --ks-line-strong: #6d8884;
  --ks-paper: #f4f8f6;
  --ks-panel: #ffffff;
  --ks-sidebar: #e9f2ee;
  --ks-brand: #0f5f57;      /* white on brand: ~7.6:1 */
  --ks-brand-dark: #0a4943;
  --ks-soft: #e1efea;
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
.block-container { width: 100%; max-width: 980px; padding: clamp(1rem, 4vw, 2.5rem) clamp(.85rem, 4vw, 2rem) 2.5rem; }

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
  border-color: var(--ks-brand) !important; box-shadow: 0 0 0 2px rgba(15,95,87,.28);
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
[data-testid="stChatMessage"] { padding: .75rem 0; background: transparent; }
[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] { line-height: 1.65; }
[data-testid="stAlert"], [data-testid="stAlert"] * { color: var(--ks-ink) !important; }
[data-testid="stCheckbox"] label, [data-testid="stRadio"] label { color: var(--ks-ink); }
hr { border-color: var(--ks-line); }

/* Brand components */
.ks-brand { color: var(--ks-brand-dark); font-weight: 800; font-size: 1.05rem; letter-spacing: -.02em; }
.ks-hero { position: relative; overflow: hidden; isolation: isolate; padding: clamp(1.4rem, 5vw, 3rem); border: 1px solid var(--ks-line); border-radius: 24px;
  background: linear-gradient(120deg, #ffffff, #e6f3ee, #fdf1e8, #e6f3ee, #ffffff); background-size: 300% 300%; animation: ks-gradient 18s ease-in-out infinite; }
.ks-hero h1 { color: var(--ks-ink); max-width: 16ch; }
.ks-hero p { color: var(--ks-muted); max-width: 46ch; }
.ks-hero-text { position: relative; z-index: 2; }
.ks-orb { position: absolute; border-radius: 50%; filter: blur(2px); opacity: .55; z-index: 0; pointer-events: none; animation: ks-float 14s ease-in-out infinite; }
.ks-orb.one { width: 220px; height: 220px; right: -60px; top: -70px; background: radial-gradient(circle at 30% 30%, #bfe3d8, rgba(191,227,216,0) 70%); }
.ks-orb.two { width: 180px; height: 180px; left: 38%; bottom: -80px; background: radial-gradient(circle at 30% 30%, #ffd9bf, rgba(255,217,191,0) 70%); animation-delay: -5s; }
.ks-orb.three { width: 120px; height: 120px; left: -30px; top: 30%; background: radial-gradient(circle at 30% 30%, #cfe6f5, rgba(207,230,245,0) 70%); animation-delay: -9s; }
.ks-art { position: absolute; right: clamp(.5rem, 4vw, 2.5rem); top: 50%; width: clamp(150px, 26vw, 260px); transform: translateY(-50%); z-index: 1; animation: ks-float 9s ease-in-out infinite; }
.ks-features { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: .75rem; margin-top: .9rem; }
.ks-feature { padding: .9rem 1rem; border: 1px solid var(--ks-line); border-radius: 14px; background: var(--ks-panel); color: var(--ks-ink); }
.ks-feature strong { display: block; color: var(--ks-brand-dark); margin-bottom: .2rem; }
.ks-feature span { color: var(--ks-muted); font-size: .92rem; }
@keyframes ks-gradient { 0%, 100% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } }
@keyframes ks-float { 0%, 100% { transform: translate3d(0, 0, 0); } 50% { transform: translate3d(0, -14px, 0); } }
@keyframes ks-art-float { 0%, 100% { transform: translateY(-50%); } 50% { transform: translateY(calc(-50% - 12px)); } }.ks-art { animation-name: ks-art-float; }
.ks-eyebrow { color: var(--ks-brand-dark); font-weight: 700; font-size: .78rem; letter-spacing: .1em; text-transform: uppercase; }
.ks-note { padding: .85rem 1rem; border-radius: 12px; border: 1px solid #e3c7b4; background: var(--ks-peach); color: var(--ks-peach-ink) !important; }
.ks-card { padding: 1rem; border: 1px solid var(--ks-line); border-radius: 16px; background: var(--ks-panel); color: var(--ks-ink); }

@media (max-width: 640px) {
  [data-testid="stSidebar"] { min-width: 0; }
  [data-testid="stSidebar"] .block-container { padding: .8rem .65rem; }
  .ks-hero { border-radius: 18px; }
  .ks-art { display: none; }
  .ks-hero h1 { max-width: none; }
  [data-testid="stHorizontalBlock"] { gap: .65rem; }
  [data-testid="stChatMessage"] { padding: .5rem 0; }
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

# No blank lines or indentation: Markdown would otherwise end the HTML block early.
WELCOME_HERO_HTML = (
    '<section class="ks-hero">'
    '<span class="ks-orb one"></span><span class="ks-orb two"></span><span class="ks-orb three"></span>'
    '<svg class="ks-art" viewBox="0 0 240 240" role="img" aria-label="A leaf growing from a small plant pot">'
    '<circle cx="120" cy="120" r="108" fill="#ffffff" fill-opacity=".7"/>'
    '<circle cx="120" cy="120" r="84" fill="#e1efea"/>'
    '<path d="M120 178 C120 140 120 118 120 92" stroke="#0f5f57" stroke-width="6" stroke-linecap="round" fill="none"/>'
    '<path d="M120 126 C86 126 66 104 64 80 C92 80 116 96 120 126 Z" fill="#0f5f57"/>'
    '<path d="M120 108 C148 108 168 90 172 64 C144 64 122 80 120 108 Z" fill="#2f8f80"/>'
    '<path d="M92 178 H148 L142 208 H98 Z" fill="#d98b5f"/>'
    '<rect x="88" y="172" width="64" height="10" rx="5" fill="#c4764b"/>'
    '</svg>'
    '<div class="ks-hero-text">'
    '<div class="ks-eyebrow">A little space to think things through</div>'
    '<h1>Meet you where you are.</h1>'
    '<p>KindSpace is a private AI assistant for everyday questions, reflection, planning, and encouragement.</p>'
    '</div>'
    '</section>'
    '<div class="ks-features">'
    '<div class="ks-feature"><strong>Private by design</strong><span>Your conversations stay in your own account.</span></div>'
    '<div class="ks-feature"><strong>Ready when you are</strong><span>Ask, plan, or reflect at any hour.</span></div>'
    '<div class="ks-feature"><strong>Your pace, your tone</strong><span>Choose warm, direct, or encouraging replies.</span></div>'
    '</div>'
)
