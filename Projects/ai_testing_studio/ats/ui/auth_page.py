"""The welcome, sign-in and sign-up page in the studio's yellow cyberpunk look: hero, animated pipeline terminal and a glowing card."""

from __future__ import annotations

import html

import streamlit as st

from ats.accounts import service
from ats.accounts.social import SocialLoginError, github_authorization_url, github_is_configured, google_is_configured
from ats.ui.auth_session import ERROR_KEY, sign_in

_VIEW = "auth_view"  # "login" or "reset"
_RESET = "auth_reset_state"
_NOTICE = "auth_notice"

_GOOGLE_ICON = (
    "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 18 18'>"
    "<path fill='%234285F4' d='M17.64 9.2045c0-.638-.0573-1.2518-.1636-1.8409H9v3.4814h4.8436c-.2086 1.125-.8427 2.0782-1.7959 2.7164v2.2581h2.9087c1.7018-1.5668 2.6836-3.874 2.6836-6.615z'/>"
    "<path fill='%2334A853' d='M9 18c2.43 0 4.4673-.806 5.9564-2.1805l-2.9087-2.2581c-.8059.54-1.8368.859-3.0477.859-2.344 0-4.3282-1.5831-5.0359-3.7104H.9574v2.3318C2.4382 15.9832 5.4818 18 9 18z'/>"
    "<path fill='%23FBBC05' d='M3.9641 10.71c-.18-.54-.2823-1.1168-.2823-1.71s.1023-1.17.2823-1.71V4.9582H.9573C.3477 6.1732 0 7.5477 0 9s.3477 2.8268.9573 4.0418L3.9641 10.71z'/>"
    "<path fill='%23EA4335' d='M9 3.5795c1.3214 0 2.5077.4541 3.4405 1.346l2.5813-2.5814C13.4632.8918 11.426 0 9 0 5.4818 0 2.4382 2.0168.9573 4.9582L3.9641 7.29C4.6718 5.1627 6.6559 3.5795 9 3.5795z'/>"
    "</svg>\")"
)
# A ring around a git branch: a mark that needs no copied vector data.
_GITHUB_ICON = (
    "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16' fill='none' stroke='%23EDEBDD' stroke-width='1.3' stroke-linecap='round'>"
    "<circle cx='8' cy='8' r='7'/><circle cx='5.6' cy='5' r='1.2' fill='%23EDEBDD' stroke='none'/><circle cx='5.6' cy='11' r='1.2' fill='%23EDEBDD' stroke='none'/>"
    "<circle cx='10.6' cy='6.8' r='1.2' fill='%23EDEBDD' stroke='none'/><path d='M5.6 6.2v3.6M5.6 8.6c3.2 0 4.8-.6 5-1.6'/></svg>\")"
)

