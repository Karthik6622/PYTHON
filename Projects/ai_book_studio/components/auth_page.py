"""The sign-in and sign-up page: the Ember Forge look with a glowing card, a live "forge" terminal and social buttons."""

from __future__ import annotations

import html

import streamlit as st

from components.auth_session import ERROR_KEY, sign_in
from components.styles import apply_styles
from config import APP_ICON, APP_NAME
from services import auth_service
from services.social_auth import (
    SocialLoginError,
    github_authorization_url,
    github_is_configured,
    google_is_configured,
)

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
_GITHUB_PATH = (
    "M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"
)
_GITHUB_SVG = f"<svg viewBox='0 0 16 16' width='18' height='18' aria-hidden='true'><path fill='#FFF4EA' d='{_GITHUB_PATH}'/></svg>"

_CSS = (
    r"""
<style>
@property --ang { syntax: '<angle>'; initial-value: 0deg; inherits: false; }
@keyframes auth-spin { to { --ang: 360deg; } }
@keyframes auth-rise { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: none; } }
@keyframes auth-line { from { opacity: 0; transform: translateX(-10px); } to { opacity: 1; transform: none; } }
@keyframes auth-fill { from { width: 0; } to { width: var(--to); } }
@keyframes auth-blink { 50% { opacity: 0; } }
@keyframes auth-float { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-9px); } }
@keyframes auth-orbit { to { transform: rotate(360deg); } }

[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] { display: none !important; }
.block-container { max-width: 1180px; padding-top: 2.2rem; }

/* ---------- Left: brand story ---------- */
.auth-hero { position: relative; padding: 8px 4px; animation: auth-rise .7s ease both; }
.auth-hero .kicker {
  display: inline-flex; align-items: center; gap: 9px; font-size: .72rem; font-weight: 700;
  letter-spacing: .22em; text-transform: uppercase; color: var(--amber); margin-bottom: 14px;
}
.auth-hero .kicker i { width: 8px; height: 8px; border-radius: 50%; background: var(--ok); box-shadow: 0 0 0 0 rgba(94, 234, 168, .7); animation: pulse-dot 2s infinite; }
.auth-hero h1 {
  font-family: var(--display); margin: 0 0 14px; padding: 0; line-height: 1.04; font-weight: 700; letter-spacing: -.025em;
  font-size: clamp(2.2rem, 4.6vw, 3.6rem); color: var(--ink);
}
.auth-hero h1 span {
  background: linear-gradient(100deg, #FFC24D 0%, #FF7A1F 55%, #FF4D6A 100%);
  -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; color: transparent;
}
.auth-hero p.lead { color: var(--muted); font-size: 1.05rem; line-height: 1.6; max-width: 34rem; margin: 0 0 22px; }

.auth-term {
  position: relative; max-width: 34rem; border-radius: 16px; padding: 14px 16px 16px; overflow: hidden;
  font-family: 'JetBrains Mono', ui-monospace, 'Cascadia Code', Consolas, monospace; font-size: .8rem; color: var(--muted);
  background: linear-gradient(160deg, rgba(255, 255, 255, .06), rgba(255, 255, 255, .015));
  border: 1px solid var(--line); box-shadow: 0 24px 50px -30px rgba(255, 106, 31, .7);
  backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px); animation: auth-float 7s ease-in-out infinite;
}
.auth-term::before {
  content: ""; position: absolute; inset: 0; pointer-events: none;
  background: repeating-linear-gradient(0deg, rgba(255, 255, 255, .02) 0 1px, transparent 1px 4px);
}
.auth-term .bar { display: flex; gap: 6px; margin-bottom: 12px; }
.auth-term .bar b { width: 9px; height: 9px; border-radius: 50%; background: rgba(255, 255, 255, .16); }
.auth-term .bar b:nth-child(1) { background: #FF5F57; } .auth-term .bar b:nth-child(2) { background: #FEBC2E; } .auth-term .bar b:nth-child(3) { background: #28C840; }
.auth-term .row { display: flex; align-items: center; gap: 10px; padding: 3px 0; opacity: 0; animation: auth-line .5s ease forwards; }
.auth-term .row:nth-of-type(1) { animation-delay: .3s; } .auth-term .row:nth-of-type(2) { animation-delay: .9s; }
.auth-term .row:nth-of-type(3) { animation-delay: 1.5s; } .auth-term .row:nth-of-type(4) { animation-delay: 2.1s; }
.auth-term .row:nth-of-type(5) { animation-delay: 2.7s; }
.auth-term .tick { color: var(--ok); } .auth-term .run { color: var(--amber); } .auth-term .name { color: var(--ink); flex: 0 0 9.5rem; }
.auth-term .meter { flex: 1; height: 5px; border-radius: 9px; background: rgba(255, 255, 255, .08); overflow: hidden; }
.auth-term .meter i { display: block; height: 100%; width: 0; border-radius: 9px; background: var(--grad); box-shadow: 0 0 10px var(--glow); animation: auth-fill 1.4s ease forwards; animation-delay: inherit; --to: 100%; }
.auth-term .row:nth-of-type(4) .meter i { --to: 72%; }
.auth-term .row:nth-of-type(5) .meter i { --to: 38%; }
.auth-term .cursor { display: inline-block; width: 8px; height: 14px; margin-left: 4px; background: var(--amber); vertical-align: -2px; animation: auth-blink 1s steps(1) infinite; }

.auth-stats { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 22px; max-width: 34rem; }
.auth-stats span {
  display: inline-flex; align-items: center; gap: 8px; padding: 7px 14px; border-radius: 999px; font-size: .82rem; font-weight: 600; color: var(--ink);
  background: rgba(255, 255, 255, .05); border: 1px solid var(--line); animation: auth-rise .8s ease both;
}
.auth-stats span b { color: var(--amber); font-family: var(--display); }
.auth-stats span:nth-child(2) { animation-delay: .1s; } .auth-stats span:nth-child(3) { animation-delay: .2s; } .auth-stats span:nth-child(4) { animation-delay: .3s; }

/* ---------- Right: glowing sign-in card ---------- */
.st-key-auth_card {
  position: relative; padding: 30px 30px 22px; border-radius: 24px; border: 1.5px solid transparent;
  background:
    linear-gradient(150deg, rgba(32, 16, 9, .94), rgba(13, 7, 5, .96)) padding-box,
    conic-gradient(from var(--ang), rgba(255, 106, 31, .95), rgba(255, 194, 77, .18) 25%, rgba(255, 77, 106, .8) 50%, rgba(255, 194, 77, .18) 75%, rgba(255, 106, 31, .95)) border-box;
  animation: auth-spin 9s linear infinite, auth-rise .7s ease both;
  box-shadow: 0 40px 80px -40px rgba(255, 106, 31, .8), 0 0 90px -30px rgba(255, 77, 106, .45);
}
.st-key-auth_card::before {
  content: ""; position: absolute; z-index: 0; pointer-events: none; inset: -1px; border-radius: 24px;
  background: radial-gradient(420px 220px at 85% -10%, rgba(255, 138, 43, .18), transparent 70%);
}
.st-key-auth_card > * { position: relative; z-index: 1; }
.auth-head { display: flex; align-items: center; gap: 14px; margin-bottom: 4px; }
.auth-head .logo {
  width: 46px; height: 46px; border-radius: 14px; display: grid; place-items: center; font-size: 1.5rem; flex: none;
  background: var(--grad); box-shadow: 0 0 26px var(--glow); color: #1A0A02;
}
.auth-head h2 { margin: 0 !important; padding: 0 !important; font-size: 1.45rem !important; line-height: 1.15; }
.auth-head h2::before { display: none !important; }
.auth-head small { display: block; color: var(--muted); font-size: .85rem; margin-top: 2px; }
.auth-or {
  display: flex; align-items: center; gap: 12px; margin: 14px 0 6px; color: var(--dim);
  font-size: .72rem; letter-spacing: .2em; text-transform: uppercase;
}
.auth-or::before, .auth-or::after { content: ""; flex: 1; height: 1px; background: linear-gradient(90deg, transparent, var(--line-2), transparent); }
.auth-fine { color: var(--dim); font-size: .76rem; text-align: center; margin: 10px 0 0; }

/* social buttons */
.st-key-auth_google button, a.auth-oauth {
  display: flex; align-items: center; justify-content: center; gap: 10px; width: 100%; min-height: 2.75rem; border-radius: 12px;
  font-weight: 600; text-decoration: none; cursor: pointer; box-sizing: border-box;
  border: 1px solid var(--line-2); background: rgba(255, 255, 255, .05); color: var(--ink) !important;
  transition: transform .2s ease, border-color .2s ease, box-shadow .2s ease, background .2s ease;
}
.st-key-auth_google button:hover, a.auth-oauth:hover {
  transform: translateY(-2px); border-color: var(--amber); background: rgba(255, 138, 43, .12); box-shadow: 0 10px 26px -14px var(--glow);
}
.st-key-auth_google button::before { content: ""; width: 18px; height: 18px; background: """
    + _GOOGLE_ICON
    + r""" center / contain no-repeat; }
.st-key-auth_google button p { color: var(--ink) !important; }
a.auth-oauth svg { flex: none; }
.auth-oauth-off { opacity: .45; pointer-events: none; }
.st-key-auth_github_off button { display: flex; align-items: center; justify-content: center; gap: 10px; }
.st-key-auth_github_off button::before { content: ""; width: 18px; height: 18px; background: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'><path fill='%23FFF4EA' d='"""
    + _GITHUB_PATH
    + r"""'/></svg>") center / contain no-repeat; }
.st-key-auth_google_off button { display: flex; align-items: center; justify-content: center; gap: 10px; }
.st-key-auth_google_off button::before { content: ""; width: 18px; height: 18px; background: """
    + _GOOGLE_ICON
    + r""" center / contain no-repeat; }

/* tabs read as a segmented switch inside the card */
.st-key-auth_card .stTabs [role="tablist"] {
  display: flex !important; width: 100%; box-sizing: border-box; overflow: visible !important; gap: 6px !important; padding: 5px !important;
  border-bottom: none !important; border-radius: 999px !important; background: rgba(255, 255, 255, .05); border: 1px solid var(--line);
}
.st-key-auth_card .stTabs [role="tab"] {
  flex: 1 1 0; min-width: 0; display: flex; align-items: center; justify-content: center; height: auto !important; padding: 10px 14px !important;
  border-radius: 999px !important; background: transparent; transition: background .2s ease, box-shadow .2s ease;
}
.st-key-auth_card .stTabs [role="tab"]:hover { background: rgba(255, 138, 43, .12); }
.st-key-auth_card .stTabs [role="tab"][aria-selected="true"], .st-key-auth_card .stTabs [role="tab"][aria-selected="true"]:hover {
  background: var(--grad) !important; box-shadow: 0 8px 22px -10px var(--glow);
}
.st-key-auth_card .stTabs [role="tab"][aria-selected="true"] p { color: #1A0A02 !important; font-weight: 700; }
.st-key-auth_card .stTabs [role="tablist"] > :not([role="tab"]) { display: none !important; }
.st-key-auth_card .stTabs [role="tabpanel"] { padding-top: 14px; }
.st-key-auth_card [data-testid="stForm"] { padding: 0; }

/* text-style buttons: forgot password, back to log in */
.st-key-auth_forgot, .st-key-auth_back { display: flex; justify-content: center; }
.st-key-auth_forgot button, .st-key-auth_back button {
  background: transparent !important; border: none !important; box-shadow: none !important; min-height: 0; padding: 4px 10px; border-radius: 999px;
}
.st-key-auth_forgot button p, .st-key-auth_back button p { color: var(--amber) !important; font-size: .86rem; font-weight: 600; }
.st-key-auth_forgot button:hover, .st-key-auth_back button:hover { background: rgba(255, 138, 43, .12) !important; }
.auth-note { color: var(--muted); font-size: .92rem; margin: 6px 0 10px; }
.auth-note b { color: var(--amber); font-weight: 600; }

@media (max-width: 900px) { .auth-term { animation: none; } .st-key-auth_card { padding: 22px 18px 18px; } }
@media (prefers-reduced-motion: reduce) { .auth-term, .st-key-auth_card, .auth-hero, .auth-stats span { animation: none !important; } .auth-term .row { opacity: 1; animation: none; } .auth-term .meter i { animation: none; width: var(--to); } }
</style>
"""
)

