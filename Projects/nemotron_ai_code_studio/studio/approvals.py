"""Pauses the agent until the user approves or declines a risky action shown in the UI."""

from __future__ import annotations

import asyncio
import threading
from typing import Callable

from .tools.registry import ApprovalRequest

APPROVAL_TIMEOUT_SECONDS = 600


class ApprovalBroker:
    def __init__(self) -> None:
        self._pending: dict[str, tuple[asyncio.AbstractEventLoop, asyncio.Future[bool]]] = {}
        self._lock = threading.Lock()

    async def request(self, request: ApprovalRequest, emit: Callable[[dict], None]) -> bool:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[bool] = loop.create_future()
        with self._lock:
            self._pending[request.id] = (loop, future)
        emit({"type": "approval_request", "approval": request.public()})
        try:
            return await asyncio.wait_for(future, APPROVAL_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            emit({"type": "approval_expired", "id": request.id})
            return False
        finally:
            with self._lock:
                self._pending.pop(request.id, None)

    @staticmethod
    def _set(loop: asyncio.AbstractEventLoop, future: asyncio.Future[bool], value: bool) -> None:
        def apply() -> None:
            if not future.done():
                future.set_result(value)

        try:
            loop.call_soon_threadsafe(apply)  # the UI thread is not the agent's event-loop thread
        except RuntimeError:
            pass  # the loop already closed, so nobody is waiting

    def resolve(self, approval_id: str, approved: bool) -> bool:
        with self._lock:
            entry = self._pending.get(approval_id)
        if entry is None:
            return False
        self._set(entry[0], entry[1], bool(approved))
        return True

    def cancel_all(self) -> None:
        with self._lock:
            entries = list(self._pending.values())
        for loop, future in entries:
            self._set(loop, future, False)

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending)