_CSS = (
    r"""
<style>
@property --au-ang { syntax: '<angle>'; initial-value: 0deg; inherits: false; }
@keyframes au-spin { to { --au-ang: 360deg; } }
@keyframes au-rise { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: none; } }
@keyframes au-line { from { opacity: 0; transform: translateX(-10px); } to { opacity: 1; transform: none; } }
@keyframes au-fill { from { width: 0; } to { width: var(--to); } }
@keyframes au-blink { 50% { opacity: 0; } }
@keyframes au-pulse { 0% { box-shadow: 0 0 0 0 rgba(57, 255, 136, .7); } 70%, 100% { box-shadow: 0 0 0 9px rgba(57, 255, 136, 0); } }
@keyframes au-sweep { from { transform: translateY(-110%); } to { transform: translateY(420%); } }
@keyframes au-shimmer { from { background-position: 0 0; } to { background-position: 24px 0; } }

[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], [data-testid="stSidebarCollapseButton"] { display: none !important; }
.block-container { max-width: 1180px; padding-top: 2.6rem; }
.stElementContainer:has(> iframe[height="1"]), .stElementContainer:has(iframe[height="1"]) { position: absolute; width: 1px; height: 1px; overflow: hidden; opacity: 0; }

/* ---------- Left: product story ---------- */
.au-hero { position: relative; padding: 4px 2px; animation: au-rise .7s ease both; }
.au-kicker { display: inline-flex; align-items: center; gap: 10px; font-family: 'Share Tech Mono', Consolas, monospace; font-size: .76rem; letter-spacing: .26em; text-transform: uppercase; color: #00E5FF; margin-bottom: 16px; }
.au-kicker i { width: 8px; height: 8px; background: #39FF88; animation: au-pulse 2s infinite; }
.au-hero h1 {
  font-family: 'Orbitron', 'Segoe UI', sans-serif !important; margin: 0 0 16px; padding: 0; line-height: 1.12; font-weight: 900; letter-spacing: .02em;
  font-size: clamp(1.7rem, 3.3vw, 2.65rem) !important; color: #EDEBDD; text-shadow: none;
}
.au-hero h1 span {
  display: block; color: #FFE600; text-shadow: 0 0 22px rgba(255, 230, 0, .45);
  background: linear-gradient(100deg, #FFE600 0%, #FFF27A 55%, #00E5FF 130%); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent;
}
.au-lead { color: #A9A692; font-size: 1.12rem; line-height: 1.55; max-width: 34rem; margin: 0 0 22px; }

.au-term {
  position: relative; max-width: 34rem; padding: 12px 16px 14px; overflow: hidden; font-family: 'Share Tech Mono', Consolas, monospace; font-size: .86rem; color: #8D8A72;
  background: linear-gradient(160deg, rgba(255, 230, 0, .07), rgba(8, 8, 11, .92) 45%); border: 1px solid #3D3811; border-left: 3px solid #FFE600;
  clip-path: polygon(0 0, calc(100% - 18px) 0, 100% 18px, 100% 100%, 0 100%);
}
.au-term::before { content: ""; position: absolute; inset: 0; pointer-events: none; background: repeating-linear-gradient(0deg, rgba(255, 255, 255, .022) 0 1px, transparent 1px 4px); }
.au-term::after { content: ""; position: absolute; left: 0; right: 0; top: 0; height: 28%; pointer-events: none; background: linear-gradient(180deg, transparent, rgba(0, 229, 255, .07), transparent); animation: au-sweep 5.5s linear infinite; }
.au-bar { display: flex; align-items: center; gap: 6px; margin-bottom: 10px; padding-bottom: 8px; border-bottom: 1px dashed #3D3811; }
.au-bar b { width: 8px; height: 8px; background: #FFE600; } .au-bar b:nth-child(2) { background: #00E5FF; } .au-bar b:nth-child(3) { background: #FF2E88; }
.au-bar em { margin-left: 8px; font-style: normal; letter-spacing: .12em; color: #8D8A72; text-transform: uppercase; font-size: .72rem; }
.au-row { position: relative; display: flex; align-items: center; gap: 10px; padding: 3px 0; opacity: 0; animation: au-line .5s ease forwards; animation-delay: calc(var(--i) * .5s + .3s); }
.au-row .st { flex: none; width: 1.1rem; text-align: center; color: #39FF88; }
.au-row.run .st { color: #FFE600; } .au-row.wait .st { color: #8D8A72; }
.au-row .nm { flex: 0 0 7.4rem; color: #EDEBDD; letter-spacing: .04em; }
.au-row.wait .nm { color: #8D8A72; }
.au-row .mt { flex: 1; height: 6px; background: rgba(255, 255, 255, .07); overflow: hidden; }
.au-row .mt i { display: block; height: 100%; width: 0; background: #FFE600; box-shadow: 0 0 10px rgba(255, 230, 0, .6); animation: au-fill 1.3s ease forwards; animation-delay: calc(var(--i) * .5s + .5s); }
.au-row.run .mt i { background: repeating-linear-gradient(115deg, #00E5FF 0 8px, #00B8CC 8px 16px); box-shadow: 0 0 10px rgba(0, 229, 255, .6); animation: au-fill 1.3s ease forwards, au-shimmer .6s linear infinite; animation-delay: calc(var(--i) * .5s + .5s), 0s; }
.au-row.wait .mt i { background: #3D3811; box-shadow: none; }
.au-row .pc { flex: none; width: 2.7rem; text-align: right; color: #8D8A72; }
.au-prompt { margin-top: 8px; color: #FFE600; opacity: 0; animation: au-line .5s ease forwards; animation-delay: 4.1s; }
.au-prompt i { display: inline-block; width: 8px; height: 14px; margin-left: 5px; background: #FFE600; vertical-align: -2px; animation: au-blink 1s steps(1) infinite; }

.au-chips { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin-top: 20px; max-width: 34rem; }
.au-chip {
  display: flex; align-items: center; gap: 10px; padding: 9px 12px; background: rgba(17, 17, 22, .8); border: 1px solid #3D3811; animation: au-rise .8s ease both;
  clip-path: polygon(0 0, calc(100% - 10px) 0, 100% 10px, 100% 100%, 0 100%); transition: border-color .15s ease, background .15s ease;
}
.au-chip:hover { border-color: #FFE600; background: rgba(255, 230, 0, .07); }
.au-chip b { flex: none; min-width: 2.7rem; padding: 2px 4px; text-align: center; font-family: 'Share Tech Mono', Consolas, monospace; font-weight: 400; font-size: .7rem; letter-spacing: .08em; color: #00E5FF; border: 1px solid rgba(0, 229, 255, .5); background: rgba(0, 229, 255, .07); }
.au-chip span { font-family: 'Rajdhani', 'Segoe UI', sans-serif; font-weight: 600; font-size: .98rem; letter-spacing: .05em; text-transform: uppercase; color: #EDEBDD; line-height: 1.1; }
.au-chip:nth-child(2) { animation-delay: .1s; } .au-chip:nth-child(3) { animation-delay: .2s; } .au-chip:nth-child(4) { animation-delay: .3s; }

/* ---------- Right: glowing sign-in card ---------- */
[data-testid="stColumn"]:has(.st-key-auth_card) { filter: drop-shadow(0 0 26px rgba(255, 230, 0, .22)) drop-shadow(0 0 60px rgba(0, 229, 255, .12)); }
.st-key-auth_card {
  position: relative; padding: 28px 28px 20px; border: 1.5px solid transparent;
  background:
    linear-gradient(155deg, rgba(22, 22, 28, .97), rgba(8, 8, 11, .98)) padding-box,
    conic-gradient(from var(--au-ang), #FFE600, rgba(255, 230, 0, .1) 22%, #00E5FF 45%, rgba(0, 229, 255, .1) 62%, #FF2E88 80%, #FFE600) border-box;
  clip-path: polygon(0 0, calc(100% - 24px) 0, 100% 24px, 100% 100%, 24px 100%, 0 calc(100% - 24px));
  animation: au-spin 8s linear infinite, au-rise .7s ease both;
}
.st-key-auth_card > * { position: relative; z-index: 1; }
.au-head { display: flex; align-items: center; gap: 14px; margin-bottom: 14px; }
.au-logo { flex: none; width: 44px; height: 44px; background: #FFE600; clip-path: polygon(0 0, 100% 0, 100% 62%, 62% 100%, 0 100%); box-shadow: 0 0 18px rgba(255, 230, 0, .6); }
.au-title { font-family: 'Orbitron', 'Segoe UI', sans-serif; font-weight: 700; font-size: 1.12rem; letter-spacing: .06em; text-transform: uppercase; color: #FFE600; line-height: 1.2; text-shadow: 0 0 14px rgba(255, 230, 0, .35); }
.au-sub { font-family: 'Share Tech Mono', Consolas, monospace; font-size: .76rem; letter-spacing: .03em; color: #8D8A72; margin-top: 3px; }
.au-or { display: flex; align-items: center; gap: 12px; margin: 14px 0 8px; color: #8D8A72; font-family: 'Share Tech Mono', Consolas, monospace; font-size: .72rem; letter-spacing: .22em; text-transform: uppercase; }
.au-or::before, .au-or::after { content: ""; flex: 1; height: 1px; background: linear-gradient(90deg, transparent, #3D3811 40%, #3D3811 60%, transparent); }
.au-fine { color: #8D8A72; font-family: 'Share Tech Mono', Consolas, monospace; font-size: .72rem; text-align: center; margin: 12px 0 0; }
.au-note { color: #A9A692; font-size: 1rem; margin: 4px 0 10px; }
.au-note b { color: #FFE600; font-weight: 600; }

/* social buttons */
.st-key-auth_card .st-key-auth_google button[data-testid^="stBaseButton"], .st-key-auth_card .st-key-auth_google_off button[data-testid^="stBaseButton"],
.st-key-auth_card .st-key-auth_github_off button[data-testid^="stBaseButton"], .st-key-auth_card .st-key-auth_github a {
  display: flex; align-items: center; justify-content: center; gap: 10px; width: 100%; min-height: 2.6rem; box-sizing: border-box; cursor: pointer; text-decoration: none;
  font-family: 'Orbitron', 'Segoe UI', sans-serif; font-size: .74rem; font-weight: 700; letter-spacing: .12em; text-transform: uppercase;
  background: rgba(237, 235, 221, .04) !important; color: #EDEBDD !important; border: 1px solid #3D3811 !important; border-radius: 0 !important;
  clip-path: polygon(0 0, calc(100% - 10px) 0, 100% 10px, 100% 100%, 10px 100%, 0 calc(100% - 10px)); transition: background .15s ease, border-color .15s ease, transform .12s ease;
}
.st-key-auth_card .st-key-auth_google button:hover, .st-key-auth_card .st-key-auth_github a:hover { background: rgba(255, 230, 0, .1) !important; border-color: #FFE600 !important; transform: translateY(-1px); }
.st-key-auth_card .st-key-auth_github a p, .st-key-auth_card .st-key-auth_google button p, .st-key-auth_card .st-key-auth_google_off button p, .st-key-auth_card .st-key-auth_github_off button p { color: #EDEBDD !important; font-size: inherit; margin: 0; }
.st-key-auth_google button::before, .st-key-auth_google_off button::before { content: ""; flex: none; width: 18px; height: 18px; background: """
    + _GOOGLE_ICON
    + r""" center / contain no-repeat; }
.st-key-auth_github a::before, .st-key-auth_github_off button::before { content: ""; flex: none; width: 18px; height: 18px; background: """
    + _GITHUB_ICON
    + r""" center / contain no-repeat; }

/* tabs read as a segmented switch inside the card */
.st-key-auth_card [data-baseweb="tab-list"] { display: flex !important; width: 100%; box-sizing: border-box; gap: 4px !important; padding: 4px !important; border: 1px solid #3D3811 !important; background: rgba(255, 255, 255, .03); }
.st-key-auth_card [data-baseweb="tab"] { flex: 1 1 0; min-width: 0; display: flex; align-items: center; justify-content: center; height: auto !important; padding: 9px 12px !important; background: transparent; transition: background .15s ease; }
.st-key-auth_card [data-baseweb="tab"]:hover { background: rgba(255, 230, 0, .08); }
.st-key-auth_card [data-baseweb="tab"] p { font-family: 'Orbitron', 'Segoe UI', sans-serif; font-size: .72rem; letter-spacing: .12em; text-transform: uppercase; font-weight: 700; margin: 0; }
.st-key-auth_card [data-baseweb="tab"][aria-selected="true"], .st-key-auth_card [data-baseweb="tab"][aria-selected="true"]:hover { background: #FFE600 !important; box-shadow: 0 0 16px rgba(255, 230, 0, .35); }
.st-key-auth_card [data-baseweb="tab"][aria-selected="true"] p { color: #0A0A0A !important; }
.st-key-auth_card [data-baseweb="tab-highlight"], .st-key-auth_card [data-baseweb="tab-border"] { display: none !important; }
.st-key-auth_card [data-baseweb="tab-panel"] { padding-top: 14px; }
.st-key-auth_card [data-testid="stForm"] { padding: 0; border: none !important; background: transparent !important; }

/* text-style buttons: forgot password, back to log in */
.st-key-auth_forgot, .st-key-auth_back { display: flex; justify-content: center; }
.st-key-auth_forgot button, .st-key-auth_back button { background: transparent !important; border: none !important; box-shadow: none !important; min-height: 0; padding: 4px 10px; clip-path: none; }
.st-key-auth_forgot button p, .st-key-auth_back button p { color: #00E5FF !important; font-family: 'Share Tech Mono', Consolas, monospace; font-size: .8rem; letter-spacing: .06em; text-transform: none; }
.st-key-auth_forgot button:hover, .st-key-auth_back button:hover { background: rgba(0, 229, 255, .08) !important; }

@media (max-width: 900px) { .au-chips { grid-template-columns: 1fr; } .st-key-auth_card { padding: 22px 18px 16px; } }
@media (prefers-reduced-motion: reduce) {
  .au-hero, .au-chip, .st-key-auth_card, .au-kicker i, .au-term::after { animation: none !important; }
  .au-row, .au-prompt { opacity: 1; animation: none !important; }
  .au-row .mt i { animation: none !important; width: var(--to); }
  .au-prompt i { animation: none; }
}
</style>
"""
)


