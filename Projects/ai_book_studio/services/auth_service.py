"""Accounts and login sessions: sign-up, password sign-in, social sign-in and the remember-me session token."""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import re
import secrets
import sqlite3
import time
from typing import Any

import bcrypt

from services import user_store

LOGGER = logging.getLogger("ai_book_studio.auth")

SESSION_DAYS = 30
SESSION_SECONDS = SESSION_DAYS * 24 * 3600
MAX_FAILED_LOGINS = 5
LOCK_SECONDS = 10 * 60
MIN_PASSWORD = 8
MAX_PASSWORD = 128

_EMAIL = re.compile(
    r"^[A-Za-z0-9_%+\-]+(\.[A-Za-z0-9_%+\-]+)*"  # name: no leading, trailing or double dots
    r"@([A-Za-z0-9]([A-Za-z0-9\-]*[A-Za-z0-9])?\.)+[A-Za-z]{2,}$"  # domain with a dot and a real ending, e.g. gmail.com
)


class AuthError(ValueError):
    """A message that is safe to show to the person signing in."""


def normalize_email(email: str) -> str:
    return str(email or "").strip().lower()


def validate_name(name: str) -> str:
    cleaned = " ".join(str(name or "").split())
    if len(cleaned) < 2:
        raise AuthError("Enter your name (at least 2 characters).")
    if len(cleaned) > 80:
        raise AuthError("That name is too long (80 characters at most).")
    return cleaned


def validate_email(email: str) -> str:
    cleaned = normalize_email(email)
    if len(cleaned) > 254 or not _EMAIL.match(cleaned):
        raise AuthError("Enter a valid email address.")
    return cleaned


def validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD:
        raise AuthError(f"Use at least {MIN_PASSWORD} characters for the password.")
    if len(password) > MAX_PASSWORD:
        raise AuthError(f"The password is too long ({MAX_PASSWORD} characters at most).")
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise AuthError("The password needs at least one letter and one number.")


def _prepare(password: str) -> bytes:
    """bcrypt only reads 72 bytes; hashing first lets long passphrases count in full."""
    return base64.b64encode(hashlib.sha256(password.encode("utf-8")).digest())


def _hash(password: str) -> str:
    return bcrypt.hashpw(_prepare(password), bcrypt.gensalt(rounds=12)).decode("ascii")


_DUMMY_HASH = _hash("not-a-real-password-1")  # compared against when the email is unknown, so timing does not reveal accounts


def public_user(user: dict[str, Any]) -> dict[str, str]:
    """The fields that are safe to keep in the browser session."""
    return {"id": str(user["id"]), "name": str(user["name"]), "email": str(user["email"])}


# ------------------------------------------------------------------ password accounts
def create_account(name: str, email: str, password: str, confirm: str) -> dict[str, str]:
    name, email = validate_name(name), validate_email(email)
    validate_password(password)
    if password != confirm:
        raise AuthError("The two passwords do not match.")
    try:
        user = user_store.create_user(email, name, _hash(password))
    except sqlite3.IntegrityError:
        raise AuthError("An account with this email already exists. Log in instead.") from None
    LOGGER.info("account created id=%s", user["id"])
    return public_user(user)


