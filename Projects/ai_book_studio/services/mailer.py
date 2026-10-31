"""Optional email sending (SMTP) for password-reset codes.

Settings go in ``.streamlit/secrets.toml`` (or environment variables ``SMTP_HOST`` ...). Nothing here logs a secret or a code.

    [smtp]
    host = "smtp.gmail.com"
    port = 587
    username = "you@example.com"
    password = "an-app-password"
    from_address = "AI Book Studio <you@example.com>"   # optional, defaults to username
"""

from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage

from config import APP_NAME
from services.social_auth import _mapping, _placeholder, _root

LOGGER = logging.getLogger("ai_book_studio.auth")


def _settings() -> dict[str, str]:
    smtp = _mapping(_root().get("smtp"))

    def pick(key: str, env: str) -> str:
        value = str(smtp.get(key) or "").strip()
        return value if not _placeholder(value) else str(os.environ.get(env, "")).strip()

    return {
        "host": pick("host", "SMTP_HOST"),
        "port": pick("port", "SMTP_PORT") or "587",
        "username": pick("username", "SMTP_USERNAME"),
        "password": pick("password", "SMTP_PASSWORD"),
        "from": pick("from_address", "SMTP_FROM"),
    }


def is_configured() -> bool:
    s = _settings()
    return bool(s["host"] and s["username"] and s["password"])


def send_reset_code(to_address: str, code: str, minutes: int) -> bool:
    """Email the code. Returns ``False`` (and logs only the error type) when it could not be sent."""
    s = _settings()
    message = EmailMessage()
    message["Subject"] = f"{APP_NAME}: your password reset code"
    message["From"] = s["from"] or s["username"]
    message["To"] = to_address
    message.set_content(
        f"Your {APP_NAME} password reset code is {code}.\n\nIt works for {minutes} minutes. "
        "If you did not ask for it, you can ignore this email; your password has not changed."
    )
    try:
        port = int(s["port"])
        context = ssl.create_default_context()
        if port == 465:
            with smtplib.SMTP_SSL(s["host"], port, context=context, timeout=20) as server:
                server.login(s["username"], s["password"])
                server.send_message(message)
        else:
            with smtplib.SMTP(s["host"], port, timeout=20) as server:
                server.starttls(context=context)
                server.login(s["username"], s["password"])
                server.send_message(message)
    except (OSError, smtplib.SMTPException, ValueError) as exc:
        LOGGER.warning("reset email failed: %s", type(exc).__name__)
        return False
    return True