def _pipeline_row(index: int, name: str, state: str, percent: int) -> str:
    glyph = {"done": "&#10003;", "run": "&#9656;", "wait": "&middot;"}[state]
    label = "queued" if state == "wait" else f"{percent}%"
    return (
        f'<div class="au-row {state}" style="--i:{index};--to:{max(percent, 4)}%"><span class="st">{glyph}</span>'
        f'<span class="nm">{name}</span><span class="mt"><i></i></span><span class="pc">{label}</span></div>'
    )


_STAGES = [
    ("discover", "done", 100), ("scenarios", "done", 100), ("test_cases", "done", 100), ("automation", "done", 100),
    ("execute", "run", 72), ("heal", "run", 38), ("report", "wait", 0),
]  # fmt: skip
_CHIPS = [("UI+API", "UI + API testing"), ("HEAL", "Self-healing locators"), ("PR", "GitHub branch delivery"), ("BG", "Runs in the background")]

_HERO_HTML = (
    '<div class="au-hero"><div class="au-kicker"><i></i>RK Testing Studio &middot; Autonomous testing</div>'
    "<h1>Autonomous QA, from <span>discovery to report</span></h1>"
    '<p class="au-lead">Point the studio at a website. It explores the app, designs the scenarios, writes runnable UI and API tests, '
    "executes them, heals broken locators and hands you the report. Sign in and every project stays in your own workspace.</p>"
    '<div class="au-term"><div class="au-bar"><b></b><b></b><b></b><em>ats run --autonomous</em></div>'
    + "".join(_pipeline_row(i, name, state, percent) for i, (name, state, percent) in enumerate(_STAGES))
    + '<div class="au-prompt">$ monitoring run<i></i></div></div>'
    '<div class="au-chips">' + "".join(f"<div class=\"au-chip\"><b>{code}</b><span>{label}</span></div>" for code, label in _CHIPS) + "</div></div>"
)


