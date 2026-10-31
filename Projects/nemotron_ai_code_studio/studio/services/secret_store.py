"""Keeps the GitHub token across restarts without ever putting it in the repository, a log, a browser store or a source file.

Order of preference:
1. The operating system's credential manager, through the optional `keyring` package.
2. Windows only: a file in the user's profile encrypted with DPAPI (only this Windows user on this computer can decrypt it).
3. Nothing: the token then lives in memory for the running session only.

A hosted (shared) deployment never persists anything: the server is not the user's computer."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from ..config import is_hosted

SERVICE = "RK Studio"
ACCOUNT = "github-token"


def _keyring():
    try:
        import keyring
        from keyring.backends import fail
    except Exception:  # not installed, or a broken backend
        return None
    try:
        if isinstance(keyring.get_keyring(), fail.Keyring):
            return None
    except Exception:
        return None
    return keyring


def _dpapi_file() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(base) / "RKStudio" / "github-token.bin"


def _dpapi(data: bytes, protect: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.windll.crypt32  # type: ignore[attr-defined]
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    buffer = ctypes.create_string_buffer(data, len(data))
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    result = Blob()
    function = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    if not function(ctypes.byref(source), None, None, None, None, 0, ctypes.byref(result)):
        raise OSError("Windows could not protect or unprotect the stored credential.")
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(result.pbData, ctypes.c_void_p))


def backend() -> str:
    """"keyring", "dpapi", or "" when the token cannot be stored on this computer."""
    if is_hosted():
        return ""
    if _keyring() is not None:
        return "keyring"
    if sys.platform == "win32":
        return "dpapi"
    return ""


def save(token: str) -> str:
    """Stores `token` and returns the backend used ("" when it could not be stored; the session still works)."""
    kind = backend()
    try:
        if kind == "keyring":
            _keyring().set_password(SERVICE, ACCOUNT, token)
        elif kind == "dpapi":
            target = _dpapi_file()
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(_dpapi(token.encode("utf-8"), True))
        return kind
    except Exception:  # a locked or missing store must not break signing in
        return ""


def load() -> str:
    kind = backend()
    try:
        if kind == "keyring":
            return _keyring().get_password(SERVICE, ACCOUNT) or ""
        if kind == "dpapi":
            target = _dpapi_file()
            if target.is_file():
                return _dpapi(target.read_bytes(), False).decode("utf-8")
    except Exception:
        return ""
    return ""


def delete() -> None:
    kind = backend()
    try:
        if kind == "keyring":
            _keyring().delete_password(SERVICE, ACCOUNT)
        elif kind == "dpapi":
            _dpapi_file().unlink(missing_ok=True)
    except Exception:
        pass
