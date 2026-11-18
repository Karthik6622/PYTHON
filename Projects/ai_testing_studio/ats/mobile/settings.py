"""Mobile settings read from the environment (or .streamlit/secrets.toml). None of them is shown to testers as an Appium setting."""

from __future__ import annotations

from ats.config import lookup_secret


def _int(name: str, default: int, low: int, high: int) -> int:
    try:
        value = int(lookup_secret(name) or default)
    except ValueError:
        value = default
    return min(max(value, low), high)


def max_apk_bytes() -> int:
    """Largest APK accepted for upload or as a local path (``MOBILE_MAX_APK_MB``, default 300 MB)."""
    return _int("MOBILE_MAX_APK_MB", 300, 1, 2048) * 1024 * 1024


def max_screens() -> int:
    """How many screens app analysis may capture (``MOBILE_MAX_SCREENS``, default 6)."""
    return _int("MOBILE_MAX_SCREENS", 6, 1, 20)


def appium_start_timeout() -> int:
    return _int("MOBILE_APPIUM_START_SECONDS", 90, 10, 600)


def command_timeout() -> float:
    return float(_int("MOBILE_COMMAND_TIMEOUT_SECONDS", 25, 5, 300))