def _head(title: str, subtitle: str) -> str:
    return f'<div class="au-head"><div class="au-logo"></div><div><div class="au-title">{html.escape(title)}</div><div class="au-sub">{html.escape(subtitle)}</div></div></div>'


def _social_buttons() -> None:
    google_col, github_col = st.columns(2)
    with google_col:
        if google_is_configured():
            if st.button("Google", key="auth_google", width="stretch"):
                st.login("google")
        else:
            st.button(
                "Google",
                key="auth_google_off",
                width="stretch",
                disabled=True,
                help="Add the [auth] and [auth.google] keys to .streamlit/secrets.toml to turn this on (see the README).",
            )
    with github_col:
        if github_is_configured():
            try:
                url = github_authorization_url()
            except SocialLoginError:
                url = ""
            if url:  # opens GitHub in a new tab: embedded apps cannot navigate the whole window
                st.link_button("GitHub", url, key="auth_github", width="stretch")
        else:
            st.button(
                "GitHub",
                key="auth_github_off",
                width="stretch",
                disabled=True,
                help="Add the [github] client_id and client_secret to .streamlit/secrets.toml to turn this on (see the README).",
            )


def _login_form() -> None:
    with st.form("auth_login_form", border=False):
        email = st.text_input("Email", key="auth_login_email", autocomplete="email", placeholder="you@company.com")
        password = st.text_input("Password", type="password", key="auth_login_password", autocomplete="current-password", placeholder="Your password")
        remember = st.checkbox("Keep me signed in on this device", value=True, key="auth_login_remember")
        submitted = st.form_submit_button("Log in", type="primary", width="stretch")
    if submitted:
        try:
            user = service.authenticate(email, password)
        except service.AuthError as exc:
            st.error(str(exc))
        else:
            sign_in(user, remember)
            st.rerun()
    if st.button("Forgot password?", key="auth_forgot", type="tertiary"):
        st.session_state[_VIEW] = "reset"
        st.session_state.pop(_RESET, None)
        st.rerun()


