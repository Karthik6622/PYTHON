"""Optional mail helpers for verification-mail flows: send a mail over SMTP, wait for a mail over IMAP and pull codes or links out of it.

Host names, ports and credentials come from environment variables (see the ``mail`` section of config/api.json and .env.example).
Nothing is read or sent unless a test calls one of these functions.
"""

from __future__ import annotations

import email
import email.header
import imaplib
import json
import os
import re
import smtplib
import ssl
import time
from email.message import EmailMessage
from email.utils import parseaddr
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
LINK = re.compile(r"https?://[^\s<>\"')]+")


def _names(kind: str) -> dict[str, str]:
    path = ROOT / "config" / "api.json"
    config = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    defaults = {part: f"{kind.upper()}_{part.upper()}" for part in ("host", "port", "username", "password")}
    defaults["from_addr"] = "SMTP_FROM"
    return {**defaults, **((config.get("mail") or {}).get(kind) or {})}


def _env(name: str, required: bool = True) -> str:
    value = os.environ.get(name, "")
    if required and not value:
        raise AssertionError(f"Environment variable {name} is not set")
    return value


def send_mail(to: str, subject: str, body: str, sender: str = "") -> None:
    """Send a plain-text mail through the configured SMTP server."""
    names = _names("smtp")
    host, port = _env(names["host"]), int(_env(names["port"], False) or 587)
    username, password = _env(names["username"], False), _env(names["password"], False)
    message = EmailMessage()
    message["From"] = sender or _env(names["from_addr"], False) or username
    message["To"], message["Subject"] = to, subject
    message.set_content(body)
    factory = smtplib.SMTP_SSL if port == 465 else smtplib.SMTP
    with factory(host, port, timeout=30) as server:
        if port != 465:
            server.ehlo()
            if server.has_extn("starttls"):
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
        if username:
            server.login(username, password)
        server.send_message(message)


def _text_of(message: email.message.Message) -> str:
    parts: list[str] = []
    for part in message.walk() if message.is_multipart() else [message]:
        if part.get_content_type() in ("text/plain", "text/html"):
            payload = part.get_payload(decode=True)
            if payload:
                parts.append(payload.decode(part.get_content_charset() or "utf-8", errors="replace"))
    return "\n".join(parts)


def wait_for_mail(subject_contains: str = "", to: str = "", timeout: int = 90, poll: float = 3.0, folder: str = "INBOX", delete: bool = False) -> dict[str, Any]:
    """Poll the mailbox until a matching, unseen mail arrives. Returns ``{subject, from, to, body, links}``."""
    names = _names("imap")
    host, port = _env(names["host"]), int(_env(names["port"], False) or 993)
    username, password = _env(names["username"]), _env(names["password"])
    deadline = time.time() + timeout
    while True:
        box = imaplib.IMAP4_SSL(host, port, timeout=30) if port == 993 else imaplib.IMAP4(host, port, timeout=30)
        try:
            box.login(username, password)
            box.select(folder)
            _, data = box.search(None, "UNSEEN")
            for number in reversed((data[0] or b"").split()):
                _, fetched = box.fetch(number, "(RFC822)")
                message = email.message_from_bytes(fetched[0][1])
                subject = str(email.header.make_header(email.header.decode_header(message.get("Subject", ""))))
                recipients = " ".join([message.get("To", ""), message.get("Delivered-To", "")]).lower()
                if subject_contains.lower() in subject.lower() and to.lower() in recipients:
                    body = _text_of(message)
                    if delete:
                        box.store(number, "+FLAGS", "\\Deleted")
                        box.expunge()
                    return {"subject": subject, "from": parseaddr(message.get("From", ""))[1], "to": recipients.strip(), "body": body, "links": LINK.findall(body)}
        finally:
            try:
                box.logout()
            except (imaplib.IMAP4.error, OSError):
                pass
        if time.time() > deadline:
            raise AssertionError(f"No mail matching subject '{subject_contains}' arrived within {timeout}s")
        time.sleep(poll)


def extract_code(text: str, pattern: str = r"\b(\d{4,8})\b") -> str:
    """The first verification code in a mail body (default: a 4-8 digit number)."""
    match = re.search(pattern, text)
    if not match:
        raise AssertionError("No verification code was found in the mail")
    return match.group(1) if match.groups() else match.group(0)
