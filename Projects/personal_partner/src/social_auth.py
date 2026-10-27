"""Google OIDC and GitHub OAuth sign-up/sign-in helpers."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from urllib.parse import urlencode

import httpx
import streamlit as st


class SocialLoginError(RuntimeError):
    """Safe message for a failed social sign-in."""


def _mapping(value):
    return value if hasattr(value, "get") else {}


def _root_secrets():
    try:
        root = _mapping(st.secrets)
        root.get("auth")  # raises when no secrets file exists (e.g. a fresh local checkout)
        return root
    except Exception:
        return {}


def _secret(name: str, default: str = "") -> str:
    value = _root_secrets().get(name)
    return str(value if value not in (None, "") else os.environ.get(name, default)).strip()


def _provider_placeholder(value: str) -> bool:
    return not value or value.casefold().startswith("your-") or value.casefold().startswith("generate-")


def google_missing_settings() -> list[str]:
    """Names (never values) of the Google login settings that are absent or still placeholders."""
    root = _root_secrets()
    shared = _mapping(root.get("auth"))
    google = _mapping(shared.get("google"))
    required = {
        "[auth] redirect_uri": shared.get("redirect_uri"),
        "[auth] cookie_secret": shared.get("cookie_secret"),
        "[auth.google] client_id": google.get("client_id"),
        "[auth.google] client_secret": google.get("client_secret"),
        "[auth.google] server_metadata_url": google.get("server_metadata_url"),
    }
    return [name for name, value in required.items() if _provider_placeholder(str(value or ""))]


def google_is_configured() -> bool:
    return not google_missing_settings()


def github_settings() -> tuple[str, str, str]:
    root = _root_secrets()
    github = _mapping(root.get("github"))
    def configured(secret_name: str, environment_name: str, default: str = "") -> str:
        value = str(github.get(secret_name) or "").strip()
        return _secret(environment_name, default) if _provider_placeholder(value) else value

    client_id = configured("client_id", "GITHUB_CLIENT_ID")
    client_secret = configured("client_secret", "GITHUB_CLIENT_SECRET")
    redirect_uri = configured("redirect_uri", "GITHUB_REDIRECT_URI", "http://localhost:8501")
    return client_id, client_secret, redirect_uri


def github_is_configured() -> bool:
    client_id, client_secret, redirect_uri = github_settings()
    return all(not _provider_placeholder(value) for value in (client_id, client_secret, redirect_uri))


def github_authorization_url() -> str:
    client_id, client_secret, redirect_uri = github_settings()
    if any(_provider_placeholder(value) for value in (client_id, client_secret, redirect_uri)):
        raise SocialLoginError("Add GitHub OAuth client details to enable this option.")
    issued = str(int(time.time()))
    nonce = secrets.token_urlsafe(24)
    payload = f"{issued}.{nonce}"
    signature = hmac.new(client_secret.encode("utf-8"), payload.encode("ascii"), hashlib.sha256).hexdigest()
    state = f"{payload}.{signature}"
    params = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": "read:user user:email",
            "state": state,
        }
    )
    return f"https://github.com/login/oauth/authorize?{params}"


def _verify_github_state(state: str, client_secret: str) -> bool:
    try:
        issued, nonce, signature = state.split(".", 2)
        issued_at = int(issued)
    except (ValueError, AttributeError):
        return False
    now = int(time.time())
    if not nonce or issued_at > now + 30 or now - issued_at > 600:
        return False
    payload = f"{issued}.{nonce}"
    expected = hmac.new(client_secret.encode("utf-8"), payload.encode("ascii"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def complete_github_callback() -> dict[str, str] | None:
    """Exchange a returned GitHub code and return only its verified identity."""
    code = st.query_params.get("code")
    state = st.query_params.get("state")
    if not code and not state:
        return None
    client_id, client_secret, redirect_uri = github_settings()
    if any(_provider_placeholder(value) for value in (client_id, client_secret, redirect_uri)):
        raise SocialLoginError("GitHub sign-up is not configured yet.")
    if not code or not state or not _verify_github_state(str(state), client_secret):
        raise SocialLoginError("GitHub sign-in could not be verified. Please try again.")

    headers = {"Accept": "application/json", "User-Agent": "WithYou-Personal-Partner"}
    try:
        token_response = httpx.post(
            "https://github.com/login/oauth/access_token",
            data={"client_id": client_id, "client_secret": client_secret, "code": str(code), "redirect_uri": redirect_uri},
            headers=headers,
        )
        token_response.raise_for_status()
        token = token_response.json().get("access_token")
        if not isinstance(token, str) or not token:
            raise SocialLoginError("GitHub did not complete sign-in. Please try again.")

        api_headers = {**headers, "Authorization": f"Bearer {token}"}
        profile_response = httpx.get("https://api.github.com/user", headers=api_headers)
        profile_response.raise_for_status()
        profile = profile_response.json()
        subject = str(profile.get("id", ""))
        display_name = str(profile.get("name") or profile.get("login") or "GitHub user")[:80]

        emails_response = httpx.get("https://api.github.com/user/emails", headers=api_headers)
        emails_response.raise_for_status()
        email_record = next(
            (item for item in emails_response.json() if item.get("primary") and item.get("verified") and item.get("email")),
            None,
        )
        if not email_record or not subject:
            raise SocialLoginError("Verify an email address in GitHub before signing up.")
        return {"provider": "github", "subject": subject, "email": str(email_record["email"]), "display_name": display_name}
    except SocialLoginError:
        raise
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        raise SocialLoginError("GitHub sign-in could not be completed. Please try again.") from exc


def google_identity() -> dict[str, str] | None:
    """Read the verified OIDC claims Streamlit received from Google."""
    try:
        if not google_is_configured() or not bool(st.user.is_logged_in):
            return None
        subject = str(st.user.get("sub", ""))
        email = str(st.user.get("email", ""))
        verified = st.user.get("email_verified", False)
        display_name = str(st.user.get("name") or st.user.get("given_name") or "Google user")[:80]
    except Exception:
        return None
    if not subject or not email or verified is not True:
        raise SocialLoginError("A verified Google email is required to create your account.")
    return {"provider": "google", "subject": subject, "email": email, "display_name": display_name}