def _reset_view() -> None:
    """Forgot password: ask for the email, then (after the emailed code, when email is set up) choose a new password."""
    state = st.session_state.get(_RESET)
    if not state:
        st.markdown('<div class="au-note">Enter the email address on your account.</div>', unsafe_allow_html=True)
        with st.form("auth_reset_email_form", border=False):
            email = st.text_input("Email", key="auth_reset_email", autocomplete="email", placeholder="you@company.com")
            submitted = st.form_submit_button("Continue", type="primary", width="stretch")
        if submitted:
            try:
                st.session_state[_RESET] = service.begin_password_reset(email)
            except service.AuthError as exc:
                st.error(str(exc))
            else:
                st.rerun()
    else:
        st.markdown(
            f'<div class="au-note">Choose a new password for <b>{html.escape(str(state["email"]))}</b>.'
            + (" We emailed you a 6-digit code; it works for 15 minutes." if state["needs_code"] else "")
            + "</div>",
            unsafe_allow_html=True,
        )
        with st.form("auth_reset_password_form", border=False):
            code = (
                st.text_input("Code from your email", key="auth_reset_code", max_chars=6, autocomplete="one-time-code", placeholder="6 digits")
                if state["needs_code"]
                else ""
            )
            password = st.text_input("New password", type="password", key="auth_reset_password", autocomplete="new-password", placeholder="Create a strong password")
            confirm = st.text_input("Confirm new password", type="password", key="auth_reset_confirm", autocomplete="new-password", placeholder="Type it once more")
            submitted = st.form_submit_button("Update password", type="primary", width="stretch")
        if submitted:
            try:
                service.finish_password_reset(str(state["id"]), code, password, confirm, bool(state["needs_code"]))
            except service.AuthError as exc:
                st.error(str(exc))
            else:
                st.session_state[_NOTICE] = "Password updated. Log in with your new password."
                _leave_reset()
                st.rerun()
    st.markdown('<div class="au-fine">Signed up with Google or GitHub? Keep using those buttons on the log in page.</div>', unsafe_allow_html=True)
    if st.button("Back to log in", key="auth_back", type="tertiary"):
        _leave_reset()
        st.rerun()


