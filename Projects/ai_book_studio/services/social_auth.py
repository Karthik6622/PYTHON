"""Google (OpenID Connect through Streamlit) and GitHub (OAuth) sign-in helpers.

Secrets go in ``.streamlit/secrets.toml``. Nothing here ever logs or displays a secret value.

    [auth]
    redirect_uri = "http://localhost:8501/oauth2callback"
    cookie_secret = "a-long-random-string"

    [auth.google]
    client_id = "..."
    client_secret = "..."
    server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"

    [github]
    client_id = "..."
    client_secret = "..."
    redirect_uri = "http://localhost:8501"
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import time
from urllib.parse import urlencode

import httpx
import streamlit as st

LOGGER = logging.getLogger("ai_book_studio.auth")

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_API = "https://api.github.com"
_STATE_MAX_AGE = 600
_HTTP_TIMEOUT = 15.0


class SocialLoginError(RuntimeError):
    """A message that is safe to show to the person signing in."""


def _mapping(value):
    return value if hasattr(value, "get") else {}


def _root():
    try:
        root = _mapping(st.secrets)
        root.get("auth")  # raises when there is no secrets file at all
        return root
    except Exception:  # noqa: BLE001 - a missing secrets file is normal on a fresh checkout
        return {}


def _placeholder(value: str) -> bool:
    text = str(value or "").strip().casefold()
    return not text or text.startswith(("your-", "your_", "generate-", "<", "changeme"))


# ------------------------------------------------------------------ Google
def google_missing_settings() -> list[str]:
    """Names (never values) of the Google settings that are absent or still placeholders."""
    shared = _mapping(_root().get("auth"))
    google = _mapping(shared.get("google"))
    required = {
        "[auth] redirect_uri": shared.get("redirect_uri"),
        "[auth] cookie_secret": shared.get("cookie_secret"),
        "[auth.google] client_id": google.get("client_id"),
        "[auth.google] client_secret": google.get("client_secret"),
        "[auth.google] server_metadata_url": google.get("server_metadata_url"),
    }
    return [name for name, value in required.items() if _placeholder(str(value or ""))]


def google_is_configured() -> bool:
    return not google_missing_settings()


def google_identity() -> dict[str, str] | None:
    """The verified identity Streamlit received from Google, or ``None`` when nobody is signed in with Google."""
    try:
        if not google_is_configured() or not bool(st.user.is_logged_in):
            return None
        subject = str(st.user.get("sub", ""))
        email = str(st.user.get("email", ""))
        verified = st.user.get("email_verified", False)
        name = str(st.user.get("name") or st.user.get("given_name") or "")[:80]
    except Exception:  # noqa: BLE001
        return None
    if not subject or not email or verified is not True:
        raise SocialLoginError("A verified Google email is required to sign in.")
    return {"provider": "google", "subject": subject, "email": email, "name": name}


# ------------------------------------------------------------------ GitHub
def github_settings() -> tuple[str, str, str]:
    github = _mapping(_root().get("github"))

    def pick(key: str, env: str, default: str = "") -> str:
        value = str(github.get(key) or "").strip()
        return value if not _placeholder(value) else str(os.environ.get(env, default)).strip()

    return (
        pick("client_id", "GITHUB_CLIENT_ID"),
        pick("client_secret", "GITHUB_CLIENT_SECRET"),
        pick("redirect_uri", "GITHUB_REDIRECT_URI", "http://localhost:8501"),
    )


def github_is_configured() -> bool:
    return all(not _placeholder(value) for value in github_settings())


def _sign(payload: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload.encode("ascii"), hashlib.sha256).hexdigest()


def github_authorization_url() -> str:
    client_id, client_secret, redirect_uri = github_settings()
    if not github_is_configured():
        raise SocialLoginError("GitHub sign-in is not set up yet.")
    payload = f"{int(time.time())}.{secrets.token_urlsafe(24)}"
    state = f"{payload}.{_sign(payload, client_secret)}"
    query = urlencode({"client_id": client_id, "redirect_uri": redirect_uri, "scope": "read:user user:email", "state": state})
    return f"{GITHUB_AUTHORIZE_URL}?{query}"


def _state_is_valid(state: str, client_secret: str) -> bool:
    try:
        issued, nonce, signature = state.split(".", 2)
        issued_at = int(issued)
    except (ValueError, AttributeError):
        return False
    now = int(time.time())
    if not nonce or issued_at > now + 30 or now - issued_at > _STATE_MAX_AGE:
        return False
    return hmac.compare_digest(_sign(f"{issued}.{nonce}", client_secret), signature)


def complete_github_callback() -> dict[str, str] | None:
    """When GitHub has sent the visitor back with a code, exchange it and return the verified identity."""
    code, state = st.query_params.get("code"), st.query_params.get("state")
    if not code and not state:
        return None
    if not github_is_configured():
        return None  # the parameters belong to something else (for example Streamlit's own Google callback)
    client_id, client_secret, redirect_uri = github_settings()
    if not code or not state or not _state_is_valid(str(state), client_secret):
        raise SocialLoginError("GitHub sign-in could not be verified. Please try again.")
    headers = {"Accept": "application/json", "User-Agent": "AI-Book-Studio"}
    try:
        reply = httpx.post(
            GITHUB_TOKEN_URL,
            data={"client_id": client_id, "client_secret": client_secret, "code": str(code), "redirect_uri": redirect_uri},
            headers=headers,
            timeout=_HTTP_TIMEOUT,
        )
        reply.raise_for_status()
        token = reply.json().get("access_token")
        if not isinstance(token, str) or not token:
            raise SocialLoginError("GitHub did not complete the sign-in. Please try again.")
        api = {**headers, "Authorization": f"Bearer {token}"}
        profile = httpx.get(f"{GITHUB_API}/user", headers=api, timeout=_HTTP_TIMEOUT)
        profile.raise_for_status()
        profile = profile.json()
        emails = httpx.get(f"{GITHUB_API}/user/emails", headers=api, timeout=_HTTP_TIMEOUT)
        emails.raise_for_status()
        primary = next((e for e in emails.json() if e.get("primary") and e.get("verified") and e.get("email")), None)
        subject = str(profile.get("id", ""))
        if not primary or not subject:
            raise SocialLoginError("Verify an email address in your GitHub account, then try again.")
        name = str(profile.get("name") or profile.get("login") or "")[:80]
        return {"provider": "github", "subject": subject, "email": str(primary["email"]), "name": name}
    except SocialLoginError:
        raise
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        LOGGER.warning("GitHub sign-in failed: %s", type(exc).__name__)
        raise SocialLoginError("GitHub sign-in could not be completed. Please try again.") from exc
