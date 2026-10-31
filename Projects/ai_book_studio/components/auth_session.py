"""Browser sign-in state: who is signed in, the remember-me cookie, and sign-out.

A signed-in person's id becomes the owner id of their books (see ``components.identity.owner_id``), so their saved projects
follow the account instead of the browser and survive refreshes, new tabs and other devices.

The login cookie holds a random token. Only its SHA-256 digest is stored on the server, so the cookie value is the
only copy and a leaked database cannot be used to sign in.
"""

from __future__ import annotations

import logging
import re

import streamlit as st
import streamlit.components.v1 as components

from services import auth_service
from services.social_auth import SocialLoginError, complete_github_callback, google_identity

LOGGER = logging.getLogger("ai_book_studio.auth")

SESSION_COOKIE = "ab_session"
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
    st.session_state[USER_KEY] = auth_service.public_user(user)
    st.session_state[TOKEN_KEY] = auth_service.start_session(user["id"])
    st.session_state[COOKIE_MODE_KEY] = "persistent" if remember else "session"
    st.session_state.pop(ERROR_KEY, None)
    claim_browser_books(user["id"])


def claim_browser_books(user_id: str) -> None:
    """Books made in this browser before accounts existed become the account's books."""
    from components.identity import COOKIE_NAME, is_valid_owner
    from components.state import get_storage

    try:
        old = st.context.cookies.get(COOKIE_NAME)
    except Exception:  # noqa: BLE001
        return
    if is_valid_owner(old) and old != user_id:
        try:
            get_storage().transfer_owner(old, user_id)
        except OSError:
            LOGGER.warning("Could not move this browser's books to the account")


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
            sign_in(auth_service.social_sign_in(google["provider"], google["subject"], google["email"], google["name"]))
            return
        except auth_service.AuthError as exc:
            st.session_state[ERROR_KEY] = str(exc)
    token = _read_cookie()
    user = auth_service.user_for_session(token)
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
        sign_in(auth_service.social_sign_in(identity["provider"], identity["subject"], identity["email"], identity["name"]))
    except (SocialLoginError, auth_service.AuthError) as exc:
        st.session_state[ERROR_KEY] = str(exc)
    st.query_params.clear()
    st.rerun()


def sync_cookie() -> None:
    """Write or remove the login cookie in the browser. Renders nothing visible."""
    mode = st.session_state.get(COOKIE_MODE_KEY)
    token = st.session_state.get(TOKEN_KEY)
    if mode in ("persistent", "session") and isinstance(token, str) and _TOKEN.match(token):
        lifetime = f"max-age={auth_service.SESSION_SECONDS}; " if mode == "persistent" else ""
        _run_script(_COOKIE_SCRIPT % {"name": SESSION_COOKIE, "value": token, "lifetime": lifetime})
    elif mode == "clear":
        _run_script(_COOKIE_SCRIPT % {"name": SESSION_COOKIE, "value": "", "lifetime": "max-age=0; "})


def sign_out() -> None:
    """End the session on the server, forget everything in this tab and remove the cookie."""
    auth_service.end_session(st.session_state.get(TOKEN_KEY))
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
    from components.auth_page import render_auth_page

    sync_cookie()  # removes a stale cookie right after signing out
    render_auth_page()
    return False
