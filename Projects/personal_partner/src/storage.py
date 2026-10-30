"""File-backed storage with per-file locks and atomic JSON replacement."""

from __future__ import annotations

import hmac
import json
import logging
import os
import re
import shutil
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
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
_IMAGE_FILE_RE = re.compile(r"^[0-9a-f]{32}\.png$")
MAX_ATTACHMENTS = 5
MAX_ATTACHMENT_TEXT = 12_000
MAX_FAILED_LOGINS = 5
LOCKOUT_MINUTES = 15
_SENSITIVE_FIELDS = {"password_hash", "password_reset", "failed_logins", "locked_until"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_time(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in user.items() if key not in _SENSITIVE_FIELDS}


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
    return _public_user(record)


def create_or_link_social_user(
    provider: str,
    subject: str,
    email: str,
    display_name: str,
    password_hash: str,
) -> dict[str, Any]:
    """Create or link a social identity after its provider verified the email."""
    if provider not in {"google", "github"} or not subject or len(subject) > 255:
        raise ValueError("The social account could not be verified.")
    email = normalize_email(email)
    identity = {"provider": provider, "subject": subject}
    with FileLock(f"{USERS_FILE}.lock"):
        users = _read_users_locked()
        for user in users:
            identities = user.get("auth_identities", [])
            if isinstance(identities, list) and identity in identities:
                if not user.get("active", False):
                    raise ValueError("This account is inactive. Contact the app owner.")
                return _public_user(user)

        for user in users:
            if normalize_email(str(user.get("email", ""))) == email:
                if not user.get("active", False):
                    raise ValueError("This account is inactive. Contact the app owner.")
                identities = user.setdefault("auth_identities", [])
                if not isinstance(identities, list):
                    identities = []
                    user["auth_identities"] = identities
                identities.append(identity)
                if not user.get("display_name"):
                    user["display_name"] = display_name[:80]
                _atomic_write(USERS_FILE, {"users": users})
                return _public_user(user)

        base_username = f"{provider}_{uuid.uuid5(uuid.NAMESPACE_URL, provider + ':' + subject).hex[:16]}"
        username = base_username
        suffix = 1
        usernames = {normalize_username(str(user.get("username", ""))) for user in users}
        while username in usernames:
            suffix += 1
            username = f"{base_username[:26]}{suffix}"
        user = {
            "user_id": uuid.uuid4().hex,
            "username": username,
            "display_name": str(display_name).strip()[:80] or username,
            "email": email,
            "password_hash": password_hash,
            "created_at": _now(),
            "preferences": {"tone": "Warm", "response_length": "Balanced", "topics": []},
            "active": True,
            "auth_identities": [identity],
        }
        users.append(user)
        _atomic_write(USERS_FILE, {"users": users})
        return _public_user(user)


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
                return _public_user(user)
    return None


def find_user_by_email(email: str) -> dict[str, Any] | None:
    normalized = normalize_email(email)
    with FileLock(f"{USERS_FILE}.lock"):
        for user in _read_users_locked():
            if normalize_email(str(user.get("email", ""))) == normalized:
                return _public_user(user)
    return None


def account_lock_remaining(user: dict[str, Any]) -> timedelta | None:
    """Return the time left on a lockout, or None when the account is not locked."""
    locked_until = _parse_time(user.get("locked_until"))
    if locked_until is None:
        return None
    remaining = locked_until - datetime.now(timezone.utc)
    return remaining if remaining > timedelta(0) else None


def record_login_failure(user_id: str) -> None:
    """Count a failed password attempt and lock the account after repeated failures."""
    with FileLock(f"{USERS_FILE}.lock"):
        users = _read_users_locked()
        for user in users:
            if str(user.get("user_id", "")) == str(user_id):
                failures = int(user.get("failed_logins") or 0) + 1
                user["failed_logins"] = failures
                if failures >= MAX_FAILED_LOGINS:
                    user["locked_until"] = (datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_MINUTES)).isoformat(timespec="seconds")
                    user["failed_logins"] = 0
                    LOGGER.warning("audit event=account_locked user_id=%s", user_id)
                _atomic_write(USERS_FILE, {"users": users})
                return


def clear_login_failures(user_id: str) -> None:
    with FileLock(f"{USERS_FILE}.lock"):
        users = _read_users_locked()
        for user in users:
            if str(user.get("user_id", "")) == str(user_id):
                if user.get("failed_logins") or user.get("locked_until"):
                    user.pop("failed_logins", None)
                    user.pop("locked_until", None)
                    _atomic_write(USERS_FILE, {"users": users})
                return


def set_password_by_email(email: str, new_password_hash: str) -> bool:
    """Replace the password of the active account with this email and clear any lockout."""
    normalized = normalize_email(email)
    with FileLock(f"{USERS_FILE}.lock"):
        users = _read_users_locked()
        for user in users:
            if user.get("active", False) and normalize_email(str(user.get("email", ""))) == normalized:
                user["password_hash"] = new_password_hash
                user.pop("failed_logins", None)
                user.pop("locked_until", None)
                user["password_changed_at"] = _now()
                _atomic_write(USERS_FILE, {"users": users})
                return True
    return False


def update_user_preferences(user_id: str, preferences: dict[str, Any]) -> bool:
    allowed = {"tone", "response_length", "topics", "city", "mode", "partner"}
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
    if message.get("mode") == "Romantic":
        safe_message["mode"] = "Romantic"
    attachments = message.get("attachments")
    if isinstance(attachments, list):
        safe_attachments = [
            {
                "name": str(item.get("name", "file"))[:80],
                "kind": "image" if item.get("kind") == "image" else "document",
                "text": str(item.get("text", ""))[:MAX_ATTACHMENT_TEXT],
            }
            for item in attachments[:MAX_ATTACHMENTS]
            if isinstance(item, dict)
        ]
        if safe_attachments:
            safe_message["attachments"] = safe_attachments
    image = message.get("image")
    if isinstance(image, str) and _IMAGE_FILE_RE.fullmatch(image):
        safe_message["image"] = image
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


def save_generated_image(user_id: str, png: bytes) -> str:
    """Save a generated picture under the account's folder and return its file name."""
    if not _UUID_RE.fullmatch(str(user_id)):
        raise ValueError("Invalid account identifier.")
    folder = DATA_DIR / "generated" / user_id
    folder.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.png"
    (folder / filename).write_bytes(png)
    return filename


def generated_image_bytes(user_id: str, filename: str) -> bytes | None:
    """The saved picture, or None when the name is not valid or the file is gone."""
    if not _UUID_RE.fullmatch(str(user_id)) or not _IMAGE_FILE_RE.fullmatch(str(filename)):
        return None
    path = DATA_DIR / "generated" / user_id / filename
    try:
        return path.read_bytes()
    except OSError:
        return None


def export_conversation_as_markdown(conversation: dict[str, Any]) -> str:
    lines = [f"# {safe_conversation_title(str(conversation.get('title', 'Conversation')))}", ""]
    for message in conversation.get("messages", []):
        label = "You" if message.get("role") == "user" else "WithYou"
        lines.extend((f"## {label}", "", str(message.get("content", "")), ""))
        attached = message.get("attachments")
        for item in attached if isinstance(attached, list) else []:
            if isinstance(item, dict):
                lines.extend((f"_Attached: {item.get('name', 'file')}_", ""))
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
    shutil.rmtree(DATA_DIR / "generated" / str(user_id), ignore_errors=True)
    return True
