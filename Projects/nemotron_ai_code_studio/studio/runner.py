"""Background execution for the Streamlit UI.

Streamlit re-runs the whole script on every click, and a re-run interrupts a script that is still working. So the agent
and long commands run in their own threads here, and the UI polls their event lists (see ui/agent_panel.py).
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any

from .agents.coding_agent import CodingAgent, ConversationStore
from .approvals import ApprovalBroker
from .services.repository_service import ActiveRepository, RepositoryError


def friendly_error(exc: BaseException) -> str:
    """The user-facing text of any service exception (they all carry a .message, or fall back to str())."""
    return str(getattr(exc, "message", None) or exc) or exc.__class__.__name__


class AgentRun:
    """One agent request. Events are the same dictionaries the agent always emitted (status, token, tool_start, ...)."""

    def __init__(
        self, agent: CodingAgent, broker: ApprovalBroker, conversations: ConversationStore, repo: ActiveRepository,
        request: str, mode: str, conversation_id: str,
    ) -> None:
        self._agent, self._broker, self._conversations = agent, broker, conversations
        self.repo, self.request, self.mode, self.conversation_id = repo, request, mode, conversation_id
        self._events: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task | None = None
        self._thread = threading.Thread(target=self._main, name="agent-run", daemon=True)
        self.finished = threading.Event()

    # ------------------------------------------------------------- events
    def emit(self, event: dict[str, Any]) -> None:
        with self._lock:
            self._events.append(event)

    def events_since(self, cursor: int) -> tuple[list[dict[str, Any]], int]:
        with self._lock:
            return self._events[cursor:], len(self._events)

    # ------------------------------------------------------------- lifecycle
    def start(self) -> None:
        self._thread.start()

    def cancel(self) -> None:
        self._broker.cancel_all()
        loop, task = self._loop, self._task
        if loop is not None and task is not None and not self.finished.is_set():
            try:
                loop.call_soon_threadsafe(task.cancel)
            except RuntimeError:
                pass

    def _main(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        try:
            self._task = loop.create_task(self._run())
            loop.run_until_complete(self._task)
        except asyncio.CancelledError:
            pass  # the agent already emitted a "cancelled" event
        except Exception as exc:  # never leave the UI waiting for a "done" event
            self.emit({"type": "error", "message": f"The agent stopped unexpectedly: {friendly_error(exc)}"})
            self.emit({"type": "done", "message": "", "ok": False, "inspected": [], "modified": [], "change_id": "", "mode": self.mode})
        finally:
            self.finished.set()
            loop.close()

    async def _run(self) -> None:
        try:
            result = await self._agent.run(
                self.repo, self.request, self.mode, self._conversations.history(self.conversation_id), self.emit,
            )
            if result.message:
                note = f"\n\n[Files modified: {', '.join(result.modified)}]" if result.modified else ""
                self._conversations.add(self.conversation_id, self.request, result.message + note)
        except RepositoryError as exc:
            self.emit({"type": "error", "message": exc.message})
            self.emit({"type": "done", "message": exc.message, "ok": False, "inspected": [], "modified": [], "change_id": "", "mode": self.mode})


class CommandRun:
    """A shell command (terminal, tests) running in a worker thread with live output."""

    def __init__(self, repo: ActiveRepository, command: str, cwd: str = "", timeout: int | None = None) -> None:
        self.repo, self.command, self.cwd, self.timeout = repo, command, cwd, timeout
        self._chunks: list[str] = []
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self.result: Any = None
        self.error: str = ""
        self.finished = threading.Event()
        self.started = time.monotonic()
        threading.Thread(target=self._main, name="command-run", daemon=True).start()

    def _main(self) -> None:
        try:
            self.result = self.repo.terminal.run_streaming(self.command, self.cwd, self.timeout, self._on_output, self._cancel)
        except Exception as exc:
            self.error = friendly_error(exc)
        finally:
            self.finished.set()

    def _on_output(self, text: str) -> None:
        with self._lock:
            self._chunks.append(text)

    @property
    def output(self) -> str:
        with self._lock:
            return "".join(self._chunks)

    def cancel(self) -> None:
        self._cancel.set()