def _leave_reset() -> None:
    st.session_state[_VIEW] = "login"
    st.session_state.pop(_RESET, None)


def _signup_form() -> None:
    with st.form("auth_signup_form", border=False):
        name = st.text_input("Your name", key="auth_signup_name", autocomplete="name", max_chars=80, placeholder="How should we call you?")
        email = st.text_input("Email", key="auth_signup_email", autocomplete="email", max_chars=254, placeholder="you@company.com")
        password = st.text_input(
            "Password",
            type="password",
            key="auth_signup_password",
            autocomplete="new-password",
            placeholder="At least 8 characters, with a letter and a number",
        )
        confirm = st.text_input("Confirm password", type="password", key="auth_signup_confirm", autocomplete="new-password", placeholder="Type it once more")
        submitted = st.form_submit_button("Create my account", type="primary", width="stretch")
    if submitted:
        try:
            user = service.create_account(name, email, password, confirm)
        except service.AuthError as exc:
            st.error(str(exc))
            return
        sign_in(user, True)
        st.rerun()


def render_auth_page() -> None:
    """Welcome page for visitors who are not signed in. Expects ``theme.apply()`` to have loaded the fonts."""
    st.markdown(_CSS, unsafe_allow_html=True)
    left, right = st.columns([1.15, 1], gap="large", vertical_alignment="center")
    with left:
        st.markdown(_HERO_HTML, unsafe_allow_html=True)
    with right:
        with st.container(key="auth_card"):
            if st.session_state.get(_VIEW) == "reset":
                st.markdown(_head("Reset your password", "We'll get you back into your studio."), unsafe_allow_html=True)
                _reset_view()
                return
            st.markdown(_head("Welcome to RK Testing Studio","Log in or create an account to open your workspace."), unsafe_allow_html=True)
            message = st.session_state.pop(ERROR_KEY, None)
            if message:
                st.error(message)
            notice = st.session_state.pop(_NOTICE, None)
            if notice:
                st.success(notice)
            _social_buttons()
            st.markdown('<div class="au-or">or use your email</div>', unsafe_allow_html=True)
            login_tab, signup_tab = st.tabs(["Log in", "Create account"])
            with login_tab:
                _login_form()
            with signup_tab:
                _signup_form()
            st.markdown('<div class="au-fine">Every account gets a private workspace.</div>', unsafe_allow_html=True)
