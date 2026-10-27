"""File-backed storage with per-file locks and atomic JSON replacement."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from filelock import FileLock

from .validation import normalize_email, normalize_username, safe_conversation_title


LOGGER = logging.getLogger("kindspace.storage")
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
USERS_FILE = DATA_DIR / "users.json"
CONVERSATIONS_DIR = DATA_DIR / "conversations"
_NOTICE_LOCK = Lock()
_STORAGE_NOTICES: list[str] = []
_UUID_RE = re.compile(r"^[0-9a-f]{32}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _notice(message: str) -> None:
    with _NOTICE_LOCK:
        _STORAGE_NOTICES.append(message)


def consume_storage_notices() -> list[str]:
    with _NOTICE_LOCK:
        notices = list(_STORAGE_NOTICES)
        _STORAGE_NOTICES.clear()
    return notices


def _conversation_path(user_id: str) -> Path:
    if not _UUID_RE.fullmatch(str(user_id)):
        raise ValueError("Invalid account identifier.")
    return CONVERSATIONS_DIR / f"{user_id}.json"


def _backup_malformed(path: Path) -> None:
    backup = path.with_name(f"{path.name}.corrupt-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}.bak")
    try:
        shutil.copy2(path, backup)
        LOGGER.error("Malformed JSON was backed up to %s", backup.name)
    except OSError:
        LOGGER.exception("Could not back up malformed JSON file %s", path.name)
        _notice("A local data file could not be read. Please check the application data folder.")


def _atomic_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as handle:
            temp_name = handle.name
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.chmod(temp_name, 0o600)
        except OSError:
            pass
        os.replace(temp_name, path)
    finally:
        if temp_name and os.path.exists(temp_name):
            try:
                os.unlink(temp_name)
            except OSError:
                LOGGER.warning("Could not remove temporary data file")


def _read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default.copy()
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
        if not isinstance(value, dict):
            raise ValueError("JSON root must be an object")
        return value
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        LOGGER.exception("Could not read JSON data file %s", path.name)
        _backup_malformed(path)
        _atomic_write(path, default)
        _notice("A local data file was damaged. A backup was saved and a clean file was created.")
        return default.copy()


def initialize_storage() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)
    with FileLock(f"{USERS_FILE}.lock"):
        if not USERS_FILE.exists():
            _atomic_write(USERS_FILE, {"users": []})
        else:
            data = _read_json(USERS_FILE, {"users": []})
            if not isinstance(data.get("users"), list):
                LOGGER.error("Users data file has an invalid users collection")
                _backup_malformed(USERS_FILE)
                _atomic_write(USERS_FILE, {"users": []})
                _notice("The local account file was damaged. A backup was saved and a clean file was created.")


def _read_users_locked() -> list[dict[str, Any]]:
    data = _read_json(USERS_FILE, {"users": []})
    users = data.get("users")
    if not isinstance(users, list) or any(not isinstance(user, dict) for user in users):
        LOGGER.error("Users data file has an invalid users collection")
        _backup_malformed(USERS_FILE)
        _atomic_write(USERS_FILE, {"users": []})
        _notice("The local account file was damaged. A backup was saved and a clean file was created.")
        return []
    return users


def create_user(user: dict[str, Any]) -> dict[str, Any]:
    """Insert a user atomically, rejecting duplicate normalized names/emails."""
    required = {"user_id", "username", "display_name", "email", "password_hash"}
    if not required.issubset(user):
        raise ValueError("Account details are incomplete.")
    with FileLock(f"{USERS_FILE}.lock"):
        users = _read_users_locked()
        username = normalize_username(str(user["username"]))
        email = normalize_email(str(user["email"]))
        if any(normalize_username(str(item.get("username", ""))) == username for item in users):
            raise ValueError("That username is already in use.")
        if any(normalize_email(str(item.get("email", ""))) == email for item in users):
            raise ValueError("An account already uses that email address.")
        record = {
            "user_id": str(user["user_id"]),
            "username": username,
            "display_name": str(user["display_name"]).strip(),
            "email": email,
            "password_hash": str(user["password_hash"]),
            "created_at": str(user.get("created_at") or _now()),
            "preferences": dict(user.get("preferences") or {}),
            "active": bool(user.get("active", True)),
        }
        users.append(record)
        _atomic_write(USERS_FILE, {"users": users})
    return {key: value for key, value in record.items() if key != "password_hash"}


def find_user_by_username(username: str) -> dict[str, Any] | None:
    normalized = normalize_username(username)
    with FileLock(f"{USERS_FILE}.lock"):
        for user in _read_users_locked():
            if normalize_username(str(user.get("username", ""))) == normalized:
                return dict(user)
    return None


def get_user_by_id(user_id: str) -> dict[str, Any] | None:
    with FileLock(f"{USERS_FILE}.lock"):
        for user in _read_users_locked():
            if str(user.get("user_id", "")) == str(user_id):
                return {key: value for key, value in user.items() if key != "password_hash"}
    return None


def update_user_preferences(user_id: str, preferences: dict[str, Any]) -> bool:
    allowed = {"tone", "response_length", "topics"}
    clean_preferences = {key: value for key, value in preferences.items() if key in allowed}
    with FileLock(f"{USERS_FILE}.lock"):
        users = _read_users_locked()
        for user in users:
            if str(user.get("user_id", "")) == str(user_id):
                user["preferences"] = clean_preferences
                _atomic_write(USERS_FILE, {"users": users})
                return True
    return False


def _read_conversations_locked(user_id: str) -> tuple[Path, list[dict[str, Any]]]:
    path = _conversation_path(user_id)
    data = _read_json(path, {"conversations": []})
    conversations = data.get("conversations")
    if not isinstance(conversations, list) or any(not isinstance(item, dict) for item in conversations):
        LOGGER.error("Conversation file has an invalid conversation collection")
        _backup_malformed(path)
        _atomic_write(path, {"conversations": []})
        _notice("A conversation file was damaged. A backup was saved and a clean file was created.")
        return path, []
    return path, conversations


def load_conversations(user_id: str) -> list[dict[str, Any]]:
    path = _conversation_path(user_id)
    with FileLock(f"{path}.lock"):
        _, conversations = _read_conversations_locked(user_id)
        return conversations


def create_conversation(user_id: str, title: str = "New conversation") -> dict[str, Any]:
    conversation = {
        "conversation_id": uuid.uuid4().hex,
        "title": safe_conversation_title(title),
        "created_at": _now(),
        "updated_at": _now(),
        "messages": [],
    }
    path = _conversation_path(user_id)
    with FileLock(f"{path}.lock"):
        _, conversations = _read_conversations_locked(user_id)
        conversations.insert(0, conversation)
        _atomic_write(path, {"conversations": conversations})
    return conversation


def rename_conversation(user_id: str, conversation_id: str, title: str) -> bool:
    path = _conversation_path(user_id)
    with FileLock(f"{path}.lock"):
        _, conversations = _read_conversations_locked(user_id)
        for conversation in conversations:
            if conversation.get("conversation_id") == conversation_id:
                conversation["title"] = safe_conversation_title(title)
                conversation["updated_at"] = _now()
                _atomic_write(path, {"conversations": conversations})
                return True
    return False


def delete_conversation(user_id: str, conversation_id: str) -> bool:
    path = _conversation_path(user_id)
    with FileLock(f"{path}.lock"):
        _, conversations = _read_conversations_locked(user_id)
        remaining = [item for item in conversations if item.get("conversation_id") != conversation_id]
        if len(remaining) == len(conversations):
            return False
        _atomic_write(path, {"conversations": remaining})
        return True


def append_message(user_id: str, conversation_id: str, message: dict[str, Any]) -> bool:
    if message.get("role") not in {"user", "assistant"}:
        raise ValueError("Unsupported message role.")
    message_id = str(message.get("message_id") or uuid.uuid4().hex)
    safe_message = {
        "message_id": message_id,
        "role": message["role"],
        "content": str(message.get("content", ""))[:8_000],
        "created_at": str(message.get("created_at") or _now()),
    }
    path = _conversation_path(user_id)
    with FileLock(f"{path}.lock"):
        _, conversations = _read_conversations_locked(user_id)
        for conversation in conversations:
            if conversation.get("conversation_id") == conversation_id:
                messages = conversation.setdefault("messages", [])
                if any(item.get("message_id") == message_id for item in messages if isinstance(item, dict)):
                    return False
                messages.append(safe_message)
                conversation["updated_at"] = _now()
                _atomic_write(path, {"conversations": conversations})
                return True
    return False


def export_conversation_as_markdown(conversation: dict[str, Any]) -> str:
    lines = [f"# {safe_conversation_title(str(conversation.get('title', 'Conversation')))}", ""]
    for message in conversation.get("messages", []):
        label = "You" if message.get("role") == "user" else "KindSpace"
        lines.extend((f"## {label}", "", str(message.get("content", "")), ""))
    return "\n".join(lines).rstrip() + "\n"


def delete_all_user_data(user_id: str) -> bool:
    path = _conversation_path(user_id)
    with FileLock(f"{USERS_FILE}.lock"):
        users = _read_users_locked()
        remaining = [user for user in users if str(user.get("user_id", "")) != str(user_id)]
        if len(remaining) == len(users):
            return False
        _atomic_write(USERS_FILE, {"users": remaining})
    with FileLock(f"{path}.lock"):
        if path.exists():
            path.unlink()
    return True
