"""Account creation and authentication helpers."""

from __future__ import annotations

import bcrypt
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from . import storage
from .validation import (
    normalize_email,
    normalize_username,
    validate_display_name,
    validate_email,
    validate_password,
    validate_username,
)


LOGGER = logging.getLogger("kindspace.audit")


class AccountValidationError(ValueError):
    """Safe message suitable for display during account creation."""


class AccountLockedError(AccountValidationError):
    """Too many failed sign-ins; safe to show to the user."""


_DUMMY_PASSWORD_HASH = bcrypt.hashpw(b"not-a-real-password", bcrypt.gensalt(rounds=12))


def _username_from_email(email: str) -> str:
    """Internal unique handle; people sign in with their email address."""
    local = re.sub(r"[^a-z0-9_.]", "", email.split("@", 1)[0])[:20] or "user"
    return f"{local.ljust(3, '_')}_{uuid.uuid4().hex[:6]}"


def create_account(
    display_name: str,
    username: str,
    email: str,
    password: str,
    confirm_password: str,
    accepted_terms: bool,
) -> dict[str, Any]:
    display_name = display_name.strip()
    email = normalize_email(email)
    username = normalize_username(username) or _username_from_email(email)
    for error in (
        validate_display_name(display_name),
        validate_username(username),
        validate_email(email),
        validate_password(password),
    ):
        if error:
            raise AccountValidationError(error)
    if password != confirm_password:
        raise AccountValidationError("Passwords do not match.")
    if not accepted_terms:
        raise AccountValidationError("Please accept the privacy notice to continue.")

    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("ascii")
    return storage.create_user(
        {
            "user_id": uuid.uuid4().hex,
            "username": username,
            "display_name": display_name,
            "email": email,
            "password_hash": password_hash,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "preferences": {"tone": "Warm", "response_length": "Brief", "topics": []},
            "active": True,
        }
    )


def authenticate_user(identifier: str, password: str) -> dict[str, Any] | None:
    """Sign in with an email address (a legacy username is still accepted)."""
    identifier = identifier.strip()
    if "@" in identifier:
        record = storage.find_user_by_email(identifier)
        if record:
            record = storage.find_user_by_username(str(record["username"]))
    else:
        record = storage.find_user_by_username(normalize_username(identifier))
    if record:
        remaining = storage.account_lock_remaining(record)
        if remaining is not None:
            minutes = max(1, int(remaining.total_seconds() // 60) + 1)
            LOGGER.warning("audit event=login_blocked user_id=%s", record.get("user_id"))
            raise AccountLockedError(
                f"Too many failed attempts. Try again in about {minutes} minute(s) or reset your password."
            )
    stored_hash = _DUMMY_PASSWORD_HASH
    if record:
        try:
            stored_hash = record.get("password_hash", "").encode("ascii")
            # Invalid/corrupt hashes still follow the generic login failure path.
            if not stored_hash.startswith((b"$2a$", b"$2b$", b"$2y$")):
                stored_hash = _DUMMY_PASSWORD_HASH
        except (AttributeError, UnicodeError):
            stored_hash = _DUMMY_PASSWORD_HASH
    try:
        valid = bcrypt.checkpw(password.encode("utf-8")[:72], stored_hash)
    except (ValueError, TypeError):
        valid = False
    if not record or not record.get("active", False):
        LOGGER.info("audit event=login_failed reason=unknown_or_inactive")
        return None
    if not valid:
        storage.record_login_failure(str(record["user_id"]))
        LOGGER.info("audit event=login_failed user_id=%s", record.get("user_id"))
        return None
    storage.clear_login_failures(str(record["user_id"]))
    LOGGER.info("audit event=login_succeeded user_id=%s", record.get("user_id"))
    return {key: value for key, value in record.items() if key not in {"password_hash", "password_reset", "failed_logins", "locked_until"}}


def public_account(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_id": str(user["user_id"]),
        "username": str(user["username"]),
        "display_name": str(user["display_name"]),
        "email": str(user.get("email", "")),
        "preferences": dict(user.get("preferences") or {}),
    }


def email_has_account(email: str) -> bool:
    email = normalize_email(email)
    error = validate_email(email)
    if error:
        raise AccountValidationError(error)
    user = storage.find_user_by_email(email)
    return bool(user and user.get("active", False))


def reset_password_for_email(email: str, password: str, confirm_password: str) -> None:
    error = validate_password(password)
    if error:
        raise AccountValidationError(error)
    if password != confirm_password:
        raise AccountValidationError("Passwords do not match.")
    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("ascii")
    if not storage.set_password_by_email(normalize_email(email), password_hash):
        raise AccountValidationError("No account exists with that email.")
    LOGGER.info("audit event=password_reset_completed")


def authenticate_social_user(provider: str, subject: str, email: str, display_name: str) -> dict[str, Any]:
    """Create or link a local account from a provider-verified identity."""
    if not email or len(email) > 254 or not subject:
        raise AccountValidationError("The identity provider did not return a verified email address.")
    random_password = os.urandom(32)
    password_hash = bcrypt.hashpw(random_password, bcrypt.gensalt(rounds=12)).decode("ascii")
    user = storage.create_or_link_social_user(
        provider=provider,
        subject=subject,
        email=email,
        display_name=display_name or provider.title(),
        password_hash=password_hash,
    )
    return public_account(user)
