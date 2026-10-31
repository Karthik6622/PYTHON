"""A private, anonymous id per browser, so one visitor's books, jobs and files stay separate from everyone else's.

The id is a random token kept in a cookie. It is read from ``st.context.cookies`` when the session connects; a browser
that has none gets a new token, which a tiny hidden script then stores as a cookie for next time.
"""

from __future__ import annotations

import re
import secrets
import threading

import streamlit as st
import streamlit.components.v1 as components

COOKIE_NAME = "ab_owner"
_TOKEN = re.compile(r"^[A-Za-z0-9_\-]{20,64}$")
_SESSION_KEY = "owner_id"
_NEEDS_COOKIE_KEY = "owner_needs_cookie"

_SET_COOKIE = """<script>
(function () {
  try {
    var P = window.parent, secure = P.location.protocol === 'https:' ? '; Secure' : '';
    P.document.cookie = '%(name)s=%(token)s; path=/; max-age=31536000; SameSite=Lax' + secure;
  } catch (e) {}
})();
</script>"""

_adopt_lock = threading.Lock()
_adopted = False


def is_valid_owner(token: str | None) -> bool:
    return isinstance(token, str) and bool(_TOKEN.match(token))


def _cookie_value() -> str | None:
    try:
        return st.context.cookies.get(COOKIE_NAME)
    except Exception:  # noqa: BLE001 - cookies are unavailable outside a real browser session (for example in tests)
        return None


def owner_id() -> str:
    """The id of this browser. Stable for the whole session; created on first use."""
    token = st.session_state.get(_SESSION_KEY)
    if is_valid_owner(token):
        return token
    cookie = _cookie_value()
    if is_valid_owner(cookie):
        token = cookie
        st.session_state[_NEEDS_COOKIE_KEY] = False
    else:
        token = secrets.token_urlsafe(24)
        st.session_state[_NEEDS_COOKIE_KEY] = True
    st.session_state[_SESSION_KEY] = token
    return token


def remember_browser() -> None:
    """Store the id in the browser (only needed on its first visit). Renders nothing visible."""
    owner_id()
    if not st.session_state.get(_NEEDS_COOKIE_KEY):
        return
    html = _SET_COOKIE % {"name": COOKIE_NAME, "token": st.session_state[_SESSION_KEY]}  # the token is validated above
    if hasattr(st, "iframe"):
        st.iframe(html, height=1)
    else:
        components.html(html, height=0)


def adopt_legacy_books(storage) -> None:
    """Once per server start: books made before owners existed go to the first browser that connects."""
    global _adopted
    with _adopt_lock:
        if _adopted:
            return
        _adopted = True
    try:
        storage.adopt_unowned(owner_id())
    except OSError:
        pass
