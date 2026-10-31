"""Chat transcript model and the reducer that turns agent events into message state."""

from __future__ import annotations

import itertools
import time
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
    started: float = field(default_factory=time.time)
    ended: float = 0.0


@dataclass
class TextBlock:
    """A stretch of the model's own words, kept in order between tool calls."""
    text: str = ""


@dataclass
class ChangeSet:
    change_id: str
    files: list[dict[str, Any]] = field(default_factory=list)
    diffs: dict[str, str] = field(default_factory=dict)  # path -> unified diff
    state: str = "pending"  # pending | accepted | rejected | mixed
    kept: list[str] = field(default_factory=list)
    reverted: list[str] = field(default_factory=list)

    @property
    def diff(self) -> str:
        return "".join(self.diffs.values())


@dataclass
class ChatMessage:
    role: str  # user | assistant
    text: str = ""
    files: list[str] = field(default_factory=list)  # names of the files the user attached to this message
    mode: str = "ask"
    model: str = ""
    id: str = field(default_factory=next_id)
    reasoning: str = ""
    blocks: list[ToolCall | TextBlock] = field(default_factory=list)
    context_files: list[str] = field(default_factory=list)
    inspected: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    validation: dict[str, Any] | None = None
    changes: ChangeSet | None = None
    error: str = ""
    streaming: bool = False
    status: str = ""
    step: int = 0
    max_steps: int = 0
    started: float = field(default_factory=time.time)
    finished: float = 0.0
    last_event: float = field(default_factory=time.time)  # when the agent last reported anything (for the "no activity" hint)
    incomplete: bool = False  # the run ended before the task was finished (stopped, step limit, empty model reply)

    @property
    def tools(self) -> list[ToolCall]:
        return [b for b in self.blocks if isinstance(b, ToolCall)]


MAX_TOOL_OUTPUT = 8000


def add_notice(message: ChatMessage, text: str) -> None:
    """Appends an explanation from the studio itself (why the run ended) as its own paragraph of the reply."""
    text = text.strip()
    if not text:
        return
    message.blocks.append(TextBlock(text))
    message.text = (message.text + "\n\n" + text) if message.text else text


def apply_event(message: ChatMessage, event: dict[str, Any], approvals: dict[str, dict[str, Any]]) -> None:
    """Mutates `message` (and the pending `approvals` by id) for one event. Unknown events are ignored."""
    kind = event.get("type")
    message.last_event = time.time()
    if kind == "status":
        message.status = str(event.get("text", ""))
    elif kind == "context":
        message.context_files = [str(f if isinstance(f, str) else f.get("path", "")) for f in event.get("files") or []]
    elif kind == "token":
        text = str(event.get("text", ""))
        message.status = "Writing the reply"
        message.text += text
        if message.blocks and isinstance(message.blocks[-1], TextBlock):
            message.blocks[-1].text += text
        else:
            message.blocks.append(TextBlock(text))
    elif kind == "reasoning":
        message.reasoning += str(event.get("text", ""))
    elif kind == "retract":
        # the model's answer broke off and is being asked again: take back what that attempt had already written
        remaining = int(event.get("text", 0) or 0)
        message.text = message.text[: max(0, len(message.text) - remaining)]
        while remaining > 0 and message.blocks and isinstance(message.blocks[-1], TextBlock):
            block = message.blocks[-1]
            cut = min(remaining, len(block.text))
            block.text = block.text[: len(block.text) - cut]
            remaining -= cut
            if not block.text:
                message.blocks.pop()
        message.reasoning = message.reasoning[: max(0, len(message.reasoning) - int(event.get("reasoning", 0) or 0))]
    elif kind == "model":
        message.model = str(event.get("label", message.model))
    elif kind == "step":
        message.step, message.max_steps = int(event.get("n", 0)), int(event.get("max", 0))
    elif kind == "tool_start":
        message.blocks.append(ToolCall(id=str(event.get("id")), name=str(event.get("name")), args=event.get("args")))
        message.status = f"Running {event.get('name')}"
    elif kind == "tool_output":
        for tool in message.tools:
            if tool.id == str(event.get("id")):
                tool.output = (tool.output + str(event.get("text", "")))[-MAX_TOOL_OUTPUT:]
    elif kind == "tool_end":
        for tool in message.tools:
            if tool.id == str(event.get("id")):
                tool.done, tool.ok, tool.summary, tool.ended = True, bool(event.get("ok")), str(event.get("summary", "")), time.time()
                tool.output = tool.output or str(event.get("preview", ""))
    elif kind == "files":
        message.inspected = list(event.get("inspected") or [])
        message.modified = list(event.get("modified") or [])
    elif kind == "validation":
        message.validation = {"passed": event.get("passed"), "steps": event.get("steps") or []}
    elif kind == "changes":
        previous = message.changes
        current = ChangeSet(str(event.get("change_id")), list(event.get("files") or []), dict(event.get("diffs") or {}))
        if previous is not None and previous.change_id == current.change_id:
            current.kept, current.reverted = previous.kept, previous.reverted
        message.changes = current
    elif kind == "approval_request":
        approval = event.get("approval") or {}
        if approval.get("id"):
            approvals[str(approval["id"])] = approval
    elif kind == "approval_expired":
        approvals.pop(str(event.get("id")), None)
    elif kind == "error":
        message.error = str(event.get("message", "Error"))
        message.incomplete = True
    elif kind == "notice":
        add_notice(message, str(event.get("text", "")))
        message.incomplete = message.incomplete or bool(event.get("incomplete"))
    elif kind == "cancelled":
        message.streaming, message.status = False, "Stopped"
        approvals.clear()
        if event.get("modified"):
            message.modified = list(event["modified"])
        message.incomplete = True
        changed = len(message.modified)
        add_notice(message, "Stopped. The agent was stopped before it finished" + (f"; {changed} file(s) were already changed, review them below." if changed else "."))
    elif kind == "done":
        message.streaming, message.status = False, ""
        message.finished = time.time()
        approvals.clear()
        if not message.error:  # on failure the error banner already shows the message
            if not message.text:
                message.text = str(event.get("message", ""))
                if message.text:
                    message.blocks.append(TextBlock(message.text))
        message.inspected = list(event.get("inspected") or message.inspected)
        message.modified = list(event.get("modified") or message.modified)
