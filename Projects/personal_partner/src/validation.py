"""Input validation shared by authentication and the UI."""

from __future__ import annotations

import re
import unicodedata


USERNAME_RE = re.compile(r"^[a-z0-9_.]{3,30}$")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")
SPECIAL_RE = re.compile(r"[^A-Za-z0-9]")


def normalize_username(value: str) -> str:
    return value.strip().lower()


def normalize_email(value: str) -> str:
    return value.strip().casefold()


def validate_display_name(value: str) -> str | None:
    name = unicodedata.normalize("NFKC", value).strip()
    if not name:
        return "Enter a display name."
    if len(name) > 80:
        return "Display name must be 80 characters or fewer."
    if any(unicodedata.category(char).startswith("C") for char in name):
        return "Display name contains unsupported characters."
    return None


def validate_username(value: str) -> str | None:
    username = normalize_username(value)
    if not USERNAME_RE.fullmatch(username):
        return "Username must be 3–30 characters and use letters, numbers, periods, or underscores."
    return None


def validate_email(value: str) -> str | None:
    email = normalize_email(value)
    if len(email) > 254 or not EMAIL_RE.fullmatch(email):
        return "Enter a valid email address."
    return None


def validate_password(value: str) -> str | None:
    if len(value) < 10:
        return "Password must be at least 10 characters."
    if not re.search(r"[A-Z]", value):
        return "Password must include an uppercase letter."
    if not re.search(r"[a-z]", value):
        return "Password must include a lowercase letter."
    if not re.search(r"\d", value):
        return "Password must include a number."
    if not SPECIAL_RE.search(value):
        return "Password must include a special character."
    if len(value.encode("utf-8")) > 72:
        return "Password must be 72 bytes or fewer."
    return None


def validate_message(value: str) -> str | None:
    if not value.strip():
        return "Write a message before sending."
    if len(value) > 8_000:
        return "Messages must be 8,000 characters or fewer."
    return None


def safe_conversation_title(value: str, limit: int = 50) -> str:
    title = " ".join(value.replace("\n", " ").split())
    title = "".join(char for char in title if not unicodedata.category(char).startswith("C"))
    return title[:limit].rstrip() or "A new conversation"
