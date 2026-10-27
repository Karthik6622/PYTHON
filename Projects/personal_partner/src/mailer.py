"""Transactional email (password reset) over authenticated SMTP with TLS."""

from __future__ import annotations

import logging
import os
import re
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid, parseaddr

import httpx
import streamlit as st

_BREVO_URL = "https://api.brevo.com/v3"


LOGGER = logging.getLogger("kindspace.mailer")
_REQUIRED = ("SMTP_HOST", "SMTP_FROM", "APP_BASE_URL")
_EMAIL_IN_TEXT = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+")


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


def _api_key() -> str:
    return _setting("BREVO_API_KEY")


def missing_mail_settings() -> list[str]:
    required = ("SMTP_FROM", "APP_BASE_URL") if _api_key() else _REQUIRED
    return [name for name in required if not _setting(name) or _setting(name).casefold().startswith("your-")]


def mail_is_configured() -> bool:
    return not missing_mail_settings()


def app_base_url() -> str:
    return _setting("APP_BASE_URL").rstrip("/")


def _sender() -> str:
    """Build a valid From header even if SMTP_FROM is written loosely (e.g. missing angle brackets)."""
    raw = _setting("SMTP_FROM")
    found = _EMAIL_IN_TEXT.search(raw)
    name = raw[: found.start()].strip(" <\"'") if found else ""
    if not found:
        found = _EMAIL_IN_TEXT.search(_setting("SMTP_USERNAME"))
    if not found:
        return "KindSpace"
    return formataddr((name or "KindSpace", found.group(0)))


def _connect(host: str, port: int, username: str, password: str) -> smtplib.SMTP:
    context = ssl.create_default_context()
    client: smtplib.SMTP = (
        smtplib.SMTP_SSL(host, port, timeout=20, context=context) if port == 465 else smtplib.SMTP(host, port, timeout=20)
    )
    try:
        client.ehlo()
        if port != 465:
            client.starttls(context=context)
            client.ehlo()
        if username:
            client.login(username, password)
    except Exception:
        client.close()
        raise
    return client


def _open_connection() -> smtplib.SMTP:
    host = _setting("SMTP_HOST")
    port = int(_setting("SMTP_PORT", "587") or 587)
    username = _setting("SMTP_USERNAME")
    # Google shows app passwords in groups separated by spaces; they are not part of the password.
    password = _setting("SMTP_PASSWORD").replace(" ", "")
    # Some hosts block STARTTLS on 587; fall back to implicit TLS on 465 before giving up.
    ports = [port] + ([465] if port == 587 else [])
    errors: list[str] = []
    last_error: Exception | None = None
    for candidate in ports:
        try:
            return _connect(host, candidate, username, password)
        except smtplib.SMTPAuthenticationError:
            raise
        except (OSError, smtplib.SMTPException) as exc:
            LOGGER.warning("SMTP connection to %s:%s failed: %s: %s", host, candidate, type(exc).__name__, exc)
            errors.append(f"port {candidate} {type(exc).__name__}")
            last_error = exc
    assert last_error is not None
    raise smtplib.SMTPConnectError(0, "; ".join(errors)) from last_error


@st.cache_data(ttl=60, show_spinner=False)
def email_service_problem() -> str | None:
    """Check the SMTP login without sending anything. Returns a safe, account-independent reason or None."""
    if not mail_is_configured():
        return "Email settings are missing: " + ", ".join(missing_mail_settings()) + "."
    if _api_key():
        try:
            response = httpx.get(f"{_BREVO_URL}/account", headers={"api-key": _api_key()}, timeout=15)
        except httpx.HTTPError as exc:
            LOGGER.exception("Could not reach the Brevo API")
            return f"Could not reach the email service ({type(exc).__name__})."
        if response.status_code in (401, 403):
            return "The email service rejected BREVO_API_KEY. Create a new API key in Brevo (SMTP & API > API keys)."
        return None
    try:
        with _open_connection():
            return None
    except smtplib.SMTPAuthenticationError:
        LOGGER.error("SMTP login was rejected. Gmail requires a 16-character App Password, not the account password.")
        return "The mail server rejected the SMTP username/password. Gmail needs an App Password (Google Account > Security > 2-Step Verification > App passwords)."
    except (OSError, smtplib.SMTPException, ValueError) as exc:
        LOGGER.exception("Could not connect to the SMTP server")
        detail = f"{type(exc).__name__}: {str(exc)[:160]}"
        return (
            f"Could not connect to the mail server ({detail}). Check SMTP_HOST and SMTP_PORT. "
            "If this app is hosted on Streamlit Cloud, outbound SMTP may be blocked; set BREVO_API_KEY to send over HTTPS instead."
        )


def send_password_reset_email(to_address: str, display_name: str, token: str, valid_minutes: int) -> bool:
    """Send the reset link. Returns False (and logs) instead of raising so callers can stay generic."""
    if not mail_is_configured():
        LOGGER.warning("Password reset requested but SMTP is not configured")
        return False
    link = f"{app_base_url()}/?reset_token={token}"
    if _api_key():
        sender_name, sender_email = parseaddr(_sender())
        body = (
            f"Hi {display_name},\n\n"
            f"Use the link below to choose a new KindSpace password. It works once and expires in {valid_minutes} minutes.\n\n"
            f"{link}\n\n"
            "If you didn't ask for this, you can ignore this email; your password will not change.\n"
        )
        try:
            response = httpx.post(
                f"{_BREVO_URL}/smtp/email",
                headers={"api-key": _api_key(), "accept": "application/json"},
                json={
                    "sender": {"name": sender_name or "KindSpace", "email": sender_email},
                    "to": [{"email": to_address}],
                    "subject": "Reset your KindSpace password",
                    "textContent": body,
                },
                timeout=20,
            )
            if response.status_code >= 300:
                LOGGER.error("Brevo rejected the email: %s %s", response.status_code, response.text[:300])
                return False
            return True
        except httpx.HTTPError:
            LOGGER.exception("Could not send password reset email via Brevo")
            return False
    message = EmailMessage()
    message["Subject"] = "Reset your KindSpace password"
    message["From"] = _sender()
    message["To"] = to_address
    message["Date"] = formatdate(localtime=False)
    message["Message-ID"] = make_msgid(domain="kindspace.local")
    message.set_content(
        f"Hi {display_name},\n\n"
        f"Use the link below to choose a new KindSpace password. It works once and expires in {valid_minutes} minutes.\n\n"
        f"{link}\n\n"
        "If you didn't ask for this, you can ignore this email; your password will not change.\n"
    )
    try:
        with _open_connection() as client:
            client.send_message(message)
        return True
    except (OSError, smtplib.SMTPException, ValueError):
        LOGGER.exception("Could not send password reset email")
        return False
