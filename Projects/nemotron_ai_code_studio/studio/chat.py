"""Chat transcript model and the reducer that turns agent events into message state."""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any

_ids = itertools.count(1)


def next_id() -> str:
    return f"m{next(_ids)}"


@dataclass
class ToolCall:
    id: str
    name: str
    args: Any = None
    output: str = ""
    done: bool = False
    ok: bool = True
    summary: str = ""


@dataclass
class ChangeSet:
    change_id: str
    files: list[dict[str, Any]] = field(default_factory=list)
    diff: str = ""
    state: str = "pending"  # pending | accepted | rejected


@dataclass
class ChatMessage:
    role: str  # user | assistant
    text: str = ""
    mode: str = "ask"
    id: str = field(default_factory=next_id)
    reasoning: str = ""
    tools: list[ToolCall] = field(default_factory=list)
    context_files: list[str] = field(default_factory=list)
    inspected: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    validation: dict[str, Any] | None = None
    changes: ChangeSet | None = None
    error: str = ""
    streaming: bool = False
    status: str = ""


MAX_TOOL_OUTPUT = 8000


def apply_event(message: ChatMessage, event: dict[str, Any], approvals: dict[str, dict[str, Any]]) -> None:
    """Mutates `message` (and the pending `approvals` by id) for one event. Unknown events are ignored."""
    kind = event.get("type")
    if kind == "status":
        message.status = str(event.get("text", ""))
    elif kind == "context":
        message.context_files = [str(f if isinstance(f, str) else f.get("path", "")) for f in event.get("files") or []]
    elif kind == "token":
        message.text += str(event.get("text", ""))
    elif kind == "reasoning":
        message.reasoning += str(event.get("text", ""))
    elif kind == "tool_start":
        message.tools.append(ToolCall(id=str(event.get("id")), name=str(event.get("name")), args=event.get("args")))
        message.status = f"Running {event.get('name')}"
    elif kind == "tool_output":
        for tool in message.tools:
            if tool.id == str(event.get("id")):
                tool.output = (tool.output + str(event.get("text", "")))[-MAX_TOOL_OUTPUT:]
    elif kind == "tool_end":
        for tool in message.tools:
            if tool.id == str(event.get("id")):
                tool.done, tool.ok, tool.summary = True, bool(event.get("ok")), str(event.get("summary", ""))
                tool.output = tool.output or str(event.get("preview", ""))
    elif kind == "files":
        message.inspected = list(event.get("inspected") or [])
        message.modified = list(event.get("modified") or [])
    elif kind == "validation":
        message.validation = {"passed": event.get("passed"), "steps": event.get("steps") or []}
    elif kind == "changes":
        message.changes = ChangeSet(str(event.get("change_id")), list(event.get("files") or []), str(event.get("diff", "")))
    elif kind == "approval_request":
        approval = event.get("approval") or {}
        if approval.get("id"):
            approvals[str(approval["id"])] = approval
    elif kind == "approval_expired":
        approvals.pop(str(event.get("id")), None)
    elif kind == "error":
        message.error = str(event.get("message", "Error"))
    elif kind == "cancelled":
        message.streaming, message.status = False, "Stopped"
        approvals.clear()
        if event.get("modified"):
            message.modified = list(event["modified"])
    elif kind == "done":
        message.streaming, message.status = False, ""
        approvals.clear()
        if not message.error:  # on failure the error banner already shows the message
            message.text = message.text or str(event.get("message", ""))
        message.inspected = list(event.get("inspected") or message.inspected)
        message.modified = list(event.get("modified") or message.modified)
