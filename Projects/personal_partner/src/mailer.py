"""Transactional email (password reset) over authenticated SMTP with TLS."""

from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage

import streamlit as st


LOGGER = logging.getLogger("kindspace.mailer")
_REQUIRED = ("SMTP_HOST", "SMTP_FROM", "APP_BASE_URL")


def _secret_value(name: str) -> str:
    """Read a secret from the top level, then from any one-level table.

    In TOML, keys written below a `[table]` header belong to that table, so SMTP
    settings pasted under `[github]` would otherwise be invisible.
    """
    try:
        root = st.secrets
        value = root.get(name)
        if value not in (None, ""):
            return str(value)
        for key in list(root.keys()):
            section = root[key]
            if hasattr(section, "get") and not isinstance(section, str):
                value = section.get(name)
                if value not in (None, ""):
                    return str(value)
    except Exception:
        pass
    return ""


def _setting(name: str, default: str = "") -> str:
    return (_secret_value(name) or os.environ.get(name, default) or default).strip()


def missing_mail_settings() -> list[str]:
    return [name for name in _REQUIRED if not _setting(name) or _setting(name).casefold().startswith("your-")]


def mail_is_configured() -> bool:
    return not missing_mail_settings()


def app_base_url() -> str:
    return _setting("APP_BASE_URL").rstrip("/")


def send_password_reset_email(to_address: str, display_name: str, token: str, valid_minutes: int) -> bool:
    """Send the reset link. Returns False (and logs) instead of raising so callers can stay generic."""
    if not mail_is_configured():
        LOGGER.warning("Password reset requested but SMTP is not configured")
        return False
    link = f"{app_base_url()}/?reset_token={token}"
    message = EmailMessage()
    message["Subject"] = "Reset your KindSpace password"
    message["From"] = _setting("SMTP_FROM")
    message["To"] = to_address
    message.set_content(
        f"Hi {display_name},\n\n"
        f"Use the link below to choose a new KindSpace password. It works once and expires in {valid_minutes} minutes.\n\n"
        f"{link}\n\n"
        "If you didn't ask for this, you can ignore this email; your password will not change.\n"
    )
    host = _setting("SMTP_HOST")
    port = int(_setting("SMTP_PORT", "587") or 587)
    username = _setting("SMTP_USERNAME")
    password = _setting("SMTP_PASSWORD")
    context = ssl.create_default_context()
    try:
        if port == 465:
            client: smtplib.SMTP = smtplib.SMTP_SSL(host, port, timeout=15, context=context)
        else:
            client = smtplib.SMTP(host, port, timeout=15)
        with client:
            if port != 465:
                client.starttls(context=context)
            if username:
                client.login(username, password)
            client.send_message(message)
        return True
    except (OSError, smtplib.SMTPException, ValueError):
        LOGGER.exception("Could not send password reset email")
        return False
