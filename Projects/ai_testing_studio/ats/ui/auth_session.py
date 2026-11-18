"""Browser sign-in state: who is signed in, the remember-me cookie, and sign-out.

A signed-in person's account id becomes the owner id of their projects (see ``ats.ui.session.owner_id``), so projects
follow the account instead of the browser and survive refreshes, new tabs and other devices.

The login cookie holds a random token. Only its SHA-256 digest is stored on the server, so the cookie value is the
only copy and a leaked database cannot be used to sign in.
"""

from __future__ import annotations

import re
from html import escape

import streamlit as st
import streamlit.components.v1 as components

from ats.accounts import service
from ats.accounts.social import SocialLoginError, complete_github_callback, google_identity
from ats.logging_setup import get_logger

LOGGER = get_logger("auth")

SESSION_COOKIE = "ats_session"
USER_KEY = "auth_user"
TOKEN_KEY = "auth_token"
COOKIE_MODE_KEY = "auth_cookie_mode"  # "persistent", "session" or "clear"
ERROR_KEY = "auth_error"
_TOKEN = re.compile(r"^[A-Za-z0-9_\-]{20,80}$")

_COOKIE_SCRIPT = """<script>
(function () {
  try {
    var P = window.parent, secure = P.location.protocol === 'https:' ? '; Secure' : '';
    P.document.cookie = '%(name)s=%(value)s; path=/; %(lifetime)sSameSite=Lax' + secure;
  } catch (e) {}
})();
</script>"""

_CHIP_CSS = """<style>
.ats-user { display: flex; align-items: center; gap: .6rem; padding: .55rem .6rem; margin: .4rem 0 .5rem; border: 1px solid var(--line, #3D3811); background: rgba(255, 230, 0, .05); }
.ats-user .av { flex: none; width: 30px; height: 30px; display: grid; place-items: center; background: var(--y, #FFE600); color: #0A0A0A; font-family: var(--display, sans-serif); font-weight: 900; font-size: .85rem; clip-path: polygon(0 0, 100% 0, 100% 70%, 70% 100%, 0 100%); }
.ats-user .who { min-width: 0; line-height: 1.15; }
.ats-user .who b { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-family: var(--display, sans-serif); font-size: .68rem; letter-spacing: .08em; text-transform: uppercase; color: var(--text, #EDEBDD); }
.ats-user .who span { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-family: var(--mono, monospace); font-size: .68rem; color: var(--dim, #8D8A72); }
</style>"""


def current_user() -> dict[str, str] | None:
    user = st.session_state.get(USER_KEY)
    return user if isinstance(user, dict) and user.get("id") else None


def _read_cookie() -> str | None:
    try:
        value = st.context.cookies.get(SESSION_COOKIE)
    except Exception:  # noqa: BLE001 - cookies are unavailable outside a real browser session (for example in tests)
        return None
    return value if isinstance(value, str) and _TOKEN.match(value) else None


def _run_script(html: str) -> None:
    if hasattr(st, "iframe"):
        st.iframe(html, height=1)
    else:
        components.html(html, height=0)


def sign_in(user: dict[str, str], remember: bool = True) -> None:
    """Mark the visitor as signed in and plan to store the login cookie."""
    st.session_state[USER_KEY] = service.public_user(user)
    st.session_state[TOKEN_KEY] = service.start_session(user["id"])
    st.session_state[COOKIE_MODE_KEY] = "persistent" if remember else "session"
    st.session_state.pop(ERROR_KEY, None)
    claim_browser_projects(user["id"])


def claim_browser_projects(user_id: str) -> None:
    """Projects made in this browser before accounts existed become the account's projects."""
    from ats.ui.session import browser_owner_ids, get_services

    try:
        repo = get_services().repo
        for old in browser_owner_ids():
            repo.transfer_owner(old, user_id)
    except Exception:  # noqa: BLE001 - never block signing in over a migration problem
        LOGGER.warning("Could not move this browser's projects to the account")


def restore_login() -> None:
    """Sign the visitor in again from Google's session or from the remember-me cookie (runs when nobody is signed in)."""
    if current_user():
        return
    try:
        google = google_identity()
    except SocialLoginError as exc:
        st.session_state[ERROR_KEY] = str(exc)
        google = None
    if google:
        try:
            sign_in(service.social_sign_in(google["provider"], google["subject"], google["email"], google["name"]))
            return
        except service.AuthError as exc:
            st.session_state[ERROR_KEY] = str(exc)
    token = _read_cookie()
    user = service.user_for_session(token)
    if user and token:
        st.session_state[USER_KEY] = user
        st.session_state[TOKEN_KEY] = token
        st.session_state[COOKIE_MODE_KEY] = "persistent"


def handle_github_callback() -> None:
    """Finish a GitHub sign-in when the visitor has just come back from GitHub."""
    if current_user():
        return
    try:
        identity = complete_github_callback()
        if identity is None:
            return
        sign_in(service.social_sign_in(identity["provider"], identity["subject"], identity["email"], identity["name"]))
    except (SocialLoginError, service.AuthError) as exc:
        st.session_state[ERROR_KEY] = str(exc)
    st.query_params.clear()
    st.rerun()


def sync_cookie() -> None:
    """Write or remove the login cookie in the browser. Renders nothing visible."""
    mode = st.session_state.get(COOKIE_MODE_KEY)
    token = st.session_state.get(TOKEN_KEY)
    if mode in ("persistent", "session") and isinstance(token, str) and _TOKEN.match(token):
        lifetime = f"max-age={service.SESSION_SECONDS}; " if mode == "persistent" else ""
        _run_script(_COOKIE_SCRIPT % {"name": SESSION_COOKIE, "value": token, "lifetime": lifetime})
    elif mode == "clear":
        _run_script(_COOKIE_SCRIPT % {"name": SESSION_COOKIE, "value": "", "lifetime": "max-age=0; "})


def sign_out() -> None:
    """End the session on the server, forget everything in this tab and remove the cookie."""
    service.end_session(st.session_state.get(TOKEN_KEY))
    google_signed_in = False
    try:
        google_signed_in = bool(st.user.is_logged_in)
    except Exception:  # noqa: BLE001
        pass
    st.session_state.clear()
    st.session_state[COOKIE_MODE_KEY] = "clear"
    if google_signed_in:
        st.logout()  # also reruns the app
    st.rerun()


def require_login() -> bool:
    """``True`` when someone is signed in. Otherwise the sign-in page is shown and the caller should stop."""
    handle_github_callback()
    restore_login()
    if current_user():
        sync_cookie()
        return True
    from ats.ui.auth_page import render_auth_page

    sync_cookie()  # removes a stale cookie right after signing out
    render_auth_page()
    return False


def user_chip() -> None:
    """Sidebar block: who is signed in, and a Sign out button."""
    user = current_user()
    if not user:
        return
    label = user["name"] or user["email"]
    st.markdown(
        f'{_CHIP_CSS}<div class="ats-user"><div class="av">{escape(label[:1].upper())}</div>'
        f'<div class="who"><b>{escape(user["name"])}</b><span>{escape(user["email"])}</span></div></div>',
        unsafe_allow_html=True,
    )
    if st.button("Sign out", key="auth_sign_out", icon=":material/logout:", width="stretch"):
        sign_out()
