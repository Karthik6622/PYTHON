"""Keeps each browser window's chat on disk, so a page refresh (or a server restart) does not wipe the conversation.

Two files per window id, in .studio_chats/: the transcript shown in the chat panel, and the plain text turns the agent is given as
memory for the next request (see ConversationStore). Only the window's own id (random, in the page address) names the file.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import asdict, fields
from pathlib import Path
from typing import Any

from .chat import ChangeSet, ChatMessage, TextBlock, ToolCall, next_id
from .config import PROJECT_ROOT

CHAT_DIR = Path(os.environ.get("STUDIO_CHAT_DIR") or PROJECT_ROOT / ".studio_chats")
MAX_MESSAGES = 60
MAX_FILES = 300
_SAFE_ID = re.compile(r"[A-Za-z0-9_-]{4,64}")
_TEXT_LIMIT = 40_000
_DIFF_LIMIT = 20_000


def safe_id(window: str) -> bool:
    return bool(_SAFE_ID.fullmatch(window or ""))


def _write(path: Path, data: Any) -> None:
    """Atomic write: a refresh during a save must never leave half a file."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, temp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False)
        os.replace(temp, path)
        _prune(path.parent)
    except OSError:
        pass


def _prune(folder: Path) -> None:
    try:
        files = sorted(folder.glob("*.json"), key=lambda item: item.stat().st_mtime)
        for old in files[: max(0, len(files) - MAX_FILES * 2)]:
            old.unlink(missing_ok=True)
    except OSError:
        pass


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# ------------------------------------------------------------------ agent memory (plain text turns)
def load_turns(window: str, folder: Path | None = None) -> list[dict[str, str]]:
    if not safe_id(window):
        return []
    data = _read((folder or CHAT_DIR) / f"{window}.turns.json")
    if not isinstance(data, list):
        return []
    return [
        {"role": item["role"], "content": item["content"]}
        for item in data
        if isinstance(item, dict) and item.get("role") in {"user", "assistant"} and isinstance(item.get("content"), str)
    ]


def save_turns(window: str, turns: list[dict[str, str]], folder: Path | None = None) -> None:
    if safe_id(window):
        _write((folder or CHAT_DIR) / f"{window}.turns.json", turns)


def delete(window: str, folder: Path | None = None) -> None:
    if not safe_id(window):
        return
    for suffix in ("turns", "chat"):
        try:
            ((folder or CHAT_DIR) / f"{window}.{suffix}.json").unlink(missing_ok=True)
        except OSError:
            pass


# ------------------------------------------------------------------ transcript
def message_to_dict(message: ChatMessage) -> dict[str, Any]:
    data = asdict(message)
    data["blocks"] = [
        {"kind": "tool", **asdict(block)} if isinstance(block, ToolCall) else {"kind": "text", "text": block.text[:_TEXT_LIMIT]}
        for block in message.blocks
    ]
    data["text"] = message.text[:_TEXT_LIMIT]
    data["reasoning"] = message.reasoning[-6000:]
    for block in data["blocks"]:
        if block["kind"] == "tool":
            block["output"] = str(block.get("output", ""))[-2500:]
    if message.changes is not None:
        data["changes"]["diffs"] = {path: str(diff)[:_DIFF_LIMIT] for path, diff in message.changes.diffs.items()}
    return data


def message_from_dict(data: dict[str, Any]) -> ChatMessage | None:
    try:
        known = {f.name for f in fields(ChatMessage)}
        values = {key: value for key, value in data.items() if key in known and key not in {"blocks", "changes", "id"}}
        message = ChatMessage(**values)
        message.id = next_id()  # ids only need to be unique inside this process: they become widget keys
        tool_fields = {f.name for f in fields(ToolCall)}
        for block in data.get("blocks") or []:
            if block.get("kind") == "tool":
                message.blocks.append(ToolCall(**{k: v for k, v in block.items() if k in tool_fields}))
            elif block.get("kind") == "text":
                message.blocks.append(TextBlock(str(block.get("text", ""))))
        raw = data.get("changes")
        if isinstance(raw, dict):
            change_fields = {f.name for f in fields(ChangeSet)}
            message.changes = ChangeSet(**{k: v for k, v in raw.items() if k in change_fields})
        message.streaming = False
        return message
    except (TypeError, ValueError, KeyError):
        return None


def save_chat(window: str, messages: list[ChatMessage], folder: Path | None = None) -> None:
    """Saves the finished part of the transcript (a reply that is still being written is rebuilt from the running agent instead)."""
    if not safe_id(window):
        return
    done = list(messages)
    while done and done[-1].streaming:  # the question and its unfinished answer both come back from the running agent
        done.pop()
        if done and done[-1].role == "user":
            done.pop()
    _write((folder or CHAT_DIR) / f"{window}.chat.json", [message_to_dict(m) for m in done[-MAX_MESSAGES:]])


def load_chat(window: str, folder: Path | None = None) -> list[ChatMessage]:
    if not safe_id(window):
        return []
    data = _read((folder or CHAT_DIR) / f"{window}.chat.json")
    if not isinstance(data, list):
        return []
    restored = [message_from_dict(item) for item in data if isinstance(item, dict)]
    return [m for m in restored if m is not None]
