"""Account creation and authentication helpers."""

from __future__ import annotations

import bcrypt
import os
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


class AccountValidationError(ValueError):
    """Safe message suitable for display during account creation."""


_DUMMY_PASSWORD_HASH = bcrypt.hashpw(b"not-a-real-password", bcrypt.gensalt(rounds=12))


def create_account(
    display_name: str,
    username: str,
    email: str,
    password: str,
    confirm_password: str,
    accepted_terms: bool,
) -> dict[str, Any]:
    display_name = display_name.strip()
    username = normalize_username(username)
    email = normalize_email(email)
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
            "preferences": {"tone": "Warm", "response_length": "Balanced", "topics": []},
            "active": True,
        }
    )


def authenticate_user(username: str, password: str) -> dict[str, Any] | None:
    record = storage.find_user_by_username(normalize_username(username))
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
    if not record or not record.get("active", False) or not valid:
        return None
    return {key: value for key, value in record.items() if key != "password_hash"}


def public_account(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_id": str(user["user_id"]),
        "username": str(user["username"]),
        "display_name": str(user["display_name"]),
        "preferences": dict(user.get("preferences") or {}),
    }


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