_HERO_HTML = """
<div class="auth-hero">
  <div class="kicker"><i></i>Ember Forge &middot; AI publishing suite</div>
  <h1>Your ideas, <span>forged into real books.</span></h1>
  <p class="lead">Sign in to keep every project safe. Your plans, chapters, covers and exports are saved to your account, so they are
  waiting for you after a refresh, on another tab or on another device.</p>
  <div class="auth-term">
    <div class="bar"><b></b><b></b><b></b></div>
    <div class="row"><span class="tick">&#10003;</span><span class="name">plan.chapters</span><span class="meter"><i></i></span></div>
    <div class="row"><span class="tick">&#10003;</span><span class="name">write.chapters</span><span class="meter"><i></i></span></div>
    <div class="row"><span class="tick">&#10003;</span><span class="name">review.quality</span><span class="meter"><i></i></span></div>
    <div class="row"><span class="run">&#9656;</span><span class="name">illustrate.cover</span><span class="meter"><i></i></span></div>
    <div class="row"><span class="run">&#9656;</span><span class="name">export.pdf+docx</span><span class="meter"><i></i></span><span class="cursor"></span></div>
  </div>
  <div class="auth-stats"><span><b>7</b> languages</span><span><b>PDF</b> &middot; DOCX &middot; audio</span><span><b>Auto</b> quality review</span></div>
</div>
"""