def authenticate(email: str, password: str) -> dict[str, str]:
    """Check an email and password. Every failure says the same thing, so accounts cannot be guessed."""
    generic = AuthError("That email and password do not match.")
    user = user_store.find_by_email(normalize_email(email))
    if user and float(user["locked_until"]) > time.time():
        minutes = int((float(user["locked_until"]) - time.time()) // 60) + 1
        raise AuthError(f"Too many wrong attempts. Try again in about {minutes} minute(s).")
    stored = (user or {}).get("password_hash") or ""
    try:
        valid = bcrypt.checkpw(_prepare(password or ""), (stored or _DUMMY_HASH).encode("ascii"))
    except (ValueError, TypeError):
        valid = False
    if not user or not stored or not valid:
        if user:
            user_store.record_failure(user["id"], MAX_FAILED_LOGINS, LOCK_SECONDS)
        if user and not stored:
            raise AuthError("This account uses Google or GitHub. Use that button to log in.")
        raise generic
    user_store.clear_failures(user["id"])
    return public_user(user)


# ------------------------------------------------------------------ forgot password
RESET_MINUTES = 15
RESET_RESEND_SECONDS = 60
RESET_MAX_TRIES = 5


def begin_password_reset(email: str) -> dict[str, object]:
    """Step 1: look the account up. When email is set up, a 6-digit code is sent and step 2 must present it."""
    from services import mailer

    email = validate_email(email)
    user = user_store.find_by_email(email)
    if user is None:
        raise AuthError("We could not find an account with that email.")
    if not user["password_hash"]:
        raise AuthError("This account uses Google or GitHub. Use that button to log in.")
    needs_code = mailer.is_configured()
    if needs_code:
        previous = user_store.get_reset(user["id"])
        if previous and time.time() - float(previous["created_at"]) < RESET_RESEND_SECONDS:
            raise AuthError("A code was just sent. Check your inbox, or wait a minute and try again.")
        code = f"{secrets.randbelow(10**6):06d}"
        user_store.save_reset(user["id"], _digest(code), RESET_MINUTES * 60)
        if not mailer.send_reset_code(user["email"], code, RESET_MINUTES):
            user_store.delete_reset(user["id"])
            raise AuthError("We could not send the email right now. Please try again in a moment.")
    return {"id": user["id"], "email": user["email"], "needs_code": needs_code}


def finish_password_reset(user_id: str, code: str, password: str, confirm: str, needs_code: bool) -> None:
    """Step 2: check the code (when one was sent), then store the new password and end every old session."""
    validate_password(password)
    if password != confirm:
        raise AuthError("The two passwords do not match.")
    if needs_code:
        reset = user_store.get_reset(user_id)
        bad = AuthError("That code is not right or has expired. Go back and ask for a new one.")
        if not reset or float(reset["expires_at"]) < time.time() or int(reset["attempts"]) >= RESET_MAX_TRIES:
            raise bad
        if not hmac.compare_digest(reset["code_hash"], _digest(str(code or "").strip())):
            user_store.bump_reset_attempts(user_id)
            raise bad
    user_store.set_password(user_id, _hash(password))
    LOGGER.info("password reset id=%s", user_id)


# ------------------------------------------------------------------ social accounts
def social_sign_in(provider: str, subject: str, email: str, name: str) -> dict[str, str]:
    """Find, link or create the account for a provider-verified identity (Google or GitHub)."""
    subject = str(subject or "").strip()
    email = normalize_email(email)
    if not subject or not _EMAIL.match(email):
        raise AuthError("The sign-in provider did not return a verified email address.")
    user = user_store.find_by_identity(provider, subject)
    if user is None:
        user = user_store.find_by_email(email)  # the provider has verified this email, so the same person can use it
        if user is None:
            try:
                user = user_store.create_user(email, " ".join((name or "").split())[:80] or email.split("@")[0])
            except sqlite3.IntegrityError:
                user = user_store.find_by_email(email)
        if user is None:
            raise AuthError("Could not create your account. Please try again.")
        user_store.link_identity(user["id"], provider, subject)
        LOGGER.info("social sign-in linked provider=%s id=%s", provider, user["id"])
    return public_user(user)


# ------------------------------------------------------------------ sessions (remember me)
def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def start_session(user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    user_store.add_session(_digest(token), user_id, SESSION_SECONDS)
    return token


def user_for_session(token: str | None) -> dict[str, str] | None:
    if not token or not isinstance(token, str) or not 20 <= len(token) <= 80:
        return None
    user = user_store.user_for_session(_digest(token))
    return public_user(user) if user else None


def end_session(token: str | None) -> None:
    if token and isinstance(token, str):
        user_store.delete_session(_digest(token))