def _head(title: str, subtitle: str) -> str:
    return (
        f'<div class="auth-head"><div class="logo">{APP_ICON}</div>'
        f"<div><h2>{html.escape(title)}</h2><small>{html.escape(subtitle)}</small></div></div>"
    )


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
            if url:
                st.markdown(
                    f'<a class="auth-oauth" href="{html.escape(url, quote=True)}" target="_top" rel="noopener">{_GITHUB_SVG}GitHub</a>',
                    unsafe_allow_html=True,
                )
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
        email = st.text_input("Email", key="auth_login_email", autocomplete="email", placeholder="you@example.com")
        password = st.text_input("Password", type="password", key="auth_login_password", autocomplete="current-password", placeholder="Your password")
        remember = st.checkbox("Keep me signed in on this device", value=True, key="auth_login_remember")
        submitted = st.form_submit_button("Log in", type="primary", width="stretch")
    if submitted:
        try:
            user = auth_service.authenticate(email, password)
        except auth_service.AuthError as exc:
            st.error(str(exc))
            return
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
        st.markdown('<div class="auth-note">Enter the email address on your account.</div>', unsafe_allow_html=True)
        with st.form("auth_reset_email_form", border=False):
            email = st.text_input("Email", key="auth_reset_email", autocomplete="email", placeholder="you@example.com")
            submitted = st.form_submit_button("Continue", type="primary", width="stretch")
        if submitted:
            try:
                st.session_state[_RESET] = auth_service.begin_password_reset(email)
            except auth_service.AuthError as exc:
                st.error(str(exc))
                return
            st.rerun()
    else:
        st.markdown(
            f'<div class="auth-note">Choose a new password for <b>{html.escape(str(state["email"]))}</b>.'
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
                auth_service.finish_password_reset(str(state["id"]), code, password, confirm, bool(state["needs_code"]))
            except auth_service.AuthError as exc:
                st.error(str(exc))
                return
            st.session_state[_NOTICE] = "Password updated. Log in with your new password."
            _leave_reset()
            st.rerun()
    st.markdown('<div class="auth-fine">Signed up with Google or GitHub? You can keep using those buttons on the log in page.</div>', unsafe_allow_html=True)
    if st.button("Back to log in", key="auth_back", type="tertiary"):
        _leave_reset()
        st.rerun()


def _leave_reset() -> None:
    st.session_state[_VIEW] = "login"
    st.session_state.pop(_RESET, None)


def _signup_form() -> None:
    with st.form("auth_signup_form", border=False):
        name = st.text_input("Your name", key="auth_signup_name", autocomplete="name", max_chars=80, placeholder="How should we call you?")
        email = st.text_input("Email", key="auth_signup_email", autocomplete="email", max_chars=254, placeholder="you@example.com")
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
            user = auth_service.create_account(name, email, password, confirm)
        except auth_service.AuthError as exc:
            st.error(str(exc))
            return
        sign_in(user, True)
        st.rerun()


def render_auth_page() -> None:
    apply_styles()
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
            st.markdown(_head("Welcome to " + APP_NAME, "Log in or create an account to open your studio."), unsafe_allow_html=True)
            message = st.session_state.pop(ERROR_KEY, None)
            if message:
                st.error(message)
            notice = st.session_state.pop(_NOTICE, None)
            if notice:
                st.success(notice)
            _social_buttons()
            st.markdown('<div class="auth-or">or use your email</div>', unsafe_allow_html=True)
            login_tab, signup_tab = st.tabs(["Log in", "Create account"])
            with login_tab:
                _login_form()
            with signup_tab:
                _signup_form()
            st.markdown('<div class="auth-fine">Your books are private to your account.</div>', unsafe_allow_html=True)
